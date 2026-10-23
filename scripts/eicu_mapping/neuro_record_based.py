# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Record-based neurological comorbidity correction for an exported eICU run.

Only chronic_neurological NULL -> 0 is authorized here. Existing 0/1 and
the extraction's positive-history scope are preserved. Source CSVs are read-only.
No database, model, outcome imputation, or full patient-feature rewrite is used.
"""

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

RULE = "EICU_NEURO_RECORD_BASED_MISSING_ZERO_V1_20261020"
POSITIVE = "EXPLICIT_NEURO_HISTORY_POSITIVE"
NEGATIVE = "EXPLICIT_GLOBAL_NEURO_NEGATIVE"
SCOPE = "ORIGINAL_SCOPE_UNCONFIRMED"


def binary(value):
    """Accept PostgreSQL CSV blank as NULL; reject other nonbinary values."""
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Nonbinary neurological value") from exc
    if not number.is_finite() or number not in (0, 1):
        raise ValueError("Nonbinary neurological value")
    return int(number)


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"Missing/duplicate CSV columns: {path.name}")
        rows = list(reader)
        if any(None in row or None in row.values() for row in rows):
            raise ValueError(f"Malformed CSV row: {path.name}")
        return rows


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_columns(rows, names, table):
    if not rows:
        return
    missing = set(names) - rows[0].keys()
    if missing:
        raise ValueError(f"Missing columns in {table}: {sorted(missing)}")


def correct_record(original, history, source_ready=True):
    """Pure function. Return the original binary value, correction and reason."""
    if not source_ready:
        raise ValueError("pastHistory source is unavailable or incomplete")
    original_binary = binary(original)
    candidates = {binary(row["neuro_candidate"]) for row in history}
    candidates.discard(None)
    if len(candidates) > 1:
        raise ValueError("Conflicting explicit positive/negative history: review required")
    reconstructed = next(iter(candidates)) if candidates else None
    if reconstructed != original_binary:
        raise ValueError("Raw history and exported original neurological value disagree")
    if original_binary == 1:
        reason = "RECORDED_POSITIVE_RETAINED"
    elif original_binary == 0:
        reason = "RECORDED_NEGATIVE_RETAINED"
    elif not history:
        reason = "NO_EXPORTED_TARGET_NEURO_RECORD_CODED_ZERO"
    elif all(row["mapping_status"] == SCOPE for row in history):
        reason = "SCOPE_UNCONFIRMED_ONLY_CODED_ZERO"
    else:
        reason = "OTHER_UNRESOLVED_RECORDS_CODED_ZERO"
    return original_binary, 0 if original_binary is None else original_binary, reason


def prepare_neuro(source_dir, run_id):
    """Return (mapping_rows, aggregate_audit); suitable for importing by root."""
    source_dir = Path(source_dir)
    if Path(run_id).name != run_id or not run_id.startswith("full_"):
        raise ValueError("run_id must be a filename prefix beginning full_")
    kinds = ("patient_features", "neuro_history", "cohort_membership", "summary", "SUCCESS")
    paths = {kind: source_dir / f"{run_id}_{kind}.csv" for kind in kinds}
    data = {kind: read_csv(path) for kind, path in paths.items()}
    source_evidence = [
        json.loads(row["details"]) for row in data["summary"]
        if row["section"] == "source_schema" and row["item"] == "pasthistory"
    ]
    if len(source_evidence) != 1:
        raise ValueError("Exactly one pastHistory source-availability record is required")
    evidence = source_evidence[0]
    if evidence.get("present") is not True or evidence.get("missing_columns") != []:
        raise ValueError("pastHistory source is unavailable or incomplete")
    if len(data["SUCCESS"]) != 1:
        raise ValueError("Expected one completed-run SUCCESS record")
    if run_id not in data["SUCCESS"][0].values():
        raise ValueError("SUCCESS record does not identify the requested run")

    patients, histories = data["patient_features"], data["neuro_history"]
    require_columns(patients, ("patientunitstayid", "chronic_neurological"), "patient_features")
    require_columns(histories, ("patientunitstayid", "neuro_candidate", "mapping_status",
                               "pasthistorypath", "pasthistoryvalue", "pasthistoryvaluetext",
                               "pasthistoryoffset", "pasthistoryenteredoffset"), "neuro_history")
    by_id = {row["patientunitstayid"]: row for row in patients}
    if len(by_id) != len(patients) or "" in by_id:
        raise ValueError("Patient IDs must be nonempty and unique")
    history_by_id = defaultdict(list)
    dictionary = Counter()
    for row in histories:
        if row["patientunitstayid"] not in by_id:
            raise ValueError("Neurological raw row belongs to a patient outside the export")
        offset = Decimal(row["pasthistoryoffset"])
        entered = row["pasthistoryenteredoffset"].strip()
        if not offset.is_finite() or not 0 <= offset < 1440:
            raise ValueError("Neurological history is outside the pre-landmark window")
        if entered and (not Decimal(entered).is_finite() or Decimal(entered) >= 1440):
            raise ValueError("Neurological history was entered at/after the landmark")
        candidate = binary(row["neuro_candidate"])
        expected = 1 if row["mapping_status"] == POSITIVE else (
            0 if row["mapping_status"] == NEGATIVE else None)
        if candidate != expected:
            raise ValueError("Raw candidate conflicts with its extraction mapping status")
        history_by_id[row["patientunitstayid"]].append(row)
        dictionary[(row["pasthistorypath"], row["pasthistoryvalue"],
                    row["pasthistoryvaluetext"], row["mapping_status"],
                    row["neuro_candidate"])] += 1

    mapping, transitions, bases = [], Counter(), Counter()
    for patient in patients:
        key = patient["patientunitstayid"]
        history = history_by_id.get(key, [])
        raw, corrected, reason = correct_record(patient["chronic_neurological"], history)
        transitions[f"{'NULL' if raw is None else raw}->{corrected}"] += 1
        bases[reason] += 1
        mapping.append({
            "patientunitstayid": key,
            "chronic_neurological_raw": patient["chronic_neurological"],
            "chronic_neurological_corrected": corrected,
            "chronic_neurological_raw_missing": int(raw is None),
            "neuro_correction_basis": reason,
            "neuro_target_raw_rows": len(history),
            "neuro_positive_raw_rows": sum(row["mapping_status"] == POSITIVE for row in history),
            "neuro_explicit_negative_raw_rows": sum(row["mapping_status"] == NEGATIVE for row in history),
            "neuro_scope_unconfirmed_raw_rows": sum(row["mapping_status"] == SCOPE for row in history),
            "neuro_scope_unconfirmed_present": int(any(row["mapping_status"] == SCOPE for row in history)),
            "neuro_source_table_available": 1,
            "neuro_correction_rule": RULE,
        })
    mapped = {row["patientunitstayid"]: row for row in mapping}
    variants = defaultdict(Counter)
    membership_keys = set()
    for row in data["cohort_membership"]:
        pair = (row["patientunitstayid"], row["variant"])
        if pair in membership_keys or pair[0] not in mapped:
            raise ValueError("Duplicate or unmatched cohort membership")
        membership_keys.add(pair)
        result = mapped[pair[0]]
        raw = binary(result["chronic_neurological_raw"])
        count = variants[pair[1]]
        count["patients"] += 1
        count[f"raw_{'missing' if raw is None else raw}"] += 1
        count[f"corrected_{result['chronic_neurological_corrected']}"] += 1
        count["missing_to_zero"] += result["chronic_neurological_raw_missing"]
        count["scope_unconfirmed_only_to_zero"] += (
            result["neuro_correction_basis"] == "SCOPE_UNCONFIRMED_ONLY_CODED_ZERO")
    audit = {
        "rule": RULE,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "definition": (
            "Record-based comorbidity: keep extraction-defined recorded positive=1; "
            "keep existing 0; code remaining missing=0 as explicitly authorized. "
            "Zero means no mapped positive history, not clinically excluded disease."
        ),
        "source_availability": evidence,
        "patient_count": len(patients),
        "history_rows": len(histories),
        "patients_with_target_neuro_rows": len({row["patientunitstayid"] for row in histories}),
        "raw_counts": dict(Counter("missing" if binary(row["chronic_neurological"]) is None
                                  else str(binary(row["chronic_neurological"])) for row in patients)),
        "corrected_counts": dict(Counter(str(row["chronic_neurological_corrected"]) for row in mapping)),
        "transitions": dict(transitions),
        "correction_bases": dict(bases),
        "variants": {key: dict(value) for key, value in sorted(variants.items())},
        "history_mapping_status_counts": dict(Counter(row["mapping_status"] for row in histories)),
        "scope_unconfirmed_patients": sum(row["neuro_scope_unconfirmed_present"] for row in mapping),
        "history_rows_missing_entry_time": sum(not row["pasthistoryenteredoffset"] for row in histories),
        "source_files": {key: {"path": str(path.resolve()), "sha256": sha256(path)}
                         for key, path in paths.items()},
        "raw_dictionary": [
            {"path": key[0], "value": key[1], "value_text": key[2],
             "mapping_status": key[3], "raw_candidate": key[4], "rows": count}
            for key, count in dictionary.most_common()
        ],
        "limitations": [
            "The source table and required columns exist. Per-patient completeness of all "
            "pastHistory documentation cannot be determined from this target-filtered CSV.",
            "TIA and intracranial mass remain ORIGINAL_SCOPE_UNCONFIRMED in the extraction. "
            "The missing-to-zero policy does not newly include them as positive comorbidities.",
            "The original MIMIC ICD code list is unavailable; positive-history scope remains "
            "the existing adapted eICU definition. Seizure and historical stroke records are retained.",
            "Only records within ICU minutes [0,1440), with entry before 1440 or entry missing, "
            "were extracted. No later history is used.",
        ],
    }
    return mapping, audit


def write_outputs(output_dir, mapping, audit):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [output_dir / name for name in
             ("neuro_record_based_mapping.csv", "neuro_audit.json", "neuro_audit.txt")]
    if any(path.exists() for path in paths):
        raise FileExistsError("Output already exists; choose a new output directory")
    with paths[0].open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mapping[0]))
        writer.writeheader()
        writer.writerows(mapping)
    with paths[1].open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    lines = [
        "eICU 慢性神经病史：按记录定义的缺失转0审计",
        f"规则：{RULE}",
        f"运行批次：{audit['run_id']}",
        f"来源：{audit['source_availability']['qualified_name']} 存在，所需列齐全。",
        f"分析对象：{audit['patient_count']}人（患者级特征导出的三个队列并集）。",
        f"原值人数：{json.dumps(audit['raw_counts'], ensure_ascii=False)}",
        f"修正后人数：{json.dumps(audit['corrected_counts'], ensure_ascii=False)}",
        f"转换人数：{json.dumps(audit['transitions'], ensure_ascii=False)}",
        f"转换依据：{json.dumps(audit['correction_bases'], ensure_ascii=False)}",
        f"神经病史原始记录：{audit['history_rows']}行，涉及{audit['patients_with_target_neuro_rows']}人。",
        "0的含义：现有映射范围内未记录阳性神经病史（record-based comorbidity）。",
        "0不代表经临床检查排除疾病，也不能证明每位患者的病史记录完整。",
        "原0/1与既有阳性疾病映射不变；原始缺失和范围未确认标志保留在旁列。",
        "TIA/颅内占位原标为范围未确认；其仅有此类记录者依用户缺失转0政策编码，"
        "必须与完全无导出目标神经记录者区别解释。",
        "",
        "各预设队列：",
    ]
    lines.extend(f"{name}: {json.dumps(value, ensure_ascii=False)}"
                 for name, value in audit["variants"].items())
    lines.extend([
        "",
        "SQL证据：40_features.sql第162–207行；60_export_tables.sql第1–9及21–59行。",
        "原提取限制为ICU第0至24小时病史及预测前录入；原始ICD清单未取得，"
        "现有eICU阳性范围仍属于适配定义。",
        "患者级结果仅写本地映射CSV；源CSV及主SQL均未修改。",
        "完整来源哈希、字典和计数见同目录neuro_audit.json。",
    ])
    with paths[2].open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return paths


def self_test():
    positive = {"neuro_candidate": "1", "mapping_status": POSITIVE}
    negative = {"neuro_candidate": "0", "mapping_status": NEGATIVE}
    unresolved = {"neuro_candidate": "", "mapping_status": SCOPE}
    assert correct_record("", [])[1:] == (0, "NO_EXPORTED_TARGET_NEURO_RECORD_CODED_ZERO")
    assert correct_record("1", [positive])[1] == 1
    assert correct_record("0", [negative])[1] == 0
    assert correct_record("", [unresolved])[2] == "SCOPE_UNCONFIRMED_ONLY_CODED_ZERO"
    for bad in ("NaN", "Infinity", "-1", "2", "unknown"):
        try:
            binary(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid binary input was accepted")
    for args in (("", [], False), ("", [positive], True), ("", [positive, negative], True)):
        try:
            correct_record(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid provenance was accepted")
    return "PASS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(self_test())
        return
    if not all((args.source_dir, args.run_id, args.output_dir)):
        parser.error("--source-dir, --run-id and --output-dir are required")
    mapping, audit = prepare_neuro(args.source_dir, args.run_id)
    write_outputs(args.output_dir, mapping, audit)
    print(json.dumps({key: audit[key] for key in
                      ("patient_count", "raw_counts", "corrected_counts", "transitions",
                       "correction_bases", "variants")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

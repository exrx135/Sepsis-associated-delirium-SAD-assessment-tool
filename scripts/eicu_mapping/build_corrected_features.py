# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Apply reviewed record-based mappings to copies, never the raw export."""
from pathlib import Path
import csv
import hashlib
import json

BASE = _sad_private_path("eicu_mapping")
BASE.mkdir(parents=True, exist_ok=True)
SOURCE = _sad_private_path("eicu_exports")
RUN = "full_20261020_222456_478585_54652"
VERSION = "EICU_RECORDED_MV_NEURO_V4_20261020"
OUT = BASE / "corrected_data"
MV = "invasive_vent_12h_24h_pre_dx"
NEURO = "chronic_neurological"
MV_DEF = (
    "Recorded-state adaptation in ICU[0,720)min: concordant same-time careplan "
    "Intubated airway plus Ventilated status gives1. Paired not-intubated plus "
    "spontaneous/NIV status without unresolved positive or conflicting evidence gives0. "
    "Otherwise NULL. A0 denotes documented assessment state, not continuous proof "
    "of no ventilation throughout12h. APACHE/day1 and0-24h values do not replace this input."
)
NEURO_DEF = (
    "User-specified record-based comorbidity: existing in-scope recorded positive=1; "
    "otherwise0. Original missing values and unresolved-scope flags are retained "
    "in the audit. Zero does not assert clinical exclusion of neurological disease."
)


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def write(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def keyed(rows):
    result = {row["patientunitstayid"]: row for row in rows}
    assert len(result) == len(rows), "Duplicate stay IDs"
    return result


def main():
    originals = sorted(SOURCE.glob(RUN + "_*.csv"))
    original_hashes = {path.name: digest(path) for path in originals}
    fields, source_patients = read(SOURCE / f"{RUN}_patient_features.csv")
    long_fields, source_long = read(SOURCE / f"{RUN}_feature_long.csv")
    cat_fields, source_catalog = read(SOURCE / f"{RUN}_feature_definitions.csv")
    _, mv_rows = read(BASE / "mv_audit" / "mv_mapping.csv")
    _, neuro_rows = read(
        BASE / "neuro" / ("audit_" + RUN) / "neuro_record_based_mapping.csv")
    mv_map, neuro_map = keyed(mv_rows), keyed(neuro_rows)
    raw_map = keyed(source_patients)
    assert set(raw_map) == set(mv_map) == set(neuro_map)
    names = [name for name in fields if name in {r["feature"] for r in source_catalog}]
    assert len(names) == 14
    extra = [
        "mv_original_raw", "chronic_neurological_original_raw",
        "mv_recorded_0_24h_audit_only", "feature_mapping_version",
    ]
    assert not set(extra).intersection(fields)
    corrected = []
    for source in source_patients:
        row = dict(source)
        pid = row["patientunitstayid"]
        assert neuro_map[pid]["chronic_neurological_raw"] == source[NEURO]
        mv = mv_map[pid]["mv_0_12h"]
        neuro = neuro_map[pid]["chronic_neurological_corrected"]
        assert mv in ["0", "1", ""] and neuro in ["0", "1"]
        assert source[MV] != "1" or mv == "1", "Existing positive must not be lost"
        row["mv_original_raw"], row["chronic_neurological_original_raw"] = source[MV], source[NEURO]
        row[MV], row[NEURO] = mv, neuro
        row["mv_recorded_0_24h_audit_only"] = mv_map[pid]["mv_0_24h"]
        row["feature_mapping_version"] = VERSION
        missing = sorted(n for n in names if row[n] == "")
        row["missing_feature_count"] = str(len(missing))
        row["observed_feature_count"] = str(14 - len(missing))
        row["missing_features"] = "{" + ",".join(missing) + "}"
        row["processing_status"] = "MAPPING_CORRECTED_UNIMPUTED"
        corrected.append(row)
    corrected_map = keyed(corrected)
    allowed = {MV, NEURO, "missing_feature_count", "observed_feature_count",
               "missing_features", "processing_status"}
    for row in corrected:
        raw = raw_map[row["patientunitstayid"]]
        assert all(row[k] == raw[k] for k in fields if k not in allowed)
    corrected_long = []
    for source in source_long:
        row = dict(source)
        if row["feature"] in [MV, NEURO]:
            row["candidate_value"] = corrected_map[row["patientunitstayid"]][row["feature"]]
            row["is_missing"] = "t" if row["candidate_value"] == "" else "f"
            row["definition_status"] = (
                "V4_RECORDED_STATE_ADAPTATION" if row["feature"] == MV
                else "V4_USER_RECORD_BASED_ABSENCE_ZERO")
            row["definition"] = MV_DEF if row["feature"] == MV else NEURO_DEF
        row["processing_status"] = "MAPPING_CORRECTED_UNIMPUTED"
        corrected_long.append(row)
    corrected_catalog = []
    for source in source_catalog:
        row = dict(source)
        if row["feature"] in [MV, NEURO]:
            row["definition_status"] = (
                "V4_RECORDED_STATE_ADAPTATION" if row["feature"] == MV
                else "V4_USER_RECORD_BASED_ABSENCE_ZERO")
            row["definition"] = MV_DEF if row["feature"] == MV else NEURO_DEF
        corrected_catalog.append(row)
    assert len(corrected_long) == 14 * len(corrected)
    assert len({(r["patientunitstayid"], r["feature"]) for r in corrected_long}) == len(corrected_long)
    for row in corrected_long:
        value = corrected_map[row["patientunitstayid"]][row["feature"]]
        # Decimal formatting can differ in the original long/wide export.
        assert (value == "" and row["candidate_value"] == "") or (
            value != "" and row["candidate_value"] != "" and float(value) == float(row["candidate_value"]))
        assert (row["is_missing"] == "t") == (value == "")
    groups = {}
    for variant in ["union", "strict", "allow_missing_rass", "baseline_negative"]:
        rows = corrected if variant == "union" else [
            r for r in corrected if r["eligible_" + variant] == "t"]
        groups[variant] = {
            "n": len(rows),
            "mv": {k or "missing": sum(r[MV] == k for r in rows) for k in ["1", "0", ""]},
            "neuro": {k: sum(r[NEURO] == k for r in rows) for k in ["1", "0"]},
            "events": None if variant == "union" else sum(
                r["sad_" + variant] == "1" for r in rows),
        }
    OUT.mkdir(exist_ok=True)
    write(OUT / "patient_features_corrected.csv", fields + extra, corrected)
    write(OUT / "feature_long_corrected.csv", long_fields, corrected_long)
    write(OUT / "feature_definitions_corrected.csv", cat_fields, corrected_catalog)
    assert original_hashes == {path.name: digest(path) for path in originals}
    input_paths = [
        BASE / "mv_audit" / "mv_mapping.csv",
        BASE / "neuro" / ("audit_" + RUN) / "neuro_record_based_mapping.csv",
    ]
    report = {
        "run_id": RUN, "mapping_version": VERSION, "source": str(SOURCE),
        "original_file_hashes": original_hashes,
        "mapping_input_hashes": {str(p.relative_to(BASE)): digest(p) for p in input_paths},
        "groups": groups,
        "checks": {
            "original_exports_unchanged": True, "no_rows_added_or_removed": True,
            "only_mv_neuro_and_metadata_changed": True, "wide_long_consistent": True,
            "cohort_flags_and_outcomes_unchanged": True,
            "no_predictions_or_outcome_driven_rule_selection": True,
            "zero_does_not_assert_continuous_12h_no_mv": True,
        },
        "outputs": {
            p.name: {"bytes": p.stat().st_size, "sha256": digest(p)}
            for p in OUT.glob("*.csv")
        },
    }
    (OUT / "correction_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"groups": groups, "checks": report["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

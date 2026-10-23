# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Correct only latest-pre-landmark revision selection in existing lab exports.
Source files remain untouched. No alias, unit, range, window, or model changes.
"""
from pathlib import Path
from collections import defaultdict, Counter
from decimal import Decimal
import csv
import json
import hashlib

SOURCE=_sad_private_path("eicu_exports")
RUN="full_20261020_222456_478585_54652"
OUT=_sad_private_path("eicu_validation", "lab_audit")
OUT.mkdir(parents=True, exist_ok=True)
FEATURES=["avg_ptt","avg_po2","avg_pt","avg_aniongap",
          "avg_rdw","avg_mchc","avg_calcium","avg_hematocrit"]
ACCEPTED={"CANDIDATE_ASSUMED_UNIT","CANDIDATE_EXPLICIT_UNIT"}
VERSION="EICU_LAB_LATEST_PRE1440_REVISION_V1_20261020"

def read(name):
    with (SOURCE/f"{RUN}_{name}.csv").open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def dec(value):
    return Decimal(value) if value not in ("",None) else None

def pick_latest_before_t0(rows):
    """Rows share patient, exact labname and draw offset.
    Return (value, status). Conflicting values at the latest revision stay NULL.
    Missing/invalid latest revision does not fall back to an older value.
    """
    eligible=[r for r in rows if dec(r["labresultrevisedoffset"]) is not None
              and dec(r["labresultrevisedoffset"])<1440
              and 0<=dec(r["labresultoffset"])<1440]
    if not eligible:
        return None,"NO_KNOWN_PRE_T0_REVISION"
    last=max(dec(r["labresultrevisedoffset"]) for r in eligible)
    newest=[r for r in eligible if dec(r["labresultrevisedoffset"])==last]
    usable={dec(r["candidate_value"]) for r in newest if r["mapping_status"] in ACCEPTED}
    nonmissing_invalid=any(r["labresult"] not in ("",None)
                          and r["mapping_status"] not in ACCEPTED for r in newest)
    if len(usable)>1:
        return None,"CONFLICT_AT_LATEST_REVISION"
    if nonmissing_invalid:
        return None,"INVALID_LATEST_REVISION"
    if not usable:
        return None,"LATEST_REVISION_HAS_NO_USABLE_VALUE"
    return next(iter(usable)),"LATEST_PRE_T0_REVISION_ACCEPTED"

def corrected_values(rows):
    by_name_time=defaultdict(list)
    for r in rows:
        if r["feature"] in FEATURES:
            by_name_time[(r["patientunitstayid"],r["feature"],r["labname"],dec(r["labresultoffset"]))].append(r)
    by_feature_time=defaultdict(list)
    decisions=Counter()
    for (pid,feature,name,offset),group in by_name_time.items():
        value,status=pick_latest_before_t0(group)
        decisions[(feature,status)]+=1
        by_feature_time[(pid,feature,offset)].append(value)
    by_patient_feature=defaultdict(list)
    for (pid,feature,offset),values in by_feature_time.items():
        # If aliases occur, require the independently selected values to agree.
        unique=set(values)
        if len(unique)==1 and None not in unique:
            by_patient_feature[(pid,feature)].append(next(iter(unique)))
    out={}
    for key,values in by_patient_feature.items():
        out[key]=sum(values)/len(values)
    return out,decisions

def same_value(a,b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a-b)<=Decimal("0.00000001")

def main():
    raw=read("lab_audit")
    patients=read("patient_features")
    values,decisions=corrected_values(raw)
    corrected=[]
    changes=[]
    for r in patients:
        pid=r["patientunitstayid"]
        out={"patientunitstayid":pid}
        for feature in FEATURES:
            old=dec(r[feature])
            new=values.get((pid,feature))
            unchanged=same_value(old,new)
            out[feature]=r[feature] if unchanged else (str(new) if new is not None else "")
            if not unchanged:
                reason=("RESTORED_BY_LATEST_PRE_T0_REVISION" if old is None and new is not None
                        else "REMOVED_NO_VALID_LATEST_PRE_T0_REVISION" if new is None
                        else "MEAN_CHANGED_AFTER_REVISION_SELECTION")
                changes.append({"patientunitstayid":pid,"feature":feature,
                    "original_value":r[feature],"corrected_value":out[feature],
                    "reason":reason,"mapping_version":VERSION})
        corrected.append(out)
    with (OUT/"lab_values_corrected.csv").open("w",encoding="utf-8-sig",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=["patientunitstayid"]+FEATURES);wr.writeheader();wr.writerows(corrected)
    with (OUT/"changes.csv").open("w",encoding="utf-8-sig",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=["patientunitstayid","feature","original_value","corrected_value","reason","mapping_version"])
        wr.writeheader();wr.writerows(changes)
    ids_by_group={"union":{r["patientunitstayid"] for r in patients}}
    for name,col in [("strict","eligible_strict"),("allow_missing_rass","eligible_allow_missing_rass"),
                     ("baseline_negative","eligible_baseline_negative")]:
        ids_by_group[name]={r["patientunitstayid"] for r in patients if r[col]=="t"}
    original={r["patientunitstayid"]:r for r in patients}
    new_by_id={r["patientunitstayid"]:r for r in corrected}
    stats=[]
    for group,ids in ids_by_group.items():
        for feature in FEATURES:
            group_changes=[r for r in changes if r["patientunitstayid"] in ids and r["feature"]==feature]
            stats.append({"cohort":group,"feature":feature,"n":len(ids),
                "original_observed":sum(original[pid][feature]!="" for pid in ids),
                "corrected_observed":sum(new_by_id[pid][feature]!="" for pid in ids),
                "corrected_missing":sum(new_by_id[pid][feature]=="" for pid in ids),
                "changed_patients":len(group_changes),
                "change_reasons":dict(Counter(r["reason"] for r in group_changes))})
    summary={"version":VERSION,"source_run":RUN,"source_rows":len(raw),"patients":len(patients),
        "changed_patient_feature_pairs":len(changes),
        "changed_patients":len({r["patientunitstayid"] for r in changes}),
        "aggregate":stats,
        "latest_revision_decisions":[{"feature":f,"decision":d,"timepoints":v} for (f,d),v in sorted(decisions.items())],
        "scope":"Existing filtered export only. Preserve label/unit mapping and [0,1440) draw window. Known latest revision must be <1440; conflicting latest values remain missing. No t0-after value used.",
        "source_sha256":{name:hashlib.sha256((SOURCE/f"{RUN}_{name}.csv").read_bytes()).hexdigest()
                         for name in ["patient_features","lab_audit"]}}
    (OUT/"lab_revision_correction_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:summary[k] for k in ["version","patients","changed_patient_feature_pairs","changed_patients"]},ensure_ascii=False))
    for r in stats:
        if r["cohort"]=="strict":
            print(json.dumps(r,ensure_ascii=False))

if __name__=="__main__":
    main()

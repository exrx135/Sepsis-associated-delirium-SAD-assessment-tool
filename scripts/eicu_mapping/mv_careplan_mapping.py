# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Map already-exported eICU respiratory evidence, without model/outcome use.

Public API: build_mapping(source_dir, run_id) -> list[dict], one row per patient.
Values are 1, 0, or None. Each window is half-open [0,720) or [0,1440).
0 means documented non-invasive/spontaneous state without unresolved positive
evidence in this export; it does not prove absence throughout the entire window.
No forward fill, near-time pairing, imputation, or source-file mutation.
"""
from pathlib import Path
from collections import defaultdict, Counter
import csv
import json

VERSION = "EICU_CAREPLAN_PAIRED_STATE_V3_20261020"
SOURCE = _sad_private_path("eicu_exports")
RUN_ID = "full_20261020_222456_478585_54652"
OUT = _sad_private_path("eicu_mapping", "mv_audit")
OUT.mkdir(parents=True, exist_ok=True)
WINDOWS = (("0_12h",720),("0_24h",1440))

def read_source(source_dir, run_id, suffix):
    with (Path(source_dir)/(run_id.rstrip("_")+"_"+suffix+".csv")).open(
            encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def number(value):
    return float(value) if value not in ("",None) else None

def careplan_state(row):
    group = row["cplgroup"].strip().lower()
    value = row["cplitemvalue"].strip().lower()
    if group == "airway":
        if value.startswith("intubated/"):
            return "artificial_airway"
        if value.startswith("not intubated/"):
            return "no_artificial_airway"
        return "unknown_airway"
    if group == "ventilation":
        if value.startswith("ventilated - "):
            return "ventilated"
        if value == "non-invasive ventilation":
            return "niv"
        if value.startswith("spontaneous - "):
            return "spontaneous"
        return "unknown_ventilation"
    # "No intubation" is a care limitation; protocols are not current state.
    return "other"

def classify_point(states):
    # Unknown/blank alongside a known state remains auditable, not conflicting.
    conflict = (
        {"artificial_airway","no_artificial_airway"} <= states
        or ("ventilated" in states and bool(states & {"niv","spontaneous"}))
        or {"niv","spontaneous"} <= states
        or {"artificial_airway","niv"} <= states
        or {"no_artificial_airway","ventilated"} <= states
    )
    positive = {"artificial_airway","ventilated"} <= states and not conflict
    negative_spont = {"no_artificial_airway","spontaneous"} <= states and not conflict
    negative_niv = {"no_artificial_airway","niv"} <= states and not conflict
    return {
        "positive":positive,
        "negative_spontaneous":negative_spont,
        "negative_niv":negative_niv,
        "conflict":conflict,
        "unknown_present":bool(states & {"unknown_airway","unknown_ventilation"}),
        "isolated_artificial_airway":"artificial_airway" in states and not positive,
        "unresolved_ventilated":"ventilated" in states and not positive,
    }

def build_mapping(source_dir, run_id):
    patients = read_source(source_dir,run_id,"patient_features")
    careplan = read_source(source_dir,run_id,"careplan")
    treatments = read_source(source_dir,run_id,"treatment")
    care = read_source(source_dir,run_id,"respiratory_care")
    chart = read_source(source_dir,run_id,"respiratory_chart")
    pid_set = {r["patientunitstayid"] for r in patients}
    cp_points = defaultdict(set)
    tr_by_patient = defaultdict(list)
    care_by_patient = defaultdict(list)
    chart_by_patient = defaultdict(list)
    for r in careplan:
        if r["patientunitstayid"] in pid_set:
            cp_points[(r["patientunitstayid"],number(r["cplitemoffset"]))].add(careplan_state(r))
    points_by_patient = defaultdict(list)
    for (pid,offset),states in cp_points.items():
        points_by_patient[pid].append((offset,classify_point(states)))
    for source,target in [(treatments,tr_by_patient),(care,care_by_patient),(chart,chart_by_patient)]:
        for r in source:
            if r["patientunitstayid"] in pid_set:
                target[r["patientunitstayid"]].append(r)
    output=[]
    for patient in patients:
        pid=patient["patientunitstayid"]
        old_positive=number(patient["invasive_vent_12h_24h_pre_dx"]) == 1
        row={"patientunitstayid":pid,"mapping_version":VERSION,
             "old_v2_mv":number(patient["invasive_vent_12h_24h_pre_dx"]),
             "negative_definition":"Documented paired state; not continuous absence throughout window.",
             "time_definition":"Careplan/treatment offsets are documentation times, not support start/end."}
        for name,hi in WINDOWS:
            points=[(t,p) for t,p in points_by_patient[pid] if t is not None and 0<=t<hi]
            count=lambda key:sum(p[key] for t,p in points)
            cp_pos=count("positive")
            cp_neg_sp=count("negative_spontaneous")
            cp_neg_niv=count("negative_niv")
            conflict=count("conflict")
            unknown=count("unknown_present")
            unresolved_cp=count("unresolved_ventilated")
            isolated_cp=count("isolated_artificial_airway")
            tr=[r for r in tr_by_patient[pid] if 0<=number(r["treatmentoffset"])<hi]
            # Keep the root "mechanical ventilation" treatment independently;
            # unlike "non-invasive ventilation", it does not by itself prove route.
            core_mv=sum("|mechanical ventilation" in r["treatmentstring"].lower()
                        and "|non-invasive ventilation" not in r["treatmentstring"].lower()
                        and r["evidence_class"] != "NEGATED_PLANNED_OR_HISTORICAL_AUDIT_ONLY" for r in tr)
            weaning=sum("|ventilator weaning" in r["treatmentstring"].lower()
                        and r["evidence_class"] != "NEGATED_PLANNED_OR_HISTORICAL_AUDIT_ONLY" for r in tr)
            tr_airway=sum(r["evidence_class"]=="AIRWAY_PROCEDURE_OR_STATUS_ONLY" for r in tr)
            tr_niv=sum("|non-invasive ventilation" in r["treatmentstring"].lower()
                       and r["evidence_class"] != "NEGATED_PLANNED_OR_HISTORICAL_AUDIT_ONLY" for r in tr)
            rc=[r for r in care_by_patient[pid] if 0<=number(r["respcarestatusoffset"])<hi]
            care_airway=sum(r["p_airway"]=="t" for r in rc)
            rp=[r for r in chart_by_patient[pid] if 0<=number(r["respchartoffset"])<hi
                and r["known_by_landmark"]=="t"]
            chart_vent=sum(r["evidence_class"]=="VENTILATOR" for r in rp)
            chart_airway=sum(r["evidence_class"]=="INVASIVE_AIRWAY" for r in rp)
            blockers={
                "same_time_conflict":conflict,
                "unresolved_careplan_ventilated":unresolved_cp,
                "isolated_careplan_artificial_airway":isolated_cp,
                "treatment_mechanical_ventilation_route_unspecified":core_mv,
                "treatment_weaning_route_unspecified":weaning,
                "treatment_artificial_airway_only":tr_airway,
                "respiratorycare_artificial_airway_only":care_airway,
                "respiratorychart_ventilator_route_unresolved":chart_vent,
                "respiratorychart_artificial_airway_only":chart_airway,
            }
            if old_positive or cp_pos:
                value=1
                reason="preserved_v2_positive" if old_positive else "paired_careplan_invasive_support"
            elif cp_neg_sp+cp_neg_niv and not any(blockers.values()):
                value=0
                reason="paired_documented_noninvasive_or_spontaneous_state"
            else:
                value=None
                reason="unresolved_evidence" if any(blockers.values()) else "no_qualifying_paired_state"
            row.update({
                f"mv_{name}":value,
                f"reason_{name}":reason,
                f"positive_timepoints_{name}":cp_pos,
                f"spontaneous_negative_timepoints_{name}":cp_neg_sp,
                f"niv_negative_timepoints_{name}":cp_neg_niv,
                f"conflicting_timepoints_{name}":conflict,
                f"unknown_or_blank_timepoints_{name}":unknown,
                f"treatment_mechanical_ventilation_records_{name}":core_mv,
                f"treatment_niv_records_{name}":tr_niv,
                f"blockers_{name}":"|".join(k for k,v in blockers.items() if v),
                f"blocker_record_counts_{name}":json.dumps(blockers,separators=(",",":")),
            })
        output.append(row)
    return output

def main():
    mapped=build_mapping(SOURCE,RUN_ID)
    with (OUT/"mv_mapping.csv").open("w",encoding="utf-8-sig",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=list(mapped[0]));wr.writeheader();wr.writerows(mapped)
    patients=read_source(SOURCE,RUN_ID,"patient_features")
    groups={"union":{r["patientunitstayid"] for r in patients}}
    for label,field in [("strict","eligible_strict"),("allow_missing_rass","eligible_allow_missing_rass"),
                        ("baseline_negative","eligible_baseline_negative")]:
        groups[label]={r["patientunitstayid"] for r in patients if r[field]=="t"}
    summary={"mapping_version":VERSION,"source_run":RUN_ID,
        "no_model_or_outcome_used":True,
        "negative_definition":mapped[0]["negative_definition"],
        "rules":"Any unconflicted paired positive or valid prior V2 positive takes precedence. Documented paired negative requires no unresolved generic MV, isolated artificial airway, or true same-time contradiction anywhere in the window.",
        "groups":[]}
    for group,ids in groups.items():
        rows=[r for r in mapped if r["patientunitstayid"] in ids]
        for window,_ in WINDOWS:
            k=f"mv_{window}"
            summary["groups"].append({
                "cohort":group,"window":window,"patients":len(rows),
                "positive":sum(r[k]==1 for r in rows),
                "documented_state_negative":sum(r[k]==0 for r in rows),
                "unknown":sum(r[k] is None for r in rows),
                "positive_paired_patients":sum(r[f"positive_timepoints_{window}"]>0 for r in rows),
                "spontaneous_negative_point_patients":sum(r[f"spontaneous_negative_timepoints_{window}"]>0 for r in rows),
                "niv_negative_point_patients":sum(r[f"niv_negative_timepoints_{window}"]>0 for r in rows),
                "same_time_conflict_patients":sum(r[f"conflicting_timepoints_{window}"]>0 for r in rows),
                "same_time_conflict_points":sum(r[f"conflicting_timepoints_{window}"] for r in rows),
                "blank_or_unknown_points":sum(r[f"unknown_or_blank_timepoints_{window}"] for r in rows),
                "treatment_mechanical_ventilation_patients":sum(r[f"treatment_mechanical_ventilation_records_{window}"]>0 for r in rows),
                "treatment_mechanical_ventilation_records":sum(r[f"treatment_mechanical_ventilation_records_{window}"] for r in rows),
                "treatment_explicit_niv_patients":sum(r[f"treatment_niv_records_{window}"]>0 for r in rows),
                "reason_counts":dict(Counter(r[f"reason_{window}"] for r in rows)),
            })
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

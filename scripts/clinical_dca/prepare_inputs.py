# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Copy the supplied SOFA source and link it by stay_id without changing labels."""
from pathlib import Path
import hashlib
import json
import shutil
import pandas as pd
import numpy as np

ROOT=_sad_private_path("clinical_dca")
for name in ['data','results','figures','qa','notes']:(ROOT/name).mkdir(parents=True,exist_ok=True)
SAVED=ROOT/'source_data'/'first_day_sofa.csv'
SUPPLIED=SAVED
RISK=_sad_private_path('eicu_validation','reference_sources','identified_frozen_risk_scores.csv')
RAW=_sad_private_path('mimic_study','SAD with all variables.csv')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={str(p):sha(p) for p in [SUPPLIED,RISK,RAW]}

sofa=pd.read_csv(SAVED)
risk=pd.read_csv(RISK)
raw=pd.read_csv(RAW,usecols=['stay_id','subject_id','hadm_id','sad_7days','invasive_vent_12h_24h_pre_dx'])
assert sofa.stay_id.is_unique and risk.stay_id.is_unique and raw.stay_id.is_unique
assert len(risk)==len(raw)==17851
components=['respiration','coagulation','liver','cardiovascular','cns','renal']
renamed=sofa.rename(columns={'subject_id':'sofa_subject_id','hadm_id':'sofa_hadm_id','sofa':'sofa_first_day',
                            **{c:'sofa_component_'+c for c in components}})
d=risk.merge(renamed,on='stay_id',how='left',validate='one_to_one',indicator=True,sort=False)
assert d['_merge'].eq('both').all(), 'SOFA source does not cover the complete original cohort'
assert d.subject_id.eq(d.sofa_subject_id).all() and d.hadm_id.eq(d.sofa_hadm_id).all()
d=d.drop(columns=['_merge','sofa_subject_id','sofa_hadm_id'])
rr=raw.rename(columns={'subject_id':'mv_subject_id','hadm_id':'mv_hadm_id',
                       'invasive_vent_12h_24h_pre_dx':'mv_pre_diagnosis','sad_7days':'raw_original_outcome'})
d=d.merge(rr,on='stay_id',how='left',validate='one_to_one',sort=False)
assert d.subject_id.eq(d.mv_subject_id).all() and d.hadm_id.eq(d.mv_hadm_id).all()
assert d.legacy_sad_7days.eq(d.raw_original_outcome).all()
d=d.drop(columns=['mv_subject_id','mv_hadm_id','raw_original_outcome'])
assert d.sofa_first_day.notna().all() and d.sofa_first_day.between(0,24).all()
assert np.equal(d.sofa_first_day,np.floor(d.sofa_first_day)).all()
assert d.mv_pre_diagnosis.notna().all() and set(d.mv_pre_diagnosis.unique())=={0,1}
assert d.risk_probability_frozen14.between(0,1).all()
component_cols=['sofa_component_'+c for c in components]
assert d[component_cols].fillna(0).sum(axis=1).eq(d.sofa_first_day).all()
assert not d.subject_id.duplicated().any(), 'Paired bootstrap must cluster repeated patients'
test=d[d.split.eq('test')]
assert len(test)==3571 and int(test.legacy_sad_7days.sum())==467
d.to_csv(ROOT/'data'/'analysis_cohort_sofa_mv.csv',index=False,encoding='utf-8-sig')
report={'supplied_file':str(SUPPLIED),'saved_source_file':str(SAVED),'source_rows':len(sofa),
        'source_sofa_sha256':sha(SAVED),'source_copy_binary_identical':True,
        'matched_original_cohort':len(d),'matched_test_set':len(test),
        'id_disagreements':0,'missing_sofa_total_cohort':int(d.sofa_first_day.isna().sum()),
        'missing_sofa_total_test':int(test.sofa_first_day.isna().sum()),
        'sofa_total_range':[int(d.sofa_first_day.min()),int(d.sofa_first_day.max())],
        'source_components_missing_in_cohort':{c:int(d['sofa_component_'+c].isna().sum()) for c in components},
        'total_equals_supplied_components_with_missing_as_zero':True,
        'missing_mv':int(d.mv_pre_diagnosis.isna().sum()),
        'mv_source_field':'invasive_vent_12h_24h_pre_dx',
        'test_events_original_sad':int(test.legacy_sad_7days.sum()),
        'test_nonevents_original_sad':int(test.legacy_sad_7days.eq(0).sum()),
        'original_labels_changed':False,'original_model_predictions_changed':False,
        'sofa_label_for_figures':'ICU first-day SOFA',
        'sofa_is_not_assumed_to_be_sepsis_onset_sofa':True,
        'baseline_model_fit_split':'train only; independent test set never used for fitting',
        'source_files_unchanged':before,
        'analysis_cohort_sha256':sha(ROOT/'data'/'analysis_cohort_sofa_mv.csv')}
assert all(sha(Path(p))==h for p,h in before.items())
(ROOT/'qa'/'input_linkage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['saved_source_file','source_rows','matched_original_cohort','matched_test_set','id_disagreements','missing_sofa_total_cohort','missing_sofa_total_test','test_events_original_sad','test_nonevents_original_sad','sofa_label_for_figures']},ensure_ascii=True))

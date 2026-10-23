# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Frozen-risk clinical interpretation figures, with explicit outcome coverage.

Main population: held-out test set. Native model probabilities were independently
reproduced before this analysis. New strict outcomes are not the historical target.
"""
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Rectangle
from scipy.stats import norm, rankdata
import statsmodels.api as sm

ROOT = _sad_private_path("clinical_support")
DEST = _sad_private_path("clinical_support", "descriptive_analysis")
SOURCE = _sad_private_path("mimic_exports")
DEST.mkdir(parents=True, exist_ok=True)
FIG = DEST / 'figures'
FIG.mkdir(exist_ok=True)
COLORS = {'Low':'#27978B','Intermediate':'#4C78A8','High':'#D46B57'}
RISK = ['Low','Intermediate','High']
SUPPORT = ['Neither recorded','MV recorded only','Vasopressor recorded only','Both recorded']
SUPPORT_SHORT = ['Neither support recorded','Mechanical ventilation only (recorded)','Vasopressor only (recorded)','Both supports recorded']
OUTCOME = ['Post-t0 delirium recorded','Observed negative only','No valid follow-up CAM']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,
                     'svg.fonttype':'none','savefig.facecolor':'white'})

def yes(s):
    return s.astype(str).str.lower().isin(['t','true','1','1.0'])

def wilson(events, n):
    if not n:
        return (np.nan,np.nan)
    z=norm.ppf(.975)
    p=events/n
    center=(p+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return center-half, center+half

risk=pd.read_csv(_sad_private_path('eicu_validation','reference_sources','identified_frozen_risk_scores.csv'))
cohort=pd.read_csv(SOURCE/'sad_cohort.csv')
outcomes=pd.read_csv(SOURCE/'sad_outcome_summary.csv')
vent=pd.read_csv(SOURCE/'sad_ventilation_summary.csv')
vaso=pd.read_csv(SOURCE/'sad_vasoactive_summary.csv',usecols=['stay_id','agent_group','documented_active_at_t0'])
vaso=vaso[vaso.agent_group.eq('any_vasopressor')].rename(columns={'documented_active_at_t0':'vasopressor_at_t0_recorded'})
d=risk.merge(cohort[['stay_id','t0','in_manuscript','invalid_temporal_order','t0_before_icu','admission_age','pregnancy_recorded']],on='stay_id',validate='one_to_one')
d=d.merge(outcomes.drop(columns=['t0','legacy_sad_7days']),on='stay_id',validate='one_to_one')
d=d.merge(vent[['stay_id','documented_invasive_ventilation_at_t0']],on='stay_id',validate='one_to_one')
d=d.merge(vaso[['stay_id','vasopressor_at_t0_recorded']],on='stay_id',validate='one_to_one')
mv=yes(d.documented_invasive_ventilation_at_t0)
vp=yes(d.vasopressor_at_t0_recorded)
d['support_group']=np.select([mv&vp,mv&~vp,~mv&vp],['Both recorded','MV recorded only','Vasopressor recorded only'],default='Neither recorded')
d['strict_outcome_group']=np.select([d.strict_observed_sad_7days.eq(1),d.strict_observed_sad_7days.eq(0)],OUTCOME[:2],default=OUTCOME[2])
d['strict_baseline_observed_negative']=(d.strict_pre24_valid_n.gt(0)&d.strict_pre24_positive_n.eq(0)&d.any_prior_icu_positive_n.eq(0)&~yes(d.invalid_temporal_order)&~yes(d.t0_before_icu)&d.admission_age.ge(18)&~yes(d.pregnancy_recorded))
d['strict_baseline_available_by_t0']=d.strict_baseline_observed_negative & d.strict_pre24_valid_available_by_t0_n.gt(0)
d.to_csv(DEST/'linked_descriptive_cohort.csv',index=False,encoding='utf-8-sig')

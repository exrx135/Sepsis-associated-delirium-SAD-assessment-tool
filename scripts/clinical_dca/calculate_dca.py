# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Independent-test DCA with original binary SAD labels and frozen predictions.

Comparators use only ICU first-day SOFA or the model's original MV indicator.
They are fitted on the original training set; no test-set fitting or recalibration.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd

ROOT=_sad_private_path("clinical_dca")
for _folder in ["data", "results", "figures", "figure_assets", "qa", "notes"]:
    (ROOT/_folder).mkdir(parents=True, exist_ok=True)
DATA=ROOT/'data'/'analysis_cohort_sofa_mv.csv'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
d=pd.read_csv(DATA)
train=d[d.split.eq('train')].copy()
test=d[d.split.eq('test')].copy()
assert (len(train),len(test))==(11424,3571)
assert int(test.legacy_sad_7days.sum())==467
assert test.subject_id.is_unique
config={'endpoint':'original binary legacy_sad_7days',
        'frozen_model':'saved simplified 14-predictor CatBoost; probabilities unchanged',
        'primary_sofa_comparator':'SOFA only: logistic regression, 3-knot restricted cubic spline',
        'sofa_knots_training_quantiles':[0.1,0.5,0.9],
        'additional_sensitivity':'SOFA only: linear logistic regression',
        'mv_comparator':'MV only: saturated binary logistic model',
        'comparator_fit_population':'original train only, n=11424',
        'evaluation_population':'original independent test, n=3571, SAD=467',
        'primary_threshold_min':0.01,'primary_threshold_max':0.50,'threshold_step':0.005,
        'full_numeric_threshold_max':0.99,
        'threshold_examples':[0.05,0.10,0.15,0.20,0.25,0.30,0.40,0.50],
        'threshold_range_is_exploratory_not_a_validated_action_range':True,
        'paired_bootstrap_replicates':2000,'bootstrap_seed':20261021,
        'ci':'95% pointwise percentile intervals conditional on the fitted/frozen models',
        'decision':'prioritize additional assessment / preventive care; routine care for all',
        'routine_assessment_is_not_withheld_in_any_group':True}
(ROOT/'notes'/'analysis_specification.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')

def expit(z):
    z=np.clip(z,-700,700)
    return 1/(1+np.exp(-z))

def logit(p):return np.log(p/(1-p))

def fit_logistic(x,y):
    x=np.asarray(x,float);y=np.asarray(y,float)
    beta=np.zeros(x.shape[1]);beta[0]=logit(y.mean())
    for iteration in range(100):
        p=expit(x@beta)
        gradient=x.T@(p-y)
        if np.max(np.abs(gradient))<1e-8:break
        hessian=x.T@((p*(1-p))[:,None]*x)
        step=np.linalg.solve(hessian,gradient)
        old=np.logaddexp(0,x@beta).sum()-y@(x@beta)
        scale=1.0
        while scale>1e-10:
            candidate=beta-scale*step
            eta=x@candidate
            new=np.logaddexp(0,eta).sum()-y@eta
            if new<=old+1e-10:break
            scale*=.5
        beta=candidate
        if np.max(np.abs(scale*step))<1e-11:break
    p=expit(x@beta)
    g=float(np.max(np.abs(x.T@(p-y))))
    assert g<1e-5, f'Logistic fitting did not converge: {g}'
    return beta,{'iterations':iteration+1,'maximum_score_equation_residual':g}

sofa_train=train.sofa_first_day.to_numpy(float)
knots=np.quantile(sofa_train,[.1,.5,.9])
assert np.all(np.diff(knots)>0)
def rcs_term(x):
    k1,k2,k3=knots
    plus=lambda k:np.maximum(np.asarray(x)-k,0)**3
    return (plus(k1)-(k3-k1)/(k3-k2)*plus(k2)+(k2-k1)/(k3-k2)*plus(k3))/(k3-k1)**2

unscaled=np.column_stack([sofa_train,rcs_term(sofa_train)])
means=unscaled.mean(axis=0);sds=unscaled.std(axis=0)
def sofa_matrix(frame,nonlinear=True):
    x=frame.sofa_first_day.to_numpy(float)
    if nonlinear:
        return np.column_stack([np.ones(len(frame)),(np.column_stack([x,rcs_term(x)])-means)/sds])
    return np.column_stack([np.ones(len(frame)),(x-means[0])/sds[0]])

y_train=train.legacy_sad_7days.to_numpy(int)
coef_sofa,conv_sofa=fit_logistic(sofa_matrix(train),y_train)
coef_linear,conv_linear=fit_logistic(sofa_matrix(train,False),y_train)
mv_rates=train.groupby('mv_pre_diagnosis').legacy_sad_7days.mean().to_dict()
assert set(mv_rates)=={0,1} and all(0<p<1 for p in mv_rates.values())
coef_mv=[float(logit(mv_rates[0])),float(logit(mv_rates[1])-logit(mv_rates[0]))]
for frame in [train,test]:
    frame['p_model']=frame.risk_probability_frozen14
    frame['p_sofa']=expit(sofa_matrix(frame)@coef_sofa)
    frame['p_sofa_linear']=expit(sofa_matrix(frame,False)@coef_linear)
    frame['p_mv']=frame.mv_pre_diagnosis.map(mv_rates)
    assert frame[['p_model','p_sofa','p_sofa_linear','p_mv']].notna().all().all()
    assert frame[['p_model','p_sofa','p_sofa_linear','p_mv']].apply(lambda c:c.between(0,1).all()).all()

fitted={'sofa_rcs':{'knots':knots.tolist(),'basis_means':means.tolist(),'basis_sds':sds.tolist(),
                     'coefficients_standardized_basis':coef_sofa.tolist(),**conv_sofa},
        'sofa_linear':{'coefficient_intercept':float(coef_linear[0]-coef_linear[1]*means[0]/sds[0]),
                       'coefficient_per_sofa_point':float(coef_linear[1]/sds[0]),**conv_linear},
        'mv':{'coefficient_intercept':coef_mv[0],'coefficient_mv_present':coef_mv[1],
              'train_risk_mv_absent':float(mv_rates[0]),'train_risk_mv_present':float(mv_rates[1])},
        'train_only_fitting':True,'test_fit_or_recalibration_performed':False}
(ROOT/'results'/'fitted_comparators.json').write_text(json.dumps(fitted,ensure_ascii=False,indent=2),encoding='utf-8')
test.to_csv(ROOT/'data'/'test_predictions_sofa_mv.csv',index=False,encoding='utf-8-sig')
train.to_csv(ROOT/'data'/'training_comparator_predictions.csv',index=False,encoding='utf-8-sig')

y=test.legacy_sad_7days.to_numpy(int)
n=len(y)
thresholds=np.arange(2,199,dtype=float)/200
primary=thresholds<=.5+1e-12
pt=thresholds[primary]
odds=thresholds/(1-thresholds)
models=['model','sofa','mv','sofa_linear']
payoff={}
records=[]
for name in models:
    predicted=test['p_'+name].to_numpy()
    positive=predicted[:,None]>=thresholds[None,:]
    tp=(positive & y[:,None].astype(bool)).sum(axis=0)
    fp=(positive & ~y[:,None].astype(bool)).sum(axis=0)
    nb=tp/n-fp/n*odds
    payoff[name]=positive[:,primary]*(y[:,None]-(1-y[:,None])*(pt/(1-pt)))
    for i,t in enumerate(thresholds):
        records.append({'strategy':name,'threshold':float(t),'true_positive':int(tp[i]),'false_positive':int(fp[i]),
                        'false_negative':int(y.sum()-tp[i]),'true_negative':int((1-y).sum()-fp[i]),
                        'n_prioritized':int(tp[i]+fp[i]),'net_benefit':float(nb[i]),
                        'net_benefit_per_100':float(100*nb[i])})
for name in ['all','none']:
    for i,t in enumerate(thresholds):
        tp=int(y.sum()) if name=='all' else 0
        fp=int((1-y).sum()) if name=='all' else 0
        nb=tp/n-fp/n*odds[i]
        records.append({'strategy':name,'threshold':float(t),'true_positive':tp,'false_positive':fp,
                        'false_negative':int(y.sum()-tp),'true_negative':int((1-y).sum()-fp),
                        'n_prioritized':tp+fp,'net_benefit':float(nb),'net_benefit_per_100':float(100*nb)})
curves=pd.DataFrame(records)
curves.to_csv(ROOT/'results'/'decision_curves_all_thresholds.csv',index=False,encoding='utf-8-sig')
main=curves[curves.threshold.le(.5+1e-12)]
main.to_csv(ROOT/'results'/'decision_curves_primary_range.csv',index=False,encoding='utf-8-sig')

# Paired patient bootstrap: all strategies share the same resampled patients.
B=config['paired_bootstrap_replicates'];rng=np.random.default_rng(config['bootstrap_seed'])
bootstrap={name:np.empty((B,len(pt))) for name in ['sofa','mv']}
deltas={name:payoff['model']-payoff[name] for name in bootstrap}
for start in range(0,B,100):
    stop=min(start+100,B)
    # Multinomial weights are exactly equivalent to sampling patient rows with replacement.
    weights=rng.multinomial(n,np.full(n,1/n),size=stop-start).astype(float)
    for name in bootstrap:bootstrap[name][start:stop]=weights@deltas[name]/n

delta_records=[]
for name,samples in bootstrap.items():
    low,high=np.quantile(samples,[.025,.975],axis=0)
    observed=deltas[name].mean(axis=0)
    for j,t in enumerate(pt):
        delta_records.append({'comparator':name,'threshold':float(t),'delta_net_benefit':float(observed[j]),
                              'delta_net_benefit_per_100':float(100*observed[j]),
                              'ci95_low':float(low[j]),'ci95_high':float(high[j]),
                              'ci95_low_per_100':float(100*low[j]),'ci95_high_per_100':float(100*high[j])})
delta=pd.DataFrame(delta_records)
delta.to_csv(ROOT/'results'/'net_benefit_differences.csv',index=False,encoding='utf-8-sig')

def auc(y,p):
    ranks=pd.Series(p).rank(method='average').to_numpy()
    a=y.sum();b=len(y)-a
    return float((ranks[y==1].sum()-a*(a+1)/2)/(a*b))

metrics=[]
for name in models:
    p=test['p_'+name].to_numpy()
    metrics.append({'strategy':name,'test_n':n,'events':int(y.sum()),'event_fraction':float(y.mean()),
                    'auc_diagnostic_only':auc(y,p),'brier_diagnostic_only':float(np.mean((y-p)**2)),
                    'mean_predicted_probability':float(p.mean())})
pd.DataFrame(metrics).to_csv(ROOT/'results'/'diagnostic_metrics.csv',index=False,encoding='utf-8-sig')

wide=main.pivot(index='threshold',columns='strategy',values='net_benefit')
def intervals(flag):
    arr=wide.index.to_numpy()[np.asarray(flag)]
    if len(arr)==0:return []
    result=[];start=last=arr[0]
    for x in arr[1:]:
        if x-last>.0050001:result.append([float(start),float(last)]);start=x
        last=x
    result.append([float(start),float(last)])
    return result
examples=curves[np.any(np.isclose(curves.threshold.to_numpy()[:,None],np.array(config['threshold_examples'])[None,:]),axis=1)].copy()
examples.to_csv(ROOT/'results'/'threshold_examples.csv',index=False,encoding='utf-8-sig')
delta_examples=delta[np.any(np.isclose(delta.threshold.to_numpy()[:,None],np.array(config['threshold_examples'])[None,:]),axis=1)]
delta_examples.to_csv(ROOT/'results'/'difference_examples.csv',index=False,encoding='utf-8-sig')

summary={'n_original_cohort':len(d),'n_train':len(train),'n_validation_unused':int(d.split.eq('validation').sum()),
         'n_test':n,'n_test_sad':int(y.sum()),'n_test_no_sad':int((1-y).sum()),
         'source_outcome':'legacy_sad_7days, original binary outcome unchanged',
         'model_probability_sha256_source':sha(_sad_private_path('eicu_validation','reference_sources','identified_frozen_risk_scores.csv')),
         'risk_model_retrained_or_recalibrated':False,'comparators_fit_on_test':False,
         'sofa_label':'ICU first-day SOFA, as supplied; not sepsis-onset SOFA',
         'mv_definition':'Original model variable invasive_vent_12h_24h_pre_dx',
         'primary_sofa_mapping':'Training-only 3-knot restricted cubic spline logistic regression',
         'sofa_knots':knots.tolist(),
         'point_estimate_model_above_sofa_intervals':intervals(wide.model>wide.sofa),
         'point_estimate_model_above_mv_intervals':intervals(wide.model>wide.mv),
         'point_estimate_model_above_all_other_primary_strategies':intervals(wide.model>wide[['sofa','mv','all','none']].max(axis=1)),
         'diagnostic_metrics':metrics,
         'delta_examples':delta_examples.to_dict('records'),
         'pointwise_ci_not_simultaneous':True,'bootstrap_replicates':B,
         'clinical_thresholds_not_validated':True,
         'analysis_specification':config}
(ROOT/'results'/'dca_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'test_n':n,'test_sad':int(y.sum()),'test_no_sad':int((1-y).sum()),
                  'sofa_knots':knots.tolist(),'all_primary_strategies':summary['point_estimate_model_above_all_other_primary_strategies'],
                  'examples':delta_examples.to_dict('records')},ensure_ascii=True))

# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Recover native frozen CatBoost model and generate identified risk scores.

The native CBM blob is extracted using pickletools without executing pickle.
No model training, feature selection, imputation fitting, or outcome optimization.
"""
from pathlib import Path
import hashlib
import json
import math
import pickletools
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

ROOT = _sad_private_path("clinical_support")
DEST = _sad_private_path("eicu_validation", "reference_sources")
SOURCE = _sad_private_path("mimic_study")
MODEL_DIR = SOURCE / '数据建模'
PICKLE = SOURCE / '外部验证' / 'SAD_7day_SHAP_simplified_CatBoost_model.pkl'
DEST.mkdir(parents=True, exist_ok=True)

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def approximate_mode(counts, draws, rng):
    continuous = counts / counts.sum() * draws
    result = np.floor(continuous)
    need = int(draws - result.sum())
    remainder = continuous - result
    if need:
        for value in np.sort(np.unique(remainder))[::-1]:
            inds = np.where(remainder == value)[0]
            add = min(len(inds), need)
            chosen = rng.choice(inds, size=add, replace=False)
            result[chosen] += 1
            need -= add
            if need == 0:
                break
    return result.astype(int)

def split_indices(y):
    rng = np.random.RandomState(42)
    classes, yi = np.unique(y, return_inverse=True)
    counts = np.bincount(yi)
    test_n = math.ceil(len(y) * .2)
    train_n = len(y) - test_n
    ni = approximate_mode(counts, train_n, rng)
    ti = approximate_mode(counts - ni, test_n, rng)
    indices = np.split(np.argsort(yi, kind='mergesort'), np.cumsum(counts)[:-1])
    train, test = [], []
    for i in range(len(classes)):
        perm = rng.permutation(counts[i])
        order = indices[i].take(perm, mode='clip')
        train.extend(order[:ni[i]])
        test.extend(order[ni[i]:ni[i] + ti[i]])
    return rng.permutation(train), rng.permutation(test)

raw = PICKLE.read_bytes()
blobs = [arg for op, arg, pos in pickletools.genops(raw)
         if op.name in ('BINBYTES', 'SHORT_BINBYTES', 'BINBYTES8')
         and isinstance(arg, bytes) and arg.startswith(b'CBM1')]
assert len(blobs) == 1, 'Expected exactly one native CatBoost model blob'
model_path = DEST / 'frozen_simplified_14features.cbm'
model_path.write_bytes(blobs[0])
model = CatBoostClassifier()
model.load_model(str(model_path))
info_path = MODEL_DIR / 'catboost_shap_best_simplified_model_info.json'
info = json.loads(info_path.read_text(encoding='utf-8'))
features = info['selected_features']
assert model.feature_names_ == features, 'Frozen model feature names differ from 14-feature configuration'
cat_indices = model.get_cat_feature_indices()

data_path = MODEL_DIR / 'imputed_merge_data.csv'
data = pd.read_csv(data_path)
assert len(data) == 17851 and data.stay_id.is_unique
X = data[features].copy()
for i in cat_indices:
    X[features[i]] = X[features[i]].astype(str)
assert not X.isna().any().any(), 'Pre-imputed model input has unexpected missing values'
prob = model.predict_proba(X)[:, 1]
y = data.sad_7days.to_numpy()
temp, test = split_indices(y)
train_in_temp, val_in_temp = split_indices(y[temp])
train, val = temp[train_in_temp], temp[val_in_temp]
assert len(train) == 11424 and len(val) == 2856 and len(test) == 3571
assert len(set(train) & set(val)) == len(set(val) & set(test)) == len(set(test) & set(train)) == 0

old_path = MODEL_DIR / 'catboost_full_vs_simplified_test_predictions.csv'
old = pd.read_csv(old_path)
assert len(old) == len(test)
labels_equal = bool(np.array_equal(old.y_test.to_numpy(), y[test]))
diff = np.abs(old.simplified_catboost_proba.to_numpy() - prob[test])
matched = bool(labels_equal and np.all(diff <= 1e-12))
assert matched, 'Exact frozen model probabilities do not reproduce historical test output; do not claim historical linkage'

# Explicitly separate the simplified model from the old full-model risk table.
# Cutpoints depend only on validation risk distribution, with no treatment/outcome inspection.
cuts = np.quantile(prob[val], [1/3, 2/3])
split = np.repeat('train', len(data)).astype(object)
split[val] = 'validation'
split[test] = 'test'
result = data[['stay_id', 'subject_id', 'hadm_id', 'sad_7days']].copy()
result = result.rename(columns={'sad_7days': 'legacy_sad_7days'})
result['source_row_index'] = np.arange(len(data))
result['split'] = split
result['risk_probability_frozen14'] = prob
result['risk_group'] = pd.cut(prob, [-np.inf, cuts[0], cuts[1], np.inf], labels=['Low', 'Intermediate', 'High'], right=True)
result['historical_test_row_index'] = pd.Series(pd.NA, index=result.index, dtype='Int64')
result.loc[test, 'historical_test_row_index'] = np.arange(len(test))
result.to_csv(DEST / 'identified_frozen_risk_scores.csv', index=False, encoding='utf-8-sig')
cohort = pd.read_csv(_sad_private_path("mimic_exports")/'sad_cohort.csv')
check = result.merge(cohort[['stay_id','subject_id','hadm_id','in_manuscript','legacy_sad_7days']], on='stay_id', how='left', suffixes=('_model','_extract'), validate='one_to_one')
assert check.in_manuscript.eq('t').all()
assert check.subject_id_model.eq(check.subject_id_extract).all() and check.hadm_id_model.eq(check.hadm_id_extract).all()
assert check.legacy_sad_7days_model.eq(check.legacy_sad_7days_extract).all()

summary = {
    'status': 'CONFIRMED_BY_NATIVE_FROZEN_MODEL_RESCORING_AND_PROBABILITY_MATCH',
    'model': 'Frozen simplified CatBoost, 14 features',
    'pickle_executed': False,
    'new_model_trained': False,
    'input_already_imputed': True,
    'input_imputation_leakage_not_resolved_by_this_linkage': True,
    'model_feature_names': features,
    'categorical_features': [features[i] for i in cat_indices],
    'source_pickle_sha256': hashlib.sha256(raw).hexdigest(),
    'native_cbm_sha256': digest(model_path),
    'input_csv_sha256': digest(data_path),
    'historical_predictions_sha256': digest(old_path),
    'configuration_sha256': digest(info_path),
    'n': len(data), 'train_n': len(train), 'validation_n': len(val), 'test_n': len(test),
    'historical_test_labels_equal': labels_equal,
    'historical_test_probability_max_abs_error': float(diff.max()),
    'historical_test_probability_all_equal_at_1e_12': matched,
    'test_predicted_probabilities_unique': int(pd.Series(prob[test]).nunique()),
    'all_ids_joined_and_labels_matched_to_export': True,
    'risk_group_cutpoints': cuts.tolist(),
    'cutpoint_source': 'tertiles of validation-set frozen simplified-model risk; outcome-blind and treatment-blind',
    'not_the_previous_full_model_risk_grouping': True,
    'group_counts_by_split': [{str(k): (int(v) if isinstance(v,(np.integer,int)) else str(v)) for k,v in row.items()}
        for row in result.groupby(['split','risk_group'], observed=True).size().rename('n').reset_index().to_dict('records')],
    'main_descriptive_analysis_population': 'held-out test set, n=3571',
    'development_predictions_status': 'apparent in-sample risks; do not use as independent validation or claim strict OOF HTE',
}
(DEST/'risk_linkage_validation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=True, indent=2))

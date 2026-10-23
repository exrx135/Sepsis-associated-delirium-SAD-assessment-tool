# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Frozen-model scoring with prespecified reference MICE and hybrid sensitivity."""
from pathlib import Path
import os
for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]:
    os.environ[key] = "2"
import gc
import gzip
import hashlib
import json
import pickle
import time
import numpy as np
import pandas as pd
import miceforest as mf
import lightgbm
import catboost
from catboost import CatBoostClassifier
from miceforest_newdata_compat import impute_new_data_checked

BASE = _sad_private_path("eicu_validation")
BASE.mkdir(parents=True, exist_ok=True)
PROJECT = BASE.parent
STUDY = _sad_private_path("mimic_study")
EXT = _sad_private_path("eicu_mapping", "corrected_data", "patient_features_corrected.csv")
RAW = STUDY / "数据清洗后插补" / "SAD_cleaned_ordered_with_ID_chronic_updated_reordered.csv"
MODELED = STUDY / "数据建模" / "imputed_merge_data.csv"
LINK = BASE / "reference_sources"
OUT = BASE / "predictions_checked"
KERNELS = BASE / "predictions" / "reference_kernels"
KERNELS.mkdir(parents=True, exist_ok=True)
FEATURES = json.loads((STUDY / "外部验证" / "SAD_7day_SHAP_simplified_features.json").read_text(encoding="utf-8-sig"))
CATS = ["invasive_vent_12h_24h_pre_dx", "chronic_neurological"]
NCHAINS = 20
ITERATIONS = 5
SEED = 20261020


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def imputer_input(data):
    x = data[FEATURES].copy().reset_index(drop=True)
    for feature in FEATURES:
        x[feature] = pd.to_numeric(x[feature], errors="raise").astype("float64")
    for feature in CATS:
        assert x[feature].dropna().isin([0, 1]).all()
        x[feature] = pd.Categorical(x[feature], categories=[0, 1])
    return x


def model_input(data):
    x = data[FEATURES].copy()
    assert not x.isna().any().any()
    for feature in CATS:
        assert x[feature].isin([0, 1]).all()
        x[feature] = x[feature].astype("int64").astype(str)
    return x


def verify_observed(before, after):
    for feature in FEATURES:
        observed = before[feature].notna()
        a = before.loc[observed, feature].astype(float).to_numpy()
        b = after.loc[observed, feature].astype(float).to_numpy()
        assert np.array_equal(a, b), f"Changed observed {feature}"
    assert not after.isna().any().any()
    assert np.isfinite(after.astype(float).to_numpy()).all()


def main():
    started = time.time()
    OUT.mkdir(exist_ok=True)
    (OUT / "completed_inputs").mkdir(exist_ok=True)
    eicu = pd.read_csv(EXT, dtype={"uniquepid": str})
    assert eicu.patientunitstayid.is_unique and len(eicu) == 1576
    # Replace only values reconstructed from the same raw candidate lab export.
    lab_path = BASE / "lab_audit" / "lab_values_corrected.csv"
    assert lab_path.exists(), "Await reviewed lab revision reconstruction"
    labs = pd.read_csv(lab_path).set_index("patientunitstayid")
    assert labs.index.is_unique and set(labs.index) == set(eicu.patientunitstayid)
    lab_features = ["avg_po2", "avg_ptt", "avg_pt", "avg_aniongap",
                    "avg_rdw", "avg_mchc", "avg_calcium", "avg_hematocrit"]
    for feature in lab_features:
        eicu[feature] = labs.loc[eicu.patientunitstayid, feature].to_numpy()
    eicu["missing_feature_count"] = eicu[FEATURES].isna().sum(axis=1)
    eicu["observed_feature_count"] = 14 - eicu.missing_feature_count
    eicu["missing_features"] = eicu[FEATURES].apply(
        lambda row: "{" + ",".join(sorted(row.index[row.isna()])) + "}", axis=1)
    eicu["processing_status"] = "LAB_REVISIONS_CORRECTED_UNIMPUTED"
    eicu.to_csv(OUT / "patient_features_lab_reviewed_unimputed.csv", index=False)
    strict = eicu.eligible_strict.eq("t")
    missing = eicu.loc[strict, FEATURES].isna().mean()
    high = [f for f in FEATURES if missing[f] > .30 and f not in CATS]
    targets = [f for f in FEATURES if eicu[f].isna().any()]
    assert len(FEATURES) == 14
    assert set(high) == {"avg_po2", "avg_ptt", "avg_pt", "avg_aniongap"}
    raw = pd.read_csv(RAW)
    modeled = pd.read_csv(MODELED)
    link = pd.read_csv(LINK / "identified_frozen_risk_scores.csv")
    assert raw.stay_id.is_unique and modeled.stay_id.is_unique and link.stay_id.is_unique
    assert raw.stay_id.tolist() == modeled.stay_id.tolist() == link.stay_id.tolist()
    assert np.array_equal(link.source_row_index.to_numpy(), np.arange(len(link)))
    # Protect observed source values and ensure the training identifiers are those
    # from the already verified original split, not a new split using eICU labels.
    reference_roundtrip_errors = {}
    for f in FEATURES:
        obs = raw[f].notna()
        a, b = raw.loc[obs, f].to_numpy(float), modeled.loc[obs, f].to_numpy(float)
        # Historical CSVs round means to different decimal precision.
        reference_roundtrip_errors[f] = float(np.max(np.abs(a-b)))
        assert np.allclose(a, b, rtol=1e-8, atol=1e-8), f"Changed observed MIMIC {f}"
    train_mask = link.split.eq("train")
    assert train_mask.sum() == 11424
    reference = imputer_input(raw.loc[train_mask])
    ext_input = imputer_input(eicu)
    means = {f: float(reference[f].mean()) for f in high}
    hybrid = ext_input.copy()
    for f in high:
        hybrid[f] = hybrid[f].fillna(means[f])
    model = CatBoostClassifier()
    model_path = LINK / "frozen_simplified_14features.cbm"
    model.load_model(str(model_path))
    assert model.feature_names_ == FEATURES
    assert [FEATURES[i] for i in model.get_cat_feature_indices()] == CATS
    linkage_report = json.loads((LINK / "risk_linkage_validation.json").read_text(encoding="utf-8"))
    assert digest(model_path) == linkage_report["native_cbm_sha256"]
    assert linkage_report["historical_test_probability_all_equal_at_1e_12"]
    hashes = {str(p): digest(p) for p in [EXT, RAW, MODELED, model_path, lab_path,
                                        LINK / "identified_frozen_risk_scores.csv"]}
    metadata = {
        "model_frozen": True, "model_features": FEATURES,
        "imputer_reference": "Original MIMIC training split, raw observed values, n11424",
        "reference_rows": len(reference), "external_rows": len(eicu),
        "imputation_targets": targets, "num_independent_chains": NCHAINS,
        "iterations": ITERATIONS, "mean_match_candidates": 5,
        "base_seed": SEED, "threads": 2, "high_missing_mean_features": high,
        "training_observed_means": means,
        "strict_missing_rates_before_imputation": missing.to_dict(),
        "source_sha256": hashes,
        "historical_csv_roundtrip_max_absolute_difference": reference_roundtrip_errors,
        "packages": {"miceforest": mf.__version__, "lightgbm": lightgbm.__version__,
                     "catboost": catboost.__version__, "numpy": np.__version__, "pandas": pd.__version__},
        "outcomes_in_imputer": False,
        "eicu_fitted_models": False,
        "original_fitted_imputer_reused": False,
        "original_method_reconstructed": "Same miceforest/MICE family and five iterations;14 predictors only, reconstructed on training subset, no future LOS or outcomes.",
        "full_database_alias_audit": "Pending unless separately marked complete in lab_audit",
        "prediction_aggregation": "Average frozen-model probabilities across20 independently seeded completed datasets",
        "newdata_iteration_counter_repair": "Local adapter advances new-data iteration_tab; no installed package or trained kernel altered. Each completion explicitly requests iteration5.",
        "supersedes": "predictions and results generated before iteration counter quality-control repair; those outputs are invalid for reporting.",
        "reference_kernels": str(KERNELS),
    }
    (OUT / "imputation_specification.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    pd.DataFrame({"feature": FEATURES, "strict_missing_n": eicu.loc[strict, FEATURES].isna().sum(),
                  "strict_missing_pct": missing*100}).to_csv(OUT / "missingness_before_imputation.csv", index=False)
    print(json.dumps({"reference_n": len(reference), "external_n": len(eicu), "targets": targets,
                      "high_missing_mean_features": high, "means": means}, ensure_ascii=False), flush=True)
    id_fields = [f for f in eicu.columns if f not in FEATURES]
    predictions = eicu[id_fields].copy()
    distribution_rows, convergence_rows = [], []
    primary_probs, hybrid_probs = [], []
    for chain in range(NCHAINS):
        chain_start = time.time()
        seed = SEED + chain * 1009
        kernel_path = KERNELS / f"reference_chain_{chain+1:02d}.pkl.gz"
        if kernel_path.exists():
            # These kernels were trained correctly before the new-data bug was found.
            with gzip.open(kernel_path, "rb") as stream:
                kernel = pickle.load(stream)
            assert list(kernel.column_names) == FEATURES and kernel.iteration_count() == ITERATIONS
        else:
            KERNELS.mkdir(exist_ok=True)
            kernel = mf.ImputationKernel(reference, num_datasets=1,
                        variable_schema=targets, mean_match_candidates=5,
                        save_all_iterations_data=True, random_state=seed)
            kernel.mice(iterations=ITERATIONS, num_threads=2, verbosity=-1,
                        deterministic=True, force_col_wise=True)
            with gzip.open(kernel_path, "wb") as stream:
                pickle.dump(kernel, stream, protocol=5)
        record_seeds = ((eicu.patientunitstayid.to_numpy(dtype="uint64") * 2654435761 + seed)
                        % (2**32 - 1)).astype("uint32")
        for method, x in [("mice", ext_input), ("hybrid", hybrid)]:
            completed = impute_new_data_checked(kernel, x, iterations=ITERATIONS,
                    random_state=seed+1, random_seed_array=record_seeds,
                    save_all_iterations_data=True, verbose=False)
            full = completed.complete_data(dataset=0, iteration=ITERATIONS)
            verify_observed(ext_input, full)
            mx = model_input(full)
            probability = model.predict_proba(mx, thread_count=2)[:, 1]
            assert np.isfinite(probability).all() and ((probability >= 0) & (probability <= 1)).all()
            predictions[f"{method}_chain_{chain+1:02d}"] = probability
            (primary_probs if method == "mice" else hybrid_probs).append(probability)
            saved = full.copy()
            saved.insert(0, "patientunitstayid", eicu.patientunitstayid.to_numpy())
            saved.to_csv(OUT / "completed_inputs" / f"{method}_{chain+1:02d}.csv", index=False)
            for feature in targets:
                was_missing = ext_input[feature].isna().to_numpy() & strict.to_numpy()
                values = full.loc[was_missing, feature].astype(float)
                distribution_rows.append({"method": method, "chain": chain+1, "feature": feature,
                    "n": len(values), "mean": values.mean(), "sd": values.std(),
                    "min": values.min(), "median": values.median(), "max": values.max()})
            for iteration in range(1, ITERATIONS+1):
                iteration_data = completed.complete_data(dataset=0, iteration=iteration)
                for feature in targets:
                    mask = ext_input[feature].isna().to_numpy() & strict.to_numpy()
                    values = iteration_data.loc[mask, feature].astype(float)
                    convergence_rows.append({"method": method, "chain": chain+1, "iteration": iteration,
                                             "feature": feature, "mean": values.mean(), "sd": values.std()})
            del completed, full, mx, saved
        del kernel
        gc.collect()
        print(f"Chain {chain+1}/{NCHAINS} finished; {time.time()-chain_start:.1f}s, elapsed {time.time()-started:.1f}s", flush=True)
    predictions["probability_mice"] = np.mean(primary_probs, axis=0)
    predictions["probability_hybrid"] = np.mean(hybrid_probs, axis=0)
    predictions["probability_mice_chain_sd"] = np.std(primary_probs, axis=0, ddof=1)
    predictions["probability_hybrid_chain_sd"] = np.std(hybrid_probs, axis=0, ddof=1)
    assert np.max(predictions.probability_mice_chain_sd) > 1e-6, "Independent imputations have collapsed"
    assert np.max(predictions.probability_hybrid_chain_sd) > 1e-6, "Independent hybrid imputations have collapsed"
    predictions.to_csv(OUT / "external_predictions.csv", index=False)
    pd.DataFrame(distribution_rows).to_csv(OUT / "imputed_value_distributions.csv", index=False)
    pd.DataFrame(convergence_rows).to_csv(OUT / "imputation_iteration_diagnostics.csv", index=False)
    assert hashes == {path: digest(path) for path in hashes}
    metadata.update({"completed": True, "elapsed_seconds": time.time()-started,
                     "all_observed_values_preserved": True, "source_files_unchanged": True,
                     "missing_after_imputation": 0,
                     "prediction_output_sha256": digest(OUT / "external_predictions.csv")})
    (OUT / "imputation_completion.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("IMPUTATION_AND_FROZEN_PREDICTION_COMPLETE", flush=True)


if __name__ == "__main__":
    main()

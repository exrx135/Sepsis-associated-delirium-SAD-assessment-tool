# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Requested post hoc patient-exclusion sensitivities of the frozen 14-feature model."""
from pathlib import Path
import os
for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]:
    os.environ[key] = "2"
import hashlib
import json
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from evaluate_external import metric_row, bootstrap, dca, calibration_bins, roc, auc

BASE = _sad_private_path("eicu_validation")
BASE.mkdir(parents=True, exist_ok=True)
PRED = BASE / "predictions_checked"
OUT = BASE / "missingness_exclusion_results_20261021"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_model_input(frame, features, cats):
    data = frame.loc[:, features].copy()
    assert not data.isna().any().any()
    assert np.isfinite(data.to_numpy(float)).all()
    for feature in cats:
        assert data[feature].isin([0, 1]).all()
        data[feature] = data[feature].astype("int64").astype(str)
    return data


def contiguous_ranges(curve):
    positions = np.flatnonzero(curve.better_than_both.to_numpy())
    if not len(positions):
        return []
    blocks = np.split(positions, np.flatnonzero(np.diff(positions) > 1) + 1)
    return [[round(float(curve.threshold.iloc[b[0]]), 2),
             round(float(curve.threshold.iloc[b[-1]]), 2)] for b in blocks]


def main():
    OUT.mkdir(exist_ok=True)
    spec_path = PRED / "imputation_specification.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    features = spec["model_features"]
    assert len(features) == 14
    paths = [PRED / "patient_features_lab_reviewed_unimputed.csv",
             PRED / "external_predictions.csv",
             BASE / "reference_sources" / "frozen_simplified_14features.cbm", spec_path]
    hashes = {str(p): digest(p) for p in paths}
    raw = pd.read_csv(paths[0], dtype={"uniquepid": str}).set_index("patientunitstayid")
    predictions = pd.read_csv(paths[1], dtype={"uniquepid": str}).set_index("patientunitstayid")
    assert raw.index.is_unique and predictions.index.is_unique
    assert set(raw.index) == set(predictions.index)
    predictions = predictions.loc[raw.index]
    for field in ["uniquepid", "eligible_strict", "sad_strict"]:
        pd.testing.assert_series_equal(raw[field], predictions[field])
    strict = raw.loc[raw.eligible_strict.eq("t")].copy()
    assert len(strict) == 1323
    # Recompute from all 14 corrected, pre-imputation feature columns.
    missing = strict[features].isna().sum(axis=1)
    assert np.array_equal(missing, strict.missing_feature_count)
    scheme_definitions = [
        ("exclude_missing_gt30", "Exclude >=5/14 missing; MICE", missing.le(4), "#2166ac"),
        ("complete_case", "Complete cases; no imputation", missing.eq(0), "#b2182b"),
    ]
    model = CatBoostClassifier()
    model.load_model(str(paths[2]))
    assert model.feature_names_ == features
    cats = [features[i] for i in model.get_cat_feature_indices()]
    retained_ids = strict.index[missing.le(4)]
    scores = []
    chain_checks = []
    # The existing MICE transformations use fixed MIMIC reference donors and
    # record-specific seeds. Selecting patients does not refit an eICU imputer.
    for chain in range(1, 21):
        matrix_path = PRED / "completed_inputs" / f"mice_{chain:02d}.csv"
        matrix = pd.read_csv(matrix_path).set_index("patientunitstayid").loc[retained_ids]
        observed = strict.loc[retained_ids, features].notna()
        before = strict.loc[retained_ids, features].to_numpy(float)
        after = matrix[features].to_numpy(float)
        assert np.array_equal(before[observed], after[observed])
        probability = model.predict_proba(as_model_input(matrix, features, cats), thread_count=2)[:, 1]
        previous = predictions.loc[retained_ids, f"mice_chain_{chain:02d}"].to_numpy(float)
        assert np.allclose(probability, previous, rtol=0, atol=1e-12)
        scores.append(probability)
        chain_checks.append({"chain": chain, "input_sha256": digest(matrix_path),
                             "max_probability_difference": float(np.max(np.abs(probability - previous)))})
    ensemble = pd.Series(np.mean(scores, axis=0), index=retained_ids)
    complete_ids = strict.index[missing.eq(0)]
    complete_prob = model.predict_proba(
        as_model_input(strict.loc[complete_ids], features, cats), thread_count=2)[:, 1]
    assert np.allclose(ensemble.loc[complete_ids], complete_prob, rtol=0, atol=1e-12)
    metrics, dc_rows, bins_rows, predictions_rows, per_chain = [], [], [], [], []
    plots = []
    for name, title, keep, color in scheme_definitions:
        sub = strict.loc[keep]
        y = sub.sad_strict.to_numpy(int)
        assert set(y) == {0, 1}
        p = ensemble.loc[sub.index].to_numpy() if name == "exclude_missing_gt30" else complete_prob
        row = {
            "scheme": name, "source_n": len(strict), "excluded_n": int((~keep).sum()),
            "hospitals": int(sub.hospitalid.nunique()),
            **metric_row(y, p), **bootstrap(y, p, sub.uniquepid.to_numpy()),
        }
        metrics.append(row)
        curve = dca(y, p).assign(scheme=name)
        dc_rows.append(curve)
        bins = calibration_bins(y, p).assign(scheme=name)
        bins_rows.append(bins)
        predictions_rows.append(pd.DataFrame({
            "patientunitstayid": sub.index, "uniquepid": sub.uniquepid.to_numpy(),
            "hospitalid": sub.hospitalid.to_numpy(), "scheme": name,
            "missing_count_before_imputation": missing.loc[sub.index].to_numpy(),
            "outcome": y, "probability": p,
        }))
        for chain in range(1, 21):
            pp = predictions.loc[sub.index, f"mice_chain_{chain:02d}"].to_numpy(float)
            per_chain.append({"scheme": name, "chain": chain, "auroc": auc(y, pp)})
        plots.append((title, color, row, y, p, curve, bins))
    metric_df = pd.DataFrame(metrics)
    metric_df.to_csv(OUT / "metrics.csv", index=False, encoding="utf-8-sig")
    pd.concat(dc_rows).to_csv(OUT / "dca.csv", index=False)
    pd.concat(bins_rows).to_csv(OUT / "calibration_deciles.csv", index=False)
    pd.concat(predictions_rows).to_csv(OUT / "predictions.csv", index=False)
    pd.DataFrame(per_chain).to_csv(OUT / "per_imputation_auroc.csv", index=False)
    missing.value_counts().sort_index().rename_axis("missing_count").to_csv(OUT / "missing_count_distribution.csv")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 3, figsize=(14, 8.4))
    for i, (title, color, row, y, p, curve, bins) in enumerate(plots):
        fpr, tpr = roc(y, p)
        axes[i, 0].plot(fpr, tpr, color=color, lw=2,
                       label=f"AUC {row['auroc']:.3f}\n95% CI {row['auroc_ci_low']:.3f}–{row['auroc_ci_high']:.3f}")
        axes[i, 0].plot([0, 1], [0, 1], "--", color=".65")
        axes[i, 0].set(title=f"{title}\nn={row['n']}, events={row['events']}",
                       xlabel="False positive rate", ylabel="True positive rate", xlim=(0, 1), ylim=(0, 1))
        axes[i, 0].legend(loc="lower right", frameon=False)
        axes[i, 1].plot(bins.predicted, bins.observed, "o-", color=color)
        axes[i, 1].plot([0, 1], [0, 1], "--", color=".65")
        axes[i, 1].set(title=f"Calibration; slope {row['calibration_slope']:.2f}",
                       xlabel="Mean predicted probability", ylabel="Observed event rate", xlim=(0, 1), ylim=(0, 1))
        plotted = curve[curve.threshold.le(.5)]
        axes[i, 2].plot(plotted.threshold, plotted.net_benefit, color=color, lw=2, label="Frozen model")
        axes[i, 2].plot(plotted.threshold, plotted.treat_all, "--", color=".5", label="Act for all")
        axes[i, 2].axhline(0, color=".2", lw=1, label="Act for none")
        axes[i, 2].set(title="Decision curve", xlabel="Threshold probability",
                       ylabel="Net benefit", xlim=(.01, .5), ylim=(-.06, max(.23, y.mean() + .04)))
        axes[i, 2].legend(frameon=False, fontsize=9)
    fig.suptitle("eICU · frozen 14-feature CatBoost · requested exclusion sensitivities", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, .96))
    fig.savefig(OUT / "roc_calibration_dca.png", dpi=200)
    fig.savefig(OUT / "roc_calibration_dca.pdf")
    plt.close(fig)
    meta = {
        "completed": True, "date": "2026-10-21",
        "analysis_type": "Post hoc user-requested sensitivity analysis; original primary result retained.",
        "cohort": "Original strict primary cohort, n1323",
        "scheme1": "Exclude patients with >=5 of the 14 predictors missing (>30%); retain <=4 missing.",
        "scheme2": "Exclude patients with any of the 14 predictors missing.",
        "missingness_source": "Corrected observed inputs, before imputation; unrecorded chronic neurological history already coded zero under the existing rule.",
        "imputation": "Reuse the verified 20 fixed MIMIC-reference MICE completed inputs, preserving per-record seeds. Re-scored all retained inputs with the frozen model. No eICU fitting or mean filling.",
        "complete_case_verification": "Direct raw-input scoring equals every chain and averaged probability within 1e-12.",
        "uncertainty": "2000 patient-cluster bootstrap replicates; conditional on fixed imputation ensemble.",
        "source_sha256": hashes, "chain_checks": chain_checks,
        "sources_unchanged": all(digest(Path(p)) == h for p, h in hashes.items()),
        "dca_better_than_both_grid_ranges": {
            name: contiguous_ranges(curve) for (name, _, _, _), curve in zip(scheme_definitions, dc_rows)
        },
    }
    assert meta["sources_unchanged"]
    (OUT / "analysis_record.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    lines = ["eICU患者缺失排除方案结果", ""]
    for row in metrics:
        label = "方案1：排除至少缺5/14项的入住，其余参考MICE" if row["scheme"] == "exclude_missing_gt30" else "方案2：仅保留14项全部完整的入住"
        lines.extend([label, f"纳入{row['n']}次入住，排除{row['excluded_n']}次；事件{row['events']}例，医院{row['hospitals']}家。",
                      f"AUROC {row['auroc']:.3f}（95% CI {row['auroc_ci_low']:.3f}–{row['auroc_ci_high']:.3f}）；"
                      f"AUPRC {row['auprc']:.3f}；Brier {row['brier']:.4f}；校准斜率 {row['calibration_slope']:.3f}。", ""])
    lines += ["原主分析保留：1323次入住、245个事件；参考MICE AUROC 0.641（0.601–0.679）。",
              "本次为事后敏感性分析；筛选后人群改变，性能差异不等同于模型本身改善。",
              "ROC、校准与DCA见同目录PNG/PDF。"]
    (OUT / "结果.txt").write_text("\n".join(lines), encoding="utf-8-sig")
    print(metric_df.to_string(index=False), flush=True)
    print(json.dumps(meta["dca_better_than_both_grid_ranges"]), flush=True)


if __name__ == "__main__":
    main()

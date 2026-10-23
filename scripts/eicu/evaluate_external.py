# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Evaluate fixed predictions. No predictor selection, tuning or recalibration."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.optimize import minimize, brentq
from scipy.stats import rankdata
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = _sad_private_path("eicu_validation")
BASE.mkdir(parents=True, exist_ok=True)
OUT = BASE / "results_checked"
SEED = 20261020


def auc(y, p):
    y = np.asarray(y, dtype=int)
    n1 = y.sum()
    n0 = len(y) - n1
    if not n1 or not n0:
        return np.nan
    return float((rankdata(p)[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def roc(y, p):
    order = np.argsort(-p, kind="mergesort")
    yy, pp = np.asarray(y)[order], np.asarray(p)[order]
    ends = np.r_[np.flatnonzero(np.diff(pp)), len(pp) - 1]
    tp = np.cumsum(yy)[ends]
    fp = 1 + ends - tp
    return np.r_[0, fp / (len(yy) - yy.sum())], np.r_[0, tp / yy.sum()]


def average_precision(y, p):
    order = np.argsort(-p, kind="mergesort")
    yy, pp = np.asarray(y)[order], np.asarray(p)[order]
    ends = np.r_[np.flatnonzero(np.diff(pp)), len(pp) - 1]
    tp = np.cumsum(yy)[ends]
    precision = tp / (ends + 1)
    recall = tp / yy.sum()
    return float(np.sum(np.diff(np.r_[0, recall]) * precision))


def calibration(y, p):
    z = logit(np.clip(p, 1e-7, 1 - 1e-7))
    citl = brentq(lambda a: np.sum(expit(a + z) - y), -30, 30)
    def loss(ab):
        eta = ab[0] + ab[1] * z
        return np.sum(np.logaddexp(0, eta) - y * eta)
    def grad(ab):
        residual = expit(ab[0] + ab[1] * z) - y
        return np.array([residual.sum(), residual @ z])
    fit = minimize(loss, np.array([0., 1.]), jac=grad, method="BFGS",
                   options={"gtol": 1e-6, "maxiter": 1000})
    # BFGS may report precision loss with a numerically converged optimum.
    assert np.linalg.norm(grad(fit.x)) < 1e-3, "Calibration assessment did not converge"
    return float(citl), float(fit.x[0]), float(fit.x[1])


def metric_row(y, p):
    intercept, joint_intercept, slope = calibration(y, p)
    return {
        "n": len(y), "events": int(y.sum()), "event_rate": float(y.mean()),
        "auroc": auc(y, p), "auprc": average_precision(y, p),
        "brier": float(np.mean((p - y) ** 2)),
        "mean_predicted_probability": float(p.mean()),
        "observed_expected_ratio": float(y.sum() / p.sum()),
        "calibration_intercept_offset": intercept,
        "calibration_joint_intercept": joint_intercept,
        "calibration_slope": slope,
    }


def bootstrap(y, p, clusters, iterations=2000):
    # Resample people, preserving all of each sampled person's ICU stays.
    ids, inv = np.unique(np.asarray(clusters, str), return_inverse=True)
    groups = [np.flatnonzero(inv == i) for i in range(len(ids))]
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(iterations):
        sampled = np.concatenate([groups[i] for i in rng.integers(0, len(ids), len(ids))])
        yy, pp = y[sampled], p[sampled]
        if yy.sum() in (0, len(yy)):
            continue
        vals.append([auc(yy, pp), average_precision(yy, pp), np.mean((pp - yy) ** 2)])
    vals = np.asarray(vals)
    result = {"bootstrap_valid_replicates": len(vals), "bootstrap_clusters": len(ids)}
    for j, key in enumerate(["auroc", "auprc", "brier"]):
        result[key + "_ci_low"], result[key + "_ci_high"] = map(float, np.quantile(vals[:, j], [.025, .975]))
    return result


def dca(y, p):
    thresholds = np.arange(.01, .801, .01)
    rows = []
    for t in thresholds:
        selected = p >= t
        tp = np.sum(selected & (y == 1))
        fp = np.sum(selected & (y == 0))
        nb = (tp - fp * t / (1 - t)) / len(y)
        all_nb = y.mean() - (1 - y.mean()) * t / (1 - t)
        rows.append({"threshold": t, "net_benefit": nb, "treat_all": all_nb,
                     "treat_none": 0., "true_positives": int(tp), "false_positives": int(fp),
                     "better_than_both": bool(nb > max(0., all_nb))})
    return pd.DataFrame(rows)


def calibration_bins(y, p):
    # Fixed equal-count risk groups for visualization, not thresholds for action.
    ordered = np.argsort(p, kind="mergesort")
    records = []
    for i, idx in enumerate(np.array_split(ordered, 10)):
        n = len(idx)
        q = y[idx].mean()
        denom = 1 + 1.96 ** 2 / n
        center = (q + 1.96 ** 2 / (2*n)) / denom
        margin = 1.96 * np.sqrt(q*(1-q)/n + 1.96**2/(4*n*n)) / denom
        records.append({"bin": i+1, "n": n, "events": int(y[idx].sum()),
                        "predicted": p[idx].mean(), "observed": q,
                        "wilson_low": center-margin, "wilson_high": center+margin})
    return pd.DataFrame(records)


def main():
    OUT.mkdir(exist_ok=True)
    data = pd.read_csv(BASE / "predictions_checked" / "external_predictions.csv", dtype={"uniquepid": str})
    assert data.patientunitstayid.is_unique
    assert data.uniquepid.notna().all() and data.uniquepid.str.strip().ne("").all()
    for method in ["mice", "hybrid"]:
        chain_cols = [c for c in data.columns if c.startswith(method+"_chain_")]
        assert len(chain_cols) == 20
        assert np.isfinite(data[chain_cols].to_numpy(float)).all()
        assert np.allclose(data[chain_cols].mean(axis=1), data["probability_"+method],
                           rtol=1e-12, atol=1e-12)
    metrics, chain_metrics, dca_rows, cal_rows = [], [], [], []
    methods = [("mice", "Reference MICE", "#2166ac"),
               ("hybrid", ">30% mean + MICE", "#d6604d")]
    for cohort in ["strict", "allow_missing_rass", "baseline_negative"]:
        sub = data[data["eligible_" + cohort].eq("t")].copy()
        y = sub["sad_" + cohort].to_numpy(dtype=int)
        assert set(y) == {0, 1}
        for method, label, color in methods:
            p = sub["probability_" + method].to_numpy(float)
            assert np.isfinite(p).all() and ((0 <= p) & (p <= 1)).all()
            row = {"cohort": cohort, "method": method, **metric_row(y, p),
                   **bootstrap(y, p, sub.uniquepid.to_numpy())}
            metrics.append(row)
            curve = dca(y, p).assign(cohort=cohort, method=method)
            dca_rows.append(curve)
            cal_rows.append(calibration_bins(y, p).assign(cohort=cohort, method=method))
            for col in sub.columns:
                if col.startswith(method + "_chain_"):
                    pp = sub[col].to_numpy(float)
                    chain_metrics.append({"cohort": cohort, "method": method, "chain": col,
                                          "auroc": auc(y, pp), "auprc": average_precision(y, pp),
                                          "brier": np.mean((pp-y)**2)})
        print(f"Evaluated {cohort}: {len(sub)} stays, {y.sum()} events", flush=True)
    metric_df = pd.DataFrame(metrics)
    metric_df.to_csv(OUT / "external_validation_metrics.csv", index=False)
    pd.DataFrame(chain_metrics).to_csv(OUT / "per_imputation_metrics.csv", index=False)
    dca_df = pd.concat(dca_rows, ignore_index=True)
    dca_df.to_csv(OUT / "decision_curve_data.csv", index=False)
    cal_df = pd.concat(cal_rows, ignore_index=True)
    cal_df.to_csv(OUT / "calibration_deciles.csv", index=False)
    strict = data[data.eligible_strict.eq("t")]
    y = strict.sad_strict.to_numpy(int)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    for method, label, color in methods:
        p = strict["probability_"+method].to_numpy(float)
        row = metric_df[(metric_df.cohort == "strict") & (metric_df.method == method)].iloc[0]
        fpr, tpr = roc(y, p)
        axes[0].plot(fpr, tpr, color=color, lw=2,
                     label=f"{label}\nAUC {row.auroc:.3f} ({row.auroc_ci_low:.3f}–{row.auroc_ci_high:.3f})")
        bins = cal_df[(cal_df.cohort == "strict") & (cal_df.method == method)]
        axes[1].plot(bins.predicted, bins.observed, "o-", color=color, lw=1.5, ms=4, label=label)
        dc = dca_df[(dca_df.cohort == "strict") & (dca_df.method == method) & (dca_df.threshold <= .5)]
        axes[2].plot(dc.threshold, dc.net_benefit, lw=2, color=color, label=label)
    axes[0].plot([0,1], [0,1], "--", color=".6", lw=1)
    axes[0].set(xlabel="False positive rate", ylabel="True positive rate",
                title="A  Discrimination", xlim=(0,1), ylim=(0,1))
    axes[0].legend(fontsize=8, loc="lower right", frameon=False)
    axes[1].plot([0,1], [0,1], "--", color=".6", lw=1)
    axes[1].set(xlabel="Mean predicted probability", ylabel="Observed event rate",
                title="B  Calibration (risk deciles)", xlim=(0,1), ylim=(0,1))
    axes[1].legend(fontsize=8, frameon=False)
    axes[2].plot(dc.threshold, dc.treat_all, "--", color=".5", lw=1.4, label="Act for all")
    axes[2].axhline(0, color=".2", lw=1, label="Act for none")
    axes[2].set(xlabel="Threshold probability", ylabel="Net benefit",
                title="C  Decision curve", xlim=(.01,.5), ylim=(-.06, max(.23, y.mean()+.04)))
    axes[2].legend(fontsize=8, frameon=False)
    fig.suptitle(f"eICU external evaluation · frozen 14-feature CatBoost · n={len(y)}, events={y.sum()}",
                 fontsize=12)
    fig.tight_layout(rect=(0,0,1,.94))
    fig.savefig(OUT / "external_validation_roc_calibration_dca.png", dpi=220)
    fig.savefig(OUT / "external_validation_roc_calibration_dca.pdf")
    plt.close(fig)
    summary = {
        "status": "Evaluation of mapped exported data; cohort-window full-name lab/customlab audit status is recorded in the current lab report and final_checks.json.",
        "metrics": metrics,
        "uncertainty": "Patient-cluster bootstrap,2000 samples; conditional on fixed reference kernels and averaged probabilities. Across-chain metrics separately supplied, not Rubin-pooled CIs.",
        "calibration": "Assessment only; predictions never recalibrated on eICU.",
        "dca": "Fixed threshold grid, exploratory decision support analysis; no proven treatment benefit, cost or clinical intervention threshold.",
        "method_selection": "Primary and sensitivity fixed before performance, all results retained.",
    }
    (OUT / "evaluation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(metric_df.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()

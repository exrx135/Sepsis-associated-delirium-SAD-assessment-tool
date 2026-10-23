# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Publication figure for the original strict-cohort reference-MICE evaluation."""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import os
import tempfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FormatStrFormatter
from evaluate_external import auc, roc, dca, calibration_bins

BASE = _sad_private_path("eicu_validation")
BASE.mkdir(parents=True, exist_ok=True)
OUT = BASE / "补充图_原方案外部验证"
NAME = "Figure_S6"
STYLE_SOURCE = _sad_private_path("mimic_study", "数据建模", "SAD_7day-0603-Copy1.ipynb")
STYLE_FIGURE = _sad_private_path("reference_figures", "calibration_curves.tiff")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def uniform_calibration(y, p):
    """Match original sklearn calibration_curve(..., n_bins=10), default uniform."""
    edges = np.linspace(0, 1, 11)
    groups = np.searchsorted(edges[1:-1], p)
    records = []
    for i in range(10):
        keep = groups == i
        n = int(keep.sum())
        records.append({
            "bin": i + 1, "lower": float(edges[i]), "upper": float(edges[i + 1]),
            "n": n, "events": int(y[keep].sum()),
            "predicted": float(p[keep].mean()) if n else np.nan,
            "observed": float(y[keep].mean()) if n else np.nan,
        })
    result = pd.DataFrame(records)
    assert result.n.sum() == len(y) and result.events.sum() == y.sum()
    assert np.isclose((result.predicted * result.n).sum() / len(y), p.mean())
    return result


def main():
    OUT.mkdir(exist_ok=True)
    paths = {
        "predictions": BASE / "predictions_checked" / "external_predictions.csv",
        "metrics": BASE / "results_checked" / "external_validation_metrics.csv",
        "calibration": BASE / "results_checked" / "calibration_deciles.csv",
        "dca": BASE / "results_checked" / "decision_curve_data.csv",
    }
    source_hashes = {k: digest(p) for k, p in paths.items()}
    data = pd.read_csv(paths["predictions"])
    data = data.loc[data.eligible_strict.eq("t")]
    y = data.sad_strict.to_numpy(int)
    p = data.probability_mice.to_numpy(float)
    assert len(y) == 1323 and y.sum() == 245 and data.patientunitstayid.is_unique
    metrics = pd.read_csv(paths["metrics"])
    metrics = metrics.loc[metrics.cohort.eq("strict") & metrics.method.eq("mice")].iloc[0]
    bins = pd.read_csv(paths["calibration"])
    bins = bins.loc[bins.cohort.eq("strict") & bins.method.eq("mice")].reset_index(drop=True)
    dc = pd.read_csv(paths["dca"])
    dc = dc.loc[dc.cohort.eq("strict") & dc.method.eq("mice")].reset_index(drop=True)
    assert abs(auc(y, p) - metrics.auroc) < 1e-12
    recalc_bins = calibration_bins(y, p)
    for column in recalc_bins:
        assert np.allclose(bins[column], recalc_bins[column], atol=1e-12, rtol=0)
    recalc_dc = dca(y, p)
    for column in recalc_dc:
        assert np.allclose(dc[column], recalc_dc[column], atol=1e-12, rtol=0)
    uniform_bins = uniform_calibration(y, p)
    displayed_bins = uniform_bins.loc[uniform_bins.n.gt(0)]
    reference_notebook = json.loads(STYLE_SOURCE.read_text(encoding="utf-8"))
    reference_cell = "".join(reference_notebook["cells"][9]["source"])
    assert "calibration_curve(y_test, model_probas[model_name], n_bins=10)" in reference_cell
    assert "plt.plot(prob_pred, prob_true, 's-'" in reference_cell
    assert "'#00468B'" in reference_cell and "Times New Roman" in reference_cell
    plt.rcParams.update({
        "font.family": "Times New Roman", "font.size": 8,
        "axes.titlesize": 9, "axes.labelsize": 8,
        "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
        "legend.fontsize": 7, "axes.linewidth": .8, "axes.edgecolor": "#444444",
        "axes.spines.top": True, "axes.spines.right": True,
        "axes.axisbelow": True,
        "xtick.major.width": .6, "ytick.major.width": .6,
        "xtick.major.size": 3, "ytick.major.size": 3,
        "svg.fonttype": "none", "svg.hashsalt": "sad-eicu-original-supplementary",
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })
    blue = "#00468B"
    gray = "#4D4D4D"
    fig, axes = plt.subplots(1, 3, figsize=(7.5, 3.1))
    fig.subplots_adjust(left=.066, right=.985, bottom=.18, top=.75, wspace=.42)
    fig.suptitle("Supplementary Figure. External validation in eICU",
                 x=.5, y=.975, fontsize=10, fontweight="bold")
    fig.text(.5, .89, "Original analysis: 1,323 ICU stays, 245 SAD events; reference MICE",
             ha="center", va="center", fontsize=8, color="#444444")
    for ax, letter, title in zip(axes, "ABC", ["ROC Curve", "Calibration Curve", "Decision Curve Analysis"]):
        ax.text(-.19, 1.07, letter, transform=ax.transAxes, fontsize=11, fontweight="bold", fontfamily="Arial")
        ax.set_title(title, pad=10)
        ax.tick_params(direction="out")
        ax.grid(True, color="#EEEEEE", linestyle="-", alpha=.8, linewidth=.6)

    fpr, tpr = roc(y, p)
    axes[0].plot([0, 1], [0, 1], ls="--", color=gray, lw=.8, zorder=1)
    axes[0].plot(fpr, tpr, color=blue, lw=1.45, zorder=2)
    axes[0].set(xlabel="False Positive Rate", ylabel="True Positive Rate",
                xlim=(0, 1), ylim=(0, 1))
    axes[0].text(.97, .04,
                 f"AUROC = {metrics.auroc:.3f}\n95% CI {metrics.auroc_ci_low:.3f}–{metrics.auroc_ci_high:.3f}",
                 transform=axes[0].transAxes, ha="right", va="bottom", fontsize=7.5)
    axes[0].xaxis.set_major_locator(MultipleLocator(.2))
    axes[0].yaxis.set_major_locator(MultipleLocator(.2))

    # Main Figure 2B uses ten equal-width probability bins and square-marked
    # connecting lines, without a smoothed calibration fit or error bars.
    axes[1].plot([0, 1], [0, 1], "--", color=gray, lw=.9, label="Perfectly Calibrated")
    axes[1].plot(displayed_bins.predicted, displayed_bins.observed, "s-",
                 color=blue, lw=1.2, ms=3.8,
                 label=f"CatBoost (AUROC = {metrics.auroc:.3f})", zorder=3)
    for point in displayed_bins.loc[displayed_bins.n.eq(1)].itertuples():
        axes[1].annotate("n = 1", (point.predicted, point.observed),
                         xytext=(6, -10), textcoords="offset points", fontsize=6.5, color=gray)
    axes[1].set(xlabel="Mean Predicted Probability", ylabel="Fraction of Positives",
                xlim=(-.005, 1), ylim=(0, 1.05))
    axes[1].xaxis.set_major_locator(MultipleLocator(.2))
    axes[1].yaxis.set_major_locator(MultipleLocator(.2))
    axes[1].legend(loc="lower right", frameon=True, facecolor="white", framealpha=.95,
                   edgecolor="#CCCCCC", handlelength=1.7, borderaxespad=.4,
                   labelspacing=.35, fontsize=6.8)
    axes[1].text(.035, .96, f"Brier score = {metrics.brier:.3f}\nCalibration slope = {metrics.calibration_slope:.3f}",
                 transform=axes[1].transAxes, ha="left", va="top", fontsize=7)

    shown = dc.loc[dc.threshold.le(.5 + 1e-12)]
    axes[2].plot(shown.threshold, shown.net_benefit, color=blue, lw=1.45, label="CatBoost")
    axes[2].plot(shown.threshold, shown.treat_all, "--", color=gray, lw=.95, label="Treat All")
    axes[2].axhline(0, color="#353535", lw=.8, ls=":", label="Treat None")
    axes[2].set(xlabel="Threshold Probability", ylabel="Net Benefit",
                xlim=(0, .5), ylim=(-.05, .23))
    axes[2].xaxis.set_major_locator(MultipleLocator(.1))
    axes[2].yaxis.set_major_locator(MultipleLocator(.05))
    axes[2].yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    axes[2].legend(loc="upper right", frameon=True, facecolor="white", framealpha=.95,
                   edgecolor="#CCCCCC", handlelength=1.9, borderaxespad=.5, labelspacing=.35)
    fig.canvas.draw()
    # Native SVG preserves editable text and paths; uncompressed RGB TIFF avoids
    # the installed Pillow/libtiff LZW encoder, which exits the process on this host.
    svg_path, tif_path = OUT / f"{NAME}.svg", OUT / f"{NAME}.tif"
    fig.savefig(svg_path, format="svg", metadata={"Date": None, "Title": "Figure S6. External validation in eICU"})
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=600)
    buffer.seek(0)
    with Image.open(buffer) as rendered:
        rendered.convert("RGB").save(tif_path, compression="raw", dpi=(600, 600))
    preview = Path(tempfile.gettempdir()) / "sad_eicu_supplementary_figure_preview.png"
    fig.savefig(preview, dpi=220)
    plt.close(fig)
    with Image.open(tif_path) as tif:
        assert tif.size == (4500, 1860) and tif.mode == "RGB"
        assert tuple(tif.info["dpi"]) == (600, 600)
        assert tif.info["compression"] == "raw"
        tif_metadata = {"width_pixels": tif.width, "height_pixels": tif.height,
                        "mode": tif.mode, "dpi": [float(v) for v in tif.info["dpi"]], "compression": tif.info["compression"]}
    svg = ET.parse(svg_path).getroot()
    assert svg.tag.endswith("svg")
    assert not list(svg.iter("{http://www.w3.org/2000/svg}image")), "SVG contains raster content"
    assert list(svg.iter("{http://www.w3.org/2000/svg}text")), "Expected editable SVG text"
    caption = (
        "Supplementary Figure. External validation of the 14-variable CatBoost model in the eICU cohort.\n\n"
        "The original analysis included 1,323 ICU stays and 245 sepsis-associated delirium (SAD) events. "
        "Predicted probabilities were averaged over 20 datasets completed using MIMIC training-reference "
        "multiple imputation by chained equations (MICE). "
        "(A) Receiver operating characteristic (ROC) curve; AUROC was 0.641 (95% CI, 0.601–0.679). "
        "The confidence interval used 2,000 patient-cluster bootstrap samples with the imputation ensemble fixed. "
        "(B) Calibration using the same display method as the main Figure 2B: predicted "
        "probabilities are divided into 10 equal-width intervals between 0 and 1. Squares show mean "
        "predicted probabilities and observed event fractions in nonempty intervals and are joined by straight "
        "lines. Empty intervals are omitted. The dashed line indicates ideal calibration. "
        "The highest occupied interval (>0.7 to 0.8) contains one ICU stay, labelled in the figure. "
        "(C) Decision curve analysis showing model net benefit against treat-all and treat-none strategies "
        "shown for threshold probabilities of 0.01–0.50.\n"
    )
    (OUT / "补充图_图注.txt").write_text(caption, encoding="utf-8-sig")
    pd.DataFrame({"false_positive_rate": fpr, "true_positive_rate": tpr}).to_csv(OUT / "source_ROC.csv", index=False)
    bins.to_csv(OUT / "source_calibration_deciles.csv", index=False)
    uniform_bins.to_csv(OUT / "source_calibration_uniform_bins.csv", index=False)
    dc.to_csv(OUT / "source_DCA.csv", index=False)
    checks = {
        "completed": True, "source": "strict / mice, original analysis",
        "n_stays": len(y), "events": int(y.sum()), "auroc": float(metrics.auroc),
        "calibration_slope": float(metrics.calibration_slope),
        "calibration_joint_intercept": float(metrics.calibration_joint_intercept),
        "calibration_intercept_in_the_large": float(metrics.calibration_intercept_offset),
        "calibration_fit_used_to_change_predictions": False,
        "calibration_display": "10 equal-width probability intervals; nonempty bins connected with square markers; matches main Figure 2B. No smoothing or error bars.",
        "calibration_bins_total": 10,
        "calibration_bins_nonempty": len(displayed_bins),
        "calibration_bin_n": uniform_bins.n.tolist(),
        "style_reference_notebook": str(STYLE_SOURCE),
        "style_reference_cell_zero_based": 9,
        "style_reference_figure": str(STYLE_FIGURE),
        "style_reference_sha256": digest(STYLE_SOURCE),
        "source_sha256": source_hashes,
        "sources_unchanged": all(digest(paths[k]) == value for k, value in source_hashes.items()),
        "roc_and_dca_match_original_results": True,
        "original_quantile_calibration_diagnostics_reproduced": True,
        "calibration_display_matches_development_figure_method": True,
        "tif": tif_metadata,
        "svg_has_editable_text": True, "svg_has_raster_content": False,
        "figure_sha256": {str(p.name): digest(p) for p in [svg_path, tif_path]},
    }
    assert checks["sources_unchanged"]
    (OUT / "figure_checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    (OUT / "本版说明.txt").write_text(
        "当前补充图按研究Figure 2B的画法更新：10个等宽概率区间、蓝色方点连线、灰色理想线、"
        "Times New Roman与浅色网格。\n"
        "当前校准图数据：source_calibration_uniform_bins.csv。"
        "source_calibration_deciles.csv保留为原分析的分位数组诊断，不用于本版绘图。\n"
        "旧平滑拟合版本及source_calibration_fit.csv归档在历史版本_平滑拟合_20261021目录。\n"
        "本次不改变预测概率、AUROC、Brier评分及DCA结果。\n", encoding="utf-8-sig")
    print(json.dumps({"output": str(OUT), "preview": str(preview), "checks": checks}, indent=2))


if __name__ == "__main__":
    main()

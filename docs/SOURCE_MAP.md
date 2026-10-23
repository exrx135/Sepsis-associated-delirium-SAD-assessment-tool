# Source provenance

Source hashes are retained in the private package manifest.

- `scripts/mimic/development.py`: SAD_7day-0608_with_TRIPOD_reporting-0629-Copy.ipynb — Extracted code cells only; notebook output, attachment, metadata and execution state removed. Configurable private paths. Historical imputation omits an unrelated SA-AKI exploratory cell.
- `scripts/mimic/historical_imputation.py`: SAD_imputation_0603.ipynb — Extracted code cells only; notebook output, attachment, metadata and execution state removed. Configurable private paths. Historical imputation omits an unrelated SA-AKI exploratory cell.
- `scripts/stata/define_sad.do`: script1-SAD definition.txt — Relative configurable Stata folders; no data/log files.
- `scripts/stata/cohort_exclusions.do`: script2-排除妊娠及不满ICU24小时.txt — Relative configurable Stata folders; no data/log files.
- `scripts/stata/clean_variables.do`: 清洗变量代码（以SA-AKI清洗好的数据作为参考）.txt — Relative configurable Stata folders; no data/log files.
- `scripts/tables/table1.R`: continuous+categorical full code (table 1)_publication_labels.R — Configured local data/output directory through SAD_TABLE_DIR.
- `scripts/tables/table_s3.R`: continuous+categorical full code (Supplementary table 1)_publication_labels.R — Configured local data/output directory through SAD_TABLE_DIR.
- `scripts/eicu/evaluate_external.py`: evaluate_external.py — Only file/path configuration and output-directory creation adapted; analysis logic retained.
- `scripts/eicu/evaluate_missingness_exclusions.py`: evaluate_missingness_exclusions.py — Only file/path configuration and output-directory creation adapted; analysis logic retained.
- `scripts/eicu/miceforest_newdata_compat.py`: miceforest_newdata_compat.py — Only file/path configuration and output-directory creation adapted; analysis logic retained.
- `scripts/eicu/run_imputation_and_prediction.py`: run_imputation_and_prediction.py — Only file/path configuration and output-directory creation adapted; analysis logic retained.
- `scripts/eicu/make_supplementary_figure.py`: make_supplementary_figure.py — Current output is Figure_S6; calibration-description references use main Figure 2B; analysis logic retained.
- `scripts/eicu/correct_lab_revisions.py`: correct_lab_revisions.py — Only file/path configuration and output-directory creation adapted; analysis logic retained.
- `scripts/eicu_mapping/build_corrected_features.py`: build_corrected_features.py — Only file/path configuration and output-directory creation adapted; analysis logic retained.
- `scripts/eicu_mapping/mv_careplan_mapping.py`: mv_careplan_mapping.py — Only file/path configuration and output-directory creation adapted; analysis logic retained.
- `scripts/eicu_mapping/neuro_record_based.py`: neuro_record_based.py — Only file/path configuration and output-directory creation adapted; analysis logic retained.
- `scripts/clinical_dca/prepare_inputs.py`: prepare_inputs.py — Reads the retained SOFA source directly; removed redundant desktop-to-project copy. Configurable private paths.
- `scripts/clinical_dca/calculate_dca.py`: calculate_dca.py — Only file/path configuration and output-directory creation adapted; analysis logic retained.
- `scripts/clinical_dca/plot_dca.py`: plot_dca_30pct_20261022.py — Current combined output is Figure_6; file/path configuration and output-directory creation adapted; analysis logic retained.
- `sql/mimic/extract_supplementary_context.sql`: 01_完整提取_汇总修正版.sql — Removed all 41,295 patient seed rows and replaced with local CSV COPY; extraction logic unchanged. This is supplementary extraction, not the original complete predictor pipeline.
- `sql/eicu/extract_full_cohort.sql`: 01_eICU全量提取并直接导出.sql — Configurable local export folder; no patient-level literals.
- `app.py`: app.py — GitHub app.py blob ffd2565c2249c6b75b5db9c9bc2c5d0bc12e5a4c retrieved read-only; assets moved to configurable private folder, with clear missing-asset state. Prediction logic retained.
- `scripts/clinical_support/score_frozen_model.py`: score_frozen_model.py — Recovered original frozen-model linkage source from prior shared workspace; configurable private paths.
- `scripts/clinical_support/prepare_support_cohort.py`: build_clinical_figures.py — Retained the original input-linkage portion through linked_descriptive_cohort.csv export; omitted superseded descriptive figures using a different outcome grouping.
- `scripts/clinical_support/recalculate_binary.py`: recalculate_binary.py — Recovered final binary-endpoint statistics/figure source; configurable private paths and active Python executable. Output labels synchronized to final Figures 4 and 5; no statistical changes.
- `scripts/figures/figure_1.py`: figure_1.py — Current flowchart rendering source; only output path adapted.
- `scripts/tables/build_table_2.py`: build_table_2.py — Current Table 2 Word-rendering source; the single figure citation is mapped from Figure 6 to Figure 5 during rendering. The private source transcript and statistical cells are unchanged.

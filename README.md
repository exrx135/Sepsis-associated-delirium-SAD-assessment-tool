# SAD study source code

Source code associated with the sepsis-associated delirium manuscript prepared on 23 October 2026.

## What is included

- `scripts/stata`: available original SAD outcome definition, cohort exclusions and variable-cleaning source.
- `scripts/mimic`: code extracted from the historical imputation and final reporting/model-development notebooks. Notebook outputs, attachments and execution state have been removed.
- `scripts/tables`: R sources for the baseline and split-characteristic tables, with publication labels.
- `sql/mimic`: the later supplementary-context extraction. Its embedded patient seed has been removed and replaced by a local CSV import interface.
- `sql/eicu`: the full eICU extraction at a 24-hour ICU landmark.
- `scripts/eicu_mapping`: recorded ventilation and neurological-history mapping corrections.
- `scripts/eicu`: lab revision handling, reference imputation, frozen-model scoring, evaluation and supplementary plotting.
- `scripts/clinical_dca`: SOFA/MV comparator preparation, decision curves and the final 1–30% display-range figures.
- `app.py`: source from the existing Streamlit app, adapted to obtain its model and metadata from a separately provisioned local folder.

## Controlled data access

This repository contains no database extracts, patient-level records, prediction exports, trained model binaries, sample patient CSVs, or notebook outputs. Obtain MIMIC-IV and eICU-CRD through their official PhysioNet access processes and comply with the applicable data-use agreements:

- https://physionet.org/content/mimiciv/
- https://physionet.org/content/eicu-crd/

Keep raw and derived patient-level data in an access-controlled location outside this repository. Do not commit them, including when patient records appear inside SQL or notebook files. A filename extension alone does not establish that a file contains only code.

## Scope of reproducibility

The supplied code documents the recovered study stages. It is not a single fully automated raw-database-to-paper pipeline. The original complete SQL extraction/merging of all development predictors was not located in the supplied SAD folder; some Stata inputs originated in an earlier project. The historical fitted imputation kernel was not retained, and the eICU analysis reconstructs training-reference imputation using the archived protocol. The exact historical development package lock was not found. Re-running model selection can therefore differ from the frozen reported results. Preserve the original frozen model and linked split/prediction records privately for exact external evaluation and clinical comparison.

The development source includes its historical descriptive risk-stratification cell. The later frozen simplified-model linkage and clinical-comparison inputs are distinct. Do not substitute the historical risk output for the verified final linked predictions. The notebook named `*-0629-Copy` was selected because it contains the latest available reporting code; original versions remain in the author's preserved source folder.

Only `predictions_checked` / `results_checked` belong to the final eICU evaluation. Earlier prediction/result directories were superseded after imputation quality control. Existing assertions intentionally require the original cohort sizes, feature order and frozen-model identity; they are not a general-purpose tool for arbitrary new cohorts.

## Environment and private folders

Install Python dependencies with `python -m pip install -r requirements.txt`. The R table scripts require `dplyr`, `purrr`, and `openxlsx`. The Stata scripts require Stata. SQL scripts use PostgreSQL and a local database containing the authorized tables.

Set `SAD_PRIVATE_ROOT` to your private `final_analysis` folder. If unset, scripts resolve a sibling `study_code_and_data/final_analysis` folder outside this source repository. Preserve these private subfolders:

```
final_analysis/
  mimic_study/          # relevant original 2026.05.30 study files/subfolders
  eicu_exports/        # authorized full eICU source exports
  eicu_mapping/        # mv_audit/, neuro/, corrected_data/
  eicu_validation/     # reference_sources/, lab_audit/, predictions_checked/, results_checked/
  clinical_dca/        # source_data/, data/, results/, figures/, qa/, notes/
  mimic_exports/       # four final clinical-support extract summaries
  clinical_support/    # linked descriptive cohort and final binary statistics
  publication_figures/ # flowchart render outputs
  deployment_assets/  # frozen model and app metadata, kept private
```

Table scripts use `SAD_TABLE_DIR` for their authorized input/output folder. Edit the three relative folder settings at the top of the Stata scripts for your local inputs. Before running the SQL scripts, set `sad.seed_csv` (MIMIC supplementary extraction) or `sad.output_dir` (eICU), as described in their headers. PostgreSQL `COPY` paths are on the database server and need appropriate read/write permissions. Cohort seed columns are declared in the SQL; no seed records are supplied.

## Execution order

With authorized inputs and the original frozen resources available, the recovered sequence is:

1. Original Stata outcome/eligibility/cleaning, historical imputation and development/reporting code, followed by R descriptive tables. These stages require the earlier extracted inputs described above.
2. Full eICU SQL extraction; ventilation and neurological mapping; `build_corrected_features.py`; then `correct_lab_revisions.py`.
3. `run_imputation_and_prediction.py`, `evaluate_external.py`, and `make_supplementary_figure.py`. Sensitivity scripts are available separately.
4. `scripts/clinical_dca/prepare_inputs.py`, `calculate_dca.py`, then `plot_dca.py`.

The eICU scripts retain the original run identifier for the archived exports. For a newly extracted run, configure the source/run identifier consistently across extraction/mapping/lab scripts. `neuro_record_based.py --help` documents its source/run/output arguments. Plotting the external figure also uses the private original notebook as a style reference; it is not distributed because it contains saved outputs.

## App deployment

The app's prediction code was recovered from https://github.com/exrx135/Sepsis-associated-delirium-SAD-assessment-tool (app.py blob `ffd2565c2249c6b75b5db9c9bc2c5d0bc12e5a4c`). Supply the following local trusted assets through `SAD_APP_ASSET_DIR`:

- `SAD_7day_SHAP_simplified_CatBoost_model.pkl`
- `SAD_7day_SHAP_simplified_features.json`
- `SAD_7day_SHAP_simplified_categorical_features.json`
- `SAD_7day_SHAP_simplified_model_info.json`

Then run `streamlit run app.py`. These assets are intentionally not part of the code-only upload package. Only load a trusted local pickle. The app retains its original presentation thresholds; they are not the manuscript's later descriptive risk tertiles. For public hosting, provision the model separately on the deployment host; uploading this source folder alone will not provide a working model. Replacing the current repository with a code-only tree requires removing previously tracked sample/data/model files as well: `.gitignore` does not untrack existing files.

## Verification performed for this package

Static Python syntax checking, extension allowlisting, removal of notebook outputs, removal of embedded MIMIC patient seeds, and checks for hard-coded machine paths and common secret patterns. Study models were not retrained; analyses were not rerun. These packaging checks do not assert numerical reproducibility of a fresh analysis.


## Recovered clinical support analysis

`scripts/clinical_support` restores the earlier shared-workspace source that generated the final support-stratified analysis. Run `score_frozen_model.py`, `prepare_support_cohort.py`, and `recalculate_binary.py` in that order with the authorized frozen model and extract summaries. The preparation script contains only the original join through its cohort export; superseded plots of an alternative outcome grouping are excluded. The final binary script exports Figure_4 (alluvial distribution) and Figure_5 (support-stratified incidence). The clinical DCA source exports the combined Figure_6, and external evaluation exports Figure_S6. The detailed baseline R source exports Table_S3; external predictor definitions and missingness are Table_S2. `scripts/figures/figure_1.py` contains the final study-flowchart rendering code.

`build_table_2.py` renders final Table_2.docx from the separately retained aggregate transcript at `publication_tables/table_2_transcript.json`. Final supplementary table numbering includes Table S4 (model performance with 95% confidence intervals), Table S5 (DCA threshold results), Table S6 (external cohort/imputation variants), and Table S7 (external predictor-completeness restrictions). Numerical-analysis CSV names remain descriptive and unchanged.


## Publication numbering

Main figures:

| Number | Content |
| --- | --- |
| Figure 1 | Study flowchart |
| Figure 2 | Model performance |
| Figure 3 | SHAP interpretation |
| Figure 4 | Alluvial distribution of risk, clinical support and outcomes |
| Figure 5 | SAD incidence within clinical support categories |
| Figure 6 | Decision curves and incremental net benefit |

Supplementary figures:

| Number | Content |
| --- | --- |
| Figure S1 | Technical workflow |
| Figure S2 | Missing data and imputation |
| Figure S3 | Boruta feature selection |
| Figure S4 | Observed SAD incidence across predicted risk strata |
| Figure S5 | Frozen simplified-model performance |
| Figure S6 | External evaluation in eICU |
| Figure S7 | Web application |

Supplementary tables:

| Number | Content |
| --- | --- |
| Table S1 | Candidate-variable definitions |
| Table S2 | External predictor summaries and missingness |
| Table S3 | Detailed baseline characteristics |
| Table S4 | Detailed model performance and 95% confidence intervals |
| Table S5 | Net benefit at fixed thresholds |
| Table S6 | External performance across cohort and imputation definitions |
| Table S7 | External restrictions by predictor completeness |

The seven supplementary figures and seven supplementary tables are assembled in separate Word documents. The working supplementary-methods document is retained privately in the study materials. Original source snapshots retain their historical filenames and figure labels; only the current portable scripts use the publication numbering above. Statistical inputs, calculations and outputs are unchanged by the numbering update.

The historical `development.py` reporting section still generates `TRIPOD_AI_reporting_supplement.docx` in the private working folder. This combined methods/results document is an internal reporting reference, not the current submission supplement. Use the separately assembled supplementary-figures and supplementary-tables Word documents for submission. The Table 2 renderer updates only its historical transcript's figure citation at rendering time; the retained transcript and table cells are unchanged.

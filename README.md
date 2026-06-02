# Sepsis Associated Delirium (SAD) Assessment Tool

This Streamlit application provides a web-based risk assessment tool for estimating the probability of sepsis-associated delirium (SAD) within 7 days after sepsis diagnosis in adult ICU patients.

## Model summary

- Model type: CatBoost Classifier
- Outcome: SAD within 7 days after sepsis diagnosis
- Development dataset: MIMIC-IV
- Number of predictors: 14
- External validation: not claimed in this online tool

The tool is intended to provide supplementary risk assessment and early warning information. It should not be used as a standalone diagnostic method or as the sole basis for clinical decision-making.

## Files

- `app.py`: Streamlit application
- `SAD_7day_SHAP_simplified_CatBoost_model.pkl`: trained simplified CatBoost model
- `SAD_7day_SHAP_simplified_features.json`: model predictor list
- `SAD_7day_SHAP_simplified_categorical_features.json`: categorical/binary predictor list
- `SAD_7day_SHAP_simplified_model_info.json`: model metadata
- `requirements.txt`: Python dependencies
- `sample_input.csv`: example CSV input template

## Local deployment

```bash
pip install -r requirements.txt
streamlit run app.py
```

## GitHub update

To update an existing GitHub repository, upload all files in this folder to the repository root and choose **Commit changes**. Existing files with the same names can be overwritten.

## Streamlit Cloud deployment

Use the following settings:

- Repository: your GitHub repository
- Branch: `main`
- Main file path: `app.py`

After each GitHub commit, Streamlit Cloud usually redeploys the app automatically.


## Version note

This version uses compact horizontal input rows to reduce page height while preserving the prediction logic and SHAP explanation workflow.


## v11 update

- Variable definitions are displayed in a compact blue information box.
- The risk category is color-coded: low risk in green, intermediate risk in yellow, and high risk in red.
- Prediction logic and model files are unchanged.

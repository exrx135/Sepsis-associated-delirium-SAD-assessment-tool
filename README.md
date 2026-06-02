# Sepsis Associated Delirium (SAD) Assessment Tool

This repository contains a Streamlit-based online calculator for estimating the risk of **sepsis-associated delirium (SAD) within 7 days after sepsis diagnosis** among adult ICU patients.

## Important note

This model was developed using the MIMIC-IV critical care database and internally validated. The current online tool does **not** claim external validation. The output is intended to provide supplementary risk assessment and early warning information, and should not be used as a standalone diagnostic method or as the sole basis for clinical decision-making.

## Prediction target

The model predicts the probability of developing **sepsis-associated delirium (SAD)** within 7 days after sepsis diagnosis.

## Required predictors

The app uses a simplified CatBoost model with 14 predictors:

1. invasive_vent_12h_24h_pre_dx
2. chronic_neurological
3. avg_po2
4. hr_before_sepsis_urineoutput
5. avg_mchc
6. avg_rdw
7. admission_age
8. avg_mbp
9. avg_ptt
10. avg_calcium
11. avg_aniongap
12. avg_pt
13. los_before_icu
14. avg_hematocrit

## Variable definitions

- **Mechanical ventilation**: use of invasive mechanical ventilation during the period from 12 to 24 hours before sepsis diagnosis.
- **Continuous variables**: all continuous predictors except urine output represent mean values measured during the 24 hours preceding sepsis diagnosis; urine output represents the total urine output accumulated during this 24-hour window.
- **Chronic neurological disease**: identified from hospital-level ICD diagnosis records linked to the sepsis ICU stay, including pre-existing comorbidities and diagnoses recorded during the hospital admission. The definition covers chronic neurological disorders associated with persistent neurological dysfunction, such as dementia or other neurodegenerative diseases, Parkinsonian and other movement disorders, epilepsy, demyelinating diseases, chronic spinal cord diseases, chronic paralysis, and related long-term neurological conditions; migraine and related headache disorders were excluded.

## Local deployment

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

## Upload to GitHub

### Option 1: Upload through the GitHub web page

1. Create a new GitHub repository.
2. Unzip `SAD_7day_Streamlit_app_v4.zip` on your computer.
3. Open the new GitHub repository page.
4. Click **Add file** → **Upload files**.
5. Drag all unzipped files into the upload area, including:
   - `app.py`
   - `requirements.txt`
   - `README.md`
   - `sample_input.csv`
   - `SAD_7day_SHAP_simplified_CatBoost_model.pkl`
   - `SAD_7day_SHAP_simplified_features.json`
   - `SAD_7day_SHAP_simplified_categorical_features.json`
   - `SAD_7day_SHAP_simplified_model_info.json`
6. Click **Commit changes**.

### Option 2: Upload with Git commands

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
# Copy all project files into this folder, then run:
git add .
git commit -m "Add SAD Streamlit risk assessment tool"
git push
```

## Deploy on Streamlit Community Cloud

1. Go to Streamlit Community Cloud.
2. Click **New app**.
3. Select your GitHub repository.
4. Set the main file path as:

```text
app.py
```

5. Click **Deploy**.

If deployment fails, first check whether `requirements.txt` is present in the repository root and whether the model file is also in the repository root.

## Files

```text
app.py
requirements.txt
README.md
sample_input.csv
SAD_7day_SHAP_simplified_CatBoost_model.pkl
SAD_7day_SHAP_simplified_features.json
SAD_7day_SHAP_simplified_categorical_features.json
SAD_7day_SHAP_simplified_model_info.json
```

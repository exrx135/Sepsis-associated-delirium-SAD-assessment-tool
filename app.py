import json
import pickle
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from catboost import Pool

APP_DIR = Path(__file__).resolve().parent
MODEL_PATH = APP_DIR / "SAD_7day_SHAP_simplified_CatBoost_model.pkl"
FEATURES_PATH = APP_DIR / "SAD_7day_SHAP_simplified_features.json"
CATEGORICAL_PATH = APP_DIR / "SAD_7day_SHAP_simplified_categorical_features.json"
MODEL_INFO_PATH = APP_DIR / "SAD_7day_SHAP_simplified_model_info.json"

st.set_page_config(
    page_title="SA-D Risk Assessment Tool",
    page_icon="🧠",
    layout="wide",
)


@st.cache_resource
def load_model():
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


@st.cache_data
def load_metadata():
    with open(FEATURES_PATH, "r", encoding="utf-8") as f:
        features = json.load(f)
    with open(CATEGORICAL_PATH, "r", encoding="utf-8") as f:
        categorical_features = json.load(f)
    with open(MODEL_INFO_PATH, "r", encoding="utf-8") as f:
        model_info = json.load(f)
    return features, categorical_features, model_info


model = load_model()
features, categorical_features, model_info = load_metadata()
DISPLAY_NAMES = dict(zip(model_info.get("best_features", []), model_info.get("best_features_display", [])))

DEFAULTS = {
    "invasive_vent_12h_24h_pre_dx": 0,
    "chronic_neurological": 0,
    "avg_po2": 90.0,
    "hr_before_sepsis_urineoutput": 1000.0,
    "avg_mchc": 32.0,
    "avg_rdw": 14.0,
    "admission_age": 65.0,
    "avg_mbp": 75.0,
    "avg_ptt": 35.0,
    "avg_calcium": 8.5,
    "avg_aniongap": 14.0,
    "avg_pt": 13.0,
    "los_before_icu": 1.0,
    "avg_hematocrit": 35.0,
}

INPUT_CONFIG = {
    "avg_po2": (20.0, 300.0, 1.0, "mmHg"),
    "hr_before_sepsis_urineoutput": (0.0, 10000.0, 10.0, "mL"),
    "avg_mchc": (20.0, 45.0, 0.1, "g/dL"),
    "avg_rdw": (8.0, 35.0, 0.1, "%"),
    "admission_age": (18.0, 100.0, 1.0, "years"),
    "avg_mbp": (30.0, 160.0, 1.0, "mmHg"),
    "avg_ptt": (10.0, 200.0, 0.1, "s"),
    "avg_calcium": (4.0, 15.0, 0.1, "mg/dL"),
    "avg_aniongap": (0.0, 50.0, 0.1, "mmol/L"),
    "avg_pt": (5.0, 80.0, 0.1, "s"),
    "los_before_icu": (0.0, 60.0, 0.1, "days"),
    "avg_hematocrit": (10.0, 70.0, 0.1, "%"),
}


def feature_label(feature: str) -> str:
    return DISPLAY_NAMES.get(feature, feature)


def model_feature_label(feature: str) -> str:
    return f"{DISPLAY_NAMES.get(feature, feature)} ({feature})"


def prepare_input(input_df: pd.DataFrame) -> pd.DataFrame:
    input_df = input_df[features].copy()
    for col in categorical_features:
        input_df[col] = input_df[col].astype(int)
    for col in features:
        if col not in categorical_features:
            input_df[col] = pd.to_numeric(input_df[col], errors="coerce")
    return input_df


def make_prediction(input_df: pd.DataFrame) -> pd.DataFrame:
    model_input = prepare_input(input_df)
    prob = model.predict_proba(model_input)[:, 1]
    result = model_input.copy()
    result["predicted_probability"] = prob
    return result


def risk_group(probability: float):
    if probability < 0.15:
        return "Low", "Estimated risk <15%."
    if probability < 0.30:
        return "Intermediate", "Estimated risk 15%–30%."
    return "High", "Estimated risk ≥30%."


def get_local_shap(input_df: pd.DataFrame) -> pd.DataFrame:
    model_input = prepare_input(input_df)
    cat_idx = [features.index(c) for c in categorical_features]
    pool = Pool(model_input, cat_features=cat_idx)
    shap_values = model.get_feature_importance(pool, type="ShapValues")
    contribution = shap_values[0, :-1]
    df = pd.DataFrame({
        "Feature": features,
        "Display name": [DISPLAY_NAMES.get(f, f) for f in features],
        "Value": [model_input.iloc[0][f] for f in features],
        "SHAP contribution": contribution,
    })
    df["Direction"] = df["SHAP contribution"].apply(lambda x: "Increases predicted risk" if x > 0 else "Decreases predicted risk")
    df["Absolute contribution"] = df["SHAP contribution"].abs()
    return df.sort_values("Absolute contribution", ascending=False)


st.title("SA-D Risk Assessment Tool")
st.caption("Predicting the risk of sepsis-associated delirium (SAD) within 7 days after sepsis diagnosis.")

with st.expander("About this tool", expanded=False):
    st.markdown(
        """
This tool estimates the risk of developing **sepsis-associated delirium (SAD)** within 7 days after sepsis diagnosis among adult intensive care unit (ICU) patients.

The prediction model was developed using data from the MIMIC-IV critical care database and was internally validated. It is intended to provide supplementary risk assessment and early warning information for clinicians.

The predicted probability represents the estimated likelihood of developing SAD within 7 days following sepsis diagnosis according to the study definition used during model development.

This tool should not be used as a standalone diagnostic method or as the sole basis for clinical decision-making. Clinical assessment and professional judgment remain essential when evaluating individual patients.
        """
    )

with st.sidebar:
    st.header("Model information")
    st.write(f"**Model:** {model_info.get('model_type', 'CatBoostClassifier')}")
    st.write("**Prediction target:** SAD within 7 days after sepsis diagnosis")
    st.write("**Development dataset:** MIMIC-IV")
    st.write(f"**Number of predictors:** {len(features)}")
    st.write(f"**Internal validation AUROC:** {model_info.get('simplified_validation_auc', float('nan')):.3f}")
    st.write(f"**Test AUROC:** {model_info.get('simplified_test_auc', float('nan')):.3f}")
    st.info("No external validation result is claimed in this online tool. The output should be interpreted as a risk estimate and early warning signal.")


tab_single, tab_batch, tab_model = st.tabs(["Single-patient prediction", "Batch CSV prediction", "Predictor list"])

with tab_single:
    st.subheader("Single-patient prediction")
    st.write("Enter the 14 simplified-model predictors below.")

    values = {}
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Binary predictors")
        for feature in categorical_features:
            values[feature] = st.selectbox(
                model_feature_label(feature),
                options=[0, 1],
                format_func=lambda x: "Yes / 1" if x == 1 else "No / 0",
                index=int(DEFAULTS[feature]),
            )

    numeric_features = [f for f in features if f not in categorical_features]
    with col2:
        st.markdown("#### Continuous predictors")
        for feature in numeric_features:
            min_value, max_value, step, unit = INPUT_CONFIG.get(feature, (0.0, 9999.0, 0.1, ""))
            values[feature] = st.number_input(
                f"{model_feature_label(feature)} [{unit}]",
                min_value=min_value,
                max_value=max_value,
                value=float(DEFAULTS.get(feature, min_value)),
                step=step,
            )

    st.info(
        """
**Variable definitions**  
• **Mechanical ventilation**: use of invasive mechanical ventilation during the period from 12 to 24 hours before sepsis diagnosis.  
• **Continuous variables**: unless otherwise specified, continuous predictors represent mean values measured during the 24 hours preceding sepsis diagnosis; **urine output** represents the total urine output accumulated during this 24-hour window.  
• **Chronic neurological disease**: history of chronic neurological disorders associated with persistent neurological dysfunction, including dementia or other neurodegenerative diseases, Parkinsonian disorders, epilepsy, chronic spinal cord diseases, demyelinating diseases, chronic paralysis, and related long-term neurological conditions.
        """
    )

    input_df = pd.DataFrame([{feature: values[feature] for feature in features}])
    probability = float(make_prediction(input_df)["predicted_probability"].iloc[0])
    group, group_note = risk_group(probability)

    st.markdown("---")
    st.subheader("Predicted Risk of Sepsis-Associated Delirium Within 7 Days")
    m1, m2 = st.columns([1, 2])
    m1.metric("Predicted probability", f"{probability:.1%}")
    m2.metric("Risk category", group)
    st.progress(min(max(probability, 0.0), 1.0))
    st.markdown(
        f"""
**Interpretation**  
According to this prediction model, the estimated probability that this ICU patient with sepsis will develop **sepsis-associated delirium (SAD) within 7 days after sepsis diagnosis** is **{probability:.1%}**.  

Risk category: **{group}**. {group_note} These categories are intended only to make the risk estimate easier to read and should not be interpreted as externally validated clinical decision thresholds.
        """
    )

    with st.expander("Individual prediction explanation based on SHAP values", expanded=True):
        try:
            shap_df = get_local_shap(input_df)
            top_df = shap_df.head(10).copy()
            fig, ax = plt.subplots(figsize=(8, 4.8))
            plot_df = top_df.sort_values("SHAP contribution")
            ax.barh(plot_df["Display name"], plot_df["SHAP contribution"])
            ax.axvline(0, linewidth=1)
            ax.set_xlabel("SHAP contribution to model output")
            ax.set_ylabel("")
            ax.set_title("Top feature contributions for this prediction")
            st.pyplot(fig, use_container_width=True)
            st.caption("Positive SHAP values increase the model-predicted risk; negative SHAP values decrease the model-predicted risk.")
            st.dataframe(
                shap_df[["Display name", "Feature", "Value", "SHAP contribution", "Direction"]],
                use_container_width=True,
            )
        except Exception as exc:
            st.warning(f"SHAP explanation could not be generated for this input: {exc}")

    with st.expander("Show model input table"):
        display_df = input_df.rename(columns={f: DISPLAY_NAMES.get(f, f) for f in input_df.columns})
        st.dataframe(display_df, use_container_width=True)

with tab_batch:
    st.subheader("Batch CSV prediction")
    st.write("Upload a CSV file containing all required predictor columns. Column names must match the original model feature names.")

    template = pd.DataFrame([{feature: DEFAULTS.get(feature, 0) for feature in features}])
    st.download_button(
        "Download CSV template",
        data=template.to_csv(index=False).encode("utf-8-sig"),
        file_name="SAD_7day_prediction_template.csv",
        mime="text/csv",
    )

    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded_file is not None:
        try:
            batch_df = pd.read_csv(uploaded_file)
            missing = [f for f in features if f not in batch_df.columns]
            if missing:
                st.error("Missing required columns: " + ", ".join(missing))
            else:
                result_df = make_prediction(batch_df)
                result_df["risk_category"] = result_df["predicted_probability"].apply(lambda p: risk_group(float(p))[0])
                st.success(f"Prediction completed for {len(result_df)} patients.")
                st.dataframe(result_df, use_container_width=True)
                st.download_button(
                    "Download prediction results",
                    data=result_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="SAD_7day_batch_predictions.csv",
                    mime="text/csv",
                )
        except Exception as exc:
            st.error(f"Prediction failed: {exc}")

with tab_model:
    st.subheader("Predictor list")
    predictor_table = pd.DataFrame({
        "Feature name": features,
        "Display name": [DISPLAY_NAMES.get(f, f) for f in features],
        "Type": ["Categorical/binary" if f in categorical_features else "Continuous" for f in features],
    })
    st.dataframe(predictor_table, use_container_width=True)

    with st.expander("Model development summary"):
        st.markdown(
            f"""
- Model type: **{model_info.get('model_type', 'CatBoostClassifier')}**  
- Outcome: **SAD within 7 days after sepsis diagnosis**  
- Development dataset: **MIMIC-IV**  
- Number of predictors: **{len(features)}**  
- Internal validation AUROC: **{model_info.get('simplified_validation_auc', float('nan')):.3f}**  
- Test AUROC: **{model_info.get('simplified_test_auc', float('nan')):.3f}**  
- External validation: **not claimed in this tool**
            """
        )

    st.markdown("#### Expected CSV columns")
    st.code("\n".join(features))

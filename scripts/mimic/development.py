# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

from IPython.display import display

# %% Original notebook code cell 6
# ==================== Publication-ready feature display names ====================
# 仅用于绘图和输出显示；不改变任何原始变量名、建模流程或特征筛选流程。

FEATURE_DISPLAY_NAMES = {
    "admission_age": "Age",
    "gender": "Sex",
    "weight": "Weight",
    "los_before_icu": "Pre-ICU LOS",
    "hospital_los": "Hospital LOS",
    "icu_los": "ICU LOS",

    "hypertension": "Hypertension",
    "diabetes": "Diabetes",
    "chronic_lung_disease": "Chronic pulmonary disease",
    "chronic_neurological": "Chronic neurological disease",
    "chronic_liver_disease": "Chronic liver disease",
    "chronic_kidney_disease": "Chronic kidney disease",
    "chronic_heart_disease": "Chronic heart disease",
    "invasive_vent_12h_24h_pre_dx": "Mechanical ventilation",
    "vasoactive_agent": "Vasoactive agent",

    "avg_heart_rate": "Heart rate",
    "avg_sbp": "Systolic blood pressure",
    "avg_dbp": "Diastolic blood pressure",
    "avg_mbp": "Mean arterial pressure",
    "avg_resp_rate": "Respiratory rate",
    "avg_temperature": "Temperature",
    "avg_spo2": "SpO₂",

    "avg_po2": "PaO₂",
    "avg_pco2": "PaCO₂",
    "avg_pao2fio2": "PaO₂/FiO₂",
    "avg_ph": "pH",
    "avg_baseexcess": "Base excess",
    "avg_bicarbonate": "Bicarbonate",
    "avg_totalco2": "Total CO₂",

    "avg_hematocrit": "Hematocrit",
    "avg_hemoglobin": "Hemoglobin",
    "avg_mch": "MCH",
    "avg_mchc": "MCHC",
    "avg_mcv": "MCV",
    "avg_platelet": "Platelet count",
    "avg_rbc": "Red blood cell count",
    "avg_rdw": "RDW",
    "avg_wbc": "White blood cell count",

    "avg_inr": "INR",
    "avg_pt": "PT",
    "avg_ptt": "PTT",

    "avg_aniongap": "Anion gap",
    "avg_bun": "BUN",
    "avg_calcium": "Calcium",
    "avg_chloride": "Chloride",
    "avg_creatinine": "Creatinine",
    "avg_sodium": "Sodium",
    "avg_potassium": "Potassium",
    "avg_glucose": "Glucose",

    "hr_before_sepsis_urineoutput": "Urine output"
}

def display_feature_name(feature):
    """Return publication-ready display name for a feature without changing original variable names."""
    return FEATURE_DISPLAY_NAMES.get(feature, feature)

def display_feature_names(features):
    """Return publication-ready display names for a feature list."""
    return [display_feature_name(f) for f in features]

def safe_filename_from_label(label):
    """Generate a safe filename segment from a display label."""
    return (
        str(label)
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .replace(":", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("%", "percent")
        .replace("₂", "2")
    )

# %% Original notebook code cell 7
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split, GridSearchCV, StratifiedKFold, ParameterGrid
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.svm import SVC
from sklearn.metrics import (
    roc_auc_score, accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, balanced_accuracy_score, matthews_corrcoef,
    cohen_kappa_score, log_loss, brier_score_loss, mean_squared_error,
    mean_absolute_error, roc_curve, precision_recall_curve
)
from sklearn.feature_selection import VarianceThreshold
from sklearn.base import BaseEstimator

from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from imblearn.combine import SMOTETomek

import warnings
import sys
import re
import os
import json
import ast
import shap
from datetime import datetime

warnings.filterwarnings("ignore", category=UserWarning)

CatBoostClassifier._estimator_type = "classifier"
CatBoostClassifier.__sklearn_tags__ = BaseEstimator.__sklearn_tags__

N_JOBS = max(1, os.cpu_count() - 1)
print(f"可用CPU核心数: {os.cpu_count()}，使用核心数: {N_JOBS}")

PROJECT_DIR = str(_sad_private_path("mimic_study", '数据建模'))
DATA_FILE = os.path.join(PROJECT_DIR, "imputed_merge_data.csv")
os.makedirs(PROJECT_DIR, exist_ok=True)
os.chdir(PROJECT_DIR)

print(f"当前工作目录: {os.getcwd()}")
print(f"数据文件路径: {DATA_FILE}")

USE_GPU = False


# ==================== 参数网格：scale_pos_weight=[2,3] ====================
param_grids = {
    "XGBoost": {
        "learning_rate": [0.01],
        "max_depth": [4],
        "n_estimators": [1500],
        "gamma": [0.1],
        "reg_lambda": [5],
        "subsample": [0.8],
        "colsample_bytree": [0.8],
        "scale_pos_weight": [2, 3]
    },
    "CatBoost": {
        "learning_rate": [0.01],
        "depth": [6],
        "iterations": [1500],
        "l2_leaf_reg": [10],
        "min_data_in_leaf": [5],
        "grow_policy": ["SymmetricTree"],
        "scale_pos_weight": [2, 3]
    },
    "LightGBM": {
        "learning_rate": [0.01],
        "num_leaves": [31],
        "min_data_in_leaf": [15],
        "max_depth": [-1],
        "n_estimators": [800],
        "lambda_l1": [0],
        "lambda_l2": [0.1],
        "feature_fraction": [0.8],
        "scale_pos_weight": [2, 3]
    },
    "SVM": {
        "estimator__C": [10],
        "estimator__kernel": ["rbf"],
        "estimator__gamma": ["scale"],
        "estimator__class_weight": ["balanced"]
    },
    "Random Forest": {
        "n_estimators": [1500],
        "max_depth": [None],
        "min_samples_split": [5],
        "min_samples_leaf": [2],
        "max_features": ["sqrt"],
        "class_weight": ["balanced"]
    },
    "Logistic Regression": {
        "C": [1],
        "l1_ratio": [0],
        "solver": ["saga"],
        "class_weight": ["balanced"]
    },
    "Decision Tree": {
        "criterion": ["gini"],
        "max_depth": [10],
        "min_samples_split": [5],
        "min_samples_leaf": [2],
        "ccp_alpha": [0]
    },
    "Ridge Regression": {
        "estimator__alpha": [1]
    },
    "KNN": {
        "estimator__n_neighbors": [15],
        "estimator__weights": ["distance"],
        "estimator__p": [1]
    }
}


# ==================== sigmoid 概率校准器 ====================
class SigmoidProbabilityCalibrator:
    def __init__(self, base_model):
        self.base_model = base_model
        self.calibrator = LogisticRegression(solver="lbfgs", max_iter=1000)

    def fit(self, X_cal, y_cal):
        raw_proba = self.base_model.predict_proba(X_cal)[:, 1]
        raw_proba = np.clip(raw_proba, 1e-6, 1 - 1e-6)
        logit_proba = np.log(raw_proba / (1 - raw_proba)).reshape(-1, 1)
        self.calibrator.fit(logit_proba, y_cal)
        return self

    def predict_proba(self, X):
        raw_proba = self.base_model.predict_proba(X)[:, 1]
        raw_proba = np.clip(raw_proba, 1e-6, 1 - 1e-6)
        logit_proba = np.log(raw_proba / (1 - raw_proba)).reshape(-1, 1)
        calibrated_proba = self.calibrator.predict_proba(logit_proba)[:, 1]
        return np.column_stack([1 - calibrated_proba, calibrated_proba])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


# ==================== 特征筛选函数 ====================
def prefilter_features(X, numerical_features, categorical_features, threshold=0.85):
    missing_rate = X.isnull().mean()
    low_missing = missing_rate[missing_rate < threshold].index.tolist()

    available_numerical = [col for col in numerical_features if col in X.columns]
    available_categorical = [col for col in categorical_features if col in X.columns]

    if len(available_numerical) > 0:
        selector = VarianceThreshold(threshold=0.05)
        selector.fit(X[available_numerical])
        high_variance_num = selector.get_feature_names_out(available_numerical).tolist()
    else:
        high_variance_num = []

    retained_features = list(set(high_variance_num + available_categorical) & set(low_missing))
    return retained_features


def remove_high_correlation(X, numerical_features, categorical_features, threshold=0.90, min_features=15):
    available_numerical = [col for col in numerical_features if col in X.columns]
    available_categorical = [col for col in categorical_features if col in X.columns]

    if len(available_numerical) <= 1:
        print("数值变量不足2个，跳过高相关筛选")
        return available_numerical + available_categorical

    corr_matrix = X[available_numerical].corr().abs()
    upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))

    to_drop = [column for column in upper.columns if any(upper[column] > threshold)]

    remaining_numerical = [col for col in available_numerical if col not in to_drop]
    remaining_features = remaining_numerical + available_categorical

    if len(remaining_features) < min_features:
        print(f"警告：剔除高相关特征后只剩{len(remaining_features)}个特征，少于最小值{min_features}")
        print("将保留所有特征")
        return X.columns.tolist()

    print(f"因高度相关被剔除的特征数: {len(to_drop)}")
    if len(to_drop) > 0:
        print("被剔除的高相关特征:", to_drop)

    return remaining_features


def prepare_data_for_boruta(X, numerical_features, categorical_features):
    available_numerical = [col for col in numerical_features if col in X.columns]
    available_categorical = [col for col in categorical_features if col in X.columns]

    X_parts = []
    feature_map = {}

    if len(available_numerical) > 0:
        X_num = X[available_numerical].copy().reset_index(drop=True)
        X_parts.append(X_num)

        for col in available_numerical:
            feature_map[col] = col

    if len(available_categorical) > 0:
        X_cat = X[available_categorical].copy().astype(str)

        ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        X_cat_encoded = ohe.fit_transform(X_cat)

        encoded_names = list(ohe.get_feature_names_out(available_categorical))

        X_cat_encoded_df = pd.DataFrame(
            X_cat_encoded,
            columns=encoded_names,
            index=X.index
        ).reset_index(drop=True)

        X_parts.append(X_cat_encoded_df)

        start = 0
        for col, categories in zip(available_categorical, ohe.categories_):
            end = start + len(categories)
            for encoded_col in encoded_names[start:end]:
                feature_map[encoded_col] = col
            start = end

    X_boruta = pd.concat(X_parts, axis=1)
    return X_boruta, feature_map


def boruta_feature_selection(X_boruta, y, feature_map=None, min_features=15):
    from boruta import BorutaPy

    rf = RandomForestClassifier(
        n_estimators=500,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )

    boruta = BorutaPy(
        estimator=rf,
        n_estimators="auto",
        verbose=0,
        perc=90,
        random_state=42
    )

    boruta.fit(X_boruta.values, y.values)

    selected_encoded_features = X_boruta.columns[boruta.support_].tolist()

    rf.fit(X_boruta, y)

    importance_df = pd.DataFrame({
        "Encoded_Feature": X_boruta.columns,
        "Importance": rf.feature_importances_,
        "Selected_by_Boruta": X_boruta.columns.isin(selected_encoded_features)
    }).sort_values("Importance", ascending=False).reset_index(drop=True)

    if feature_map is None:
        feature_map = {col: col for col in X_boruta.columns}

    selected_original_features = []
    for encoded_feature in selected_encoded_features:
        original_feature = feature_map.get(encoded_feature, encoded_feature)
        if original_feature not in selected_original_features:
            selected_original_features.append(original_feature)

    print(f"Boruta原始确认编码后特征数: {len(selected_encoded_features)}")
    print("Boruta确认的编码后特征:", selected_encoded_features)
    print(f"映射回原始变量后的特征数: {len(selected_original_features)}")
    print("映射回原始变量后的特征:", selected_original_features)

    if len(selected_original_features) < min_features:
        print(f"Boruta映射回原始变量后少于{min_features}个，将按RF重要性补足")

        for encoded_feature in importance_df["Encoded_Feature"]:
            original_feature = feature_map.get(encoded_feature, encoded_feature)

            if original_feature not in selected_original_features:
                selected_original_features.append(original_feature)

            if len(selected_original_features) >= min_features:
                break

    return selected_original_features, selected_encoded_features, importance_df, boruta


# ==================== 阈值、评估、预处理函数 ====================
def find_optimal_threshold(y_true, y_proba, method="youden"):
    if method == "youden":
        fpr, tpr, thresholds = roc_curve(y_true, y_proba)
        j_scores = tpr - fpr
        return thresholds[np.argmax(j_scores)]
    elif method == "f1":
        precision, recall, thresholds = precision_recall_curve(y_true, y_proba)
        f1_scores = 2 * (precision * recall) / (precision + recall + 1e-9)
        return thresholds[np.argmax(f1_scores)]
    elif method == "closest":
        fpr, tpr, thresholds = roc_curve(y_true, y_proba)
        dist = np.sqrt(fpr ** 2 + (tpr - 1) ** 2)
        return thresholds[np.argmin(dist)]
    else:
        return 0.5


def load_and_split_data(file_path, sample_size=None):
    data = pd.read_csv(file_path)

    if sample_size is not None and len(data) > sample_size:
        data = data.sample(n=sample_size, random_state=42)
        print(f"使用 {sample_size} 个样本进行测试")

    X = data.drop(["sad_7days"], axis=1)
    y = data["sad_7days"]

    X_temp, X_test, y_temp, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    X_train, X_val, y_train, y_val = train_test_split(
        X_temp,
        y_temp,
        test_size=0.2,
        random_state=42,
        stratify=y_temp
    )

    print(f"训练集大小: {len(X_train)}, 验证集大小: {len(X_val)}, 测试集大小: {len(X_test)}")
    print(f"正样本比例 - 训练集: {y_train.mean():.4f}, 验证集: {y_val.mean():.4f}, 测试集: {y_test.mean():.4f}")

    return X_train, X_val, X_test, y_train, y_val, y_test


def preprocess_data_for_linear(X_tr, X_val, X_test, numerical, categorical):
    ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)

    Xc_train = ohe.fit_transform(X_tr[categorical])
    Xc_val = ohe.transform(X_val[categorical])
    Xc_test = ohe.transform(X_test[categorical])

    scaler = StandardScaler()

    Xn_train = scaler.fit_transform(X_tr[numerical])
    Xn_val = scaler.transform(X_val[numerical])
    Xn_test = scaler.transform(X_test[numerical])

    X_train_proc = np.hstack([Xn_train, Xc_train])
    X_val_proc = np.hstack([Xn_val, Xc_val])
    X_test_proc = np.hstack([Xn_test, Xc_test])

    cat_names = list(ohe.get_feature_names_out(categorical))
    fnames = numerical + cat_names

    print(f"线性模型预处理后特征数量: {X_train_proc.shape[1]}")

    return X_train_proc, X_val_proc, X_test_proc, fnames, None


def balance_data(X_train, y_train):
    smt = SMOTETomek(
        sampling_strategy=0.33,
        random_state=42
    )

    X_bal, y_bal = smt.fit_resample(X_train, y_train)
    print(f"平衡后训练集大小: {len(X_bal)} (正样本: {y_bal.mean():.4f})")

    return X_bal, y_bal


def enhanced_probability_calibration(model, name):
    if name in ["SVM", "KNN", "Ridge Regression"]:
        return CalibratedClassifierCV(model, method="isotonic", cv=5)
    return model


def perform_grid_search(model, param_grid, X, y, name, cat_indices=None):
    n_splits = 5
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    if name == "CatBoost":
        print("CatBoost 使用固定最佳参数 + 手动5折CV，避免GridSearchCV兼容性问题")

        params_list = list(ParameterGrid(param_grid))

        best_score = -np.inf
        best_params = None

        for params in params_list:
            fold_scores = []

            for fold, (train_idx, val_idx) in enumerate(cv.split(X, y), 1):
                X_tr = X.iloc[train_idx] if hasattr(X, "iloc") else X[train_idx]
                X_va = X.iloc[val_idx] if hasattr(X, "iloc") else X[val_idx]
                y_tr = y.iloc[train_idx] if hasattr(y, "iloc") else y[train_idx]
                y_va = y.iloc[val_idx] if hasattr(y, "iloc") else y[val_idx]

                cb_model = CatBoostClassifier(
                    random_state=42,
                    verbose=0,
                    thread_count=N_JOBS,
                    **params
                )

                cb_model.fit(X_tr, y_tr, cat_features=cat_indices)

                val_proba = cb_model.predict_proba(X_va)[:, 1]
                fold_auc = roc_auc_score(y_va, val_proba)
                fold_scores.append(fold_auc)

                print(f"CatBoost fold {fold} AUROC: {fold_auc:.4f}")

            mean_auc = float(np.mean(fold_scores))
            print(f"CatBoost params: {params}")
            print(f"CatBoost mean CV AUROC: {mean_auc:.4f}")

            if mean_auc > best_score:
                best_score = mean_auc
                best_params = params

        best_model = CatBoostClassifier(
            random_state=42,
            verbose=0,
            thread_count=N_JOBS,
            **best_params
        )

        best_model.fit(X, y, cat_features=cat_indices)

        return best_model, best_params, best_score

    grid_search = GridSearchCV(
        estimator=model,
        param_grid=param_grid,
        cv=cv,
        scoring="roc_auc",
        n_jobs=-1,
        verbose=2,
        refit=True,
        error_score="raise"
    )

    grid_search.fit(X, y)

    return grid_search.best_estimator_, grid_search.best_params_, grid_search.best_score_


def calculate_metrics(y_true, y_pred, y_proba, threshold):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
    npv = tn / (tn + fn) if (tn + fn) > 0 else 0

    return {
        "AUROC": roc_auc_score(y_true, y_proba),
        "LogLoss": log_loss(y_true, y_proba) if len(np.unique(y_proba)) > 1 else float("nan"),
        "Brier": brier_score_loss(y_true, y_proba),
        "Accuracy": accuracy_score(y_true, y_pred),
        "Precision": precision_score(y_true, y_pred, zero_division=0),
        "Recall": recall_score(y_true, y_pred, zero_division=0),
        "F1": f1_score(y_true, y_pred, zero_division=0),
        "Specificity": specificity,
        "NPV": npv,
        "BalancedAcc": balanced_accuracy_score(y_true, y_pred),
        "MCC": matthews_corrcoef(y_true, y_pred),
        "Kappa": cohen_kappa_score(y_true, y_pred),
        "MSE": mean_squared_error(y_true, y_proba),
        "MAE": mean_absolute_error(y_true, y_proba),
        "Threshold": threshold
    }


def evaluate_model_with_optimal_threshold(model, X_val, y_val, X_test, y_test, threshold_method="youden"):
    if hasattr(model, "predict_proba"):
        val_proba = model.predict_proba(X_val)[:, 1]
        test_proba = model.predict_proba(X_test)[:, 1]
    else:
        val_proba = model.decision_function(X_val)
        test_proba = model.decision_function(X_test)
        val_proba = (val_proba - val_proba.min()) / (val_proba.max() - val_proba.min())
        test_proba = (test_proba - test_proba.min()) / (test_proba.max() - test_proba.min())

    optimal_threshold = find_optimal_threshold(y_val, val_proba, method=threshold_method)
    print(f"使用阈值方法 '{threshold_method}' 找到的最佳阈值: {optimal_threshold:.4f}")

    val_pred = (val_proba >= optimal_threshold).astype(int)
    test_pred = (test_proba >= optimal_threshold).astype(int)

    val_metrics = calculate_metrics(y_val, val_pred, val_proba, optimal_threshold)
    test_metrics = calculate_metrics(y_test, test_pred, test_proba, optimal_threshold)

    return val_metrics, test_metrics, val_proba, test_proba, optimal_threshold


def plot_results(results_df, model_probas, y_val, y_test):
    test_results = results_df[results_df["Model"].str.contains("Test")].copy()
    test_results["Model"] = test_results["Model"].str.replace(r" \(Test\)$", "", regex=True)
    test_results.set_index("Model", inplace=True)

    plt.figure(figsize=(10, 8))

    for model_name, probas in model_probas.items():
        fpr, tpr, _ = roc_curve(y_test, probas)
        auc = roc_auc_score(y_test, probas)
        plt.plot(fpr, tpr, label=f"{model_name} (AUC = {auc:.3f})", linewidth=2.5)

    plt.plot([0, 1], [0, 1], "k--", label="Random")
    plt.xlabel("False Positive Rate", fontsize=12)
    plt.ylabel("True Positive Rate", fontsize=12)
    plt.title("ROC Curves Comparison (Test Set)", fontsize=14)
    plt.legend(loc="lower right", fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.savefig("roc_curves.png", dpi=300, bbox_inches="tight")
    plt.close()

    plt.figure(figsize=(15, 10))

    metrics_to_plot = ["AUROC", "Accuracy", "Precision", "Recall", "F1", "Specificity"]
    heatmap_data = test_results[metrics_to_plot].T

    sns.heatmap(
        heatmap_data,
        annot=True,
        cmap="YlOrRd",
        fmt=".3f",
        linewidths=0.5,
        linecolor="lightgray",
        cbar_kws={"label": "Score"}
    )

    plt.title("Model Performance Comparison (Test Set)", fontsize=14)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig("performance_heatmap.png", dpi=600, bbox_inches="tight")
    plt.close()


class DualLogger:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


def extract_best_params(log_content):
    best_params_dict = {}
    model_blocks = re.split(r"={50}\n处理模型: (.+?)\n={50}", log_content)

    for i in range(1, len(model_blocks), 2):
        model_name = model_blocks[i]
        model_log = model_blocks[i + 1]
        params_match = re.search(r"最佳参数: ({[\s\S]+?})\n", model_log)

        if params_match:
            params_str = params_match.group(1)
            try:
                best_params = ast.literal_eval(params_str)
                best_params_dict[model_name] = best_params
            except:
                best_params_dict[model_name] = {"error": "无法解析参数"}

    return best_params_dict


# ==================== 主程序 ====================
if __name__ == "__main__":
    if os.name == "nt":
        from multiprocessing import set_start_method
        set_start_method("spawn", force=True)

    original_categorical = [
        "chronic_heart_disease",
        "hypertension",
        "chronic_lung_disease",
        "chronic_neurological",
        "chronic_liver_disease",
        "chronic_kidney_disease",
        "diabetes",
        "vasoactive_agent",
        "neuroblock",
        "acei",
        "nsaid",
        "antibiotic",
        "invasive_vent_12h_24h_pre_dx"
    ]

    original_numerical = [
        "los_before_icu",
        "admission_age",
        "weight",
        "final_gcs_score",
        "charlson_comorbidity_index",
        "avg_heart_rate",
        "avg_mbp",
        "avg_resp_rate",
        "avg_temperature",
        "avg_spo2",
        "avg_glucose",
        "hr_before_sepsis_urineoutput",
        "avg_hematocrit",
        "avg_hemoglobin",
        "avg_mch",
        "avg_mchc",
        "avg_mcv",
        "avg_platelet",
        "avg_rbc",
        "avg_rdw",
        "avg_wbc",
        "avg_inr",
        "avg_pt",
        "avg_ptt",
        "avg_aniongap",
        "avg_bicarbonate",
        "avg_bun",
        "avg_calcium",
        "avg_chloride",
        "avg_creatinine",
        "avg_sodium",
        "avg_potassium",
        "avg_po2",
        "avg_pco2",
        "avg_ph",
        "avg_baseexcess",
        "avg_totalco2"
    ]

    CORE_CLINICAL_FEATURES = []

    log_filename = f"model_training_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    original_stdout = sys.stdout
    dual_logger = DualLogger(log_filename)
    sys.stdout = dual_logger

    print("=" * 80)
    print(f"开始SAD 7-day预测模型训练 - scale_pos_weight=[2,3] + 树模型sigmoid校准 - 日志保存在: {log_filename}")
    print("=" * 80)

    SAMPLE_SIZE = None

    print("加载数据...")
    X_train, X_val, X_test, y_train, y_val, y_test = load_and_split_data(
        DATA_FILE,
        sample_size=SAMPLE_SIZE
    )

    print("\n" + "=" * 50)
    print("阶段1: 初步特征筛选")
    print("=" * 50)

    initial_features = prefilter_features(
        X_train,
        numerical_features=original_numerical,
        categorical_features=original_categorical,
        threshold=0.85
    )

    print(f"初始特征筛选后保留特征数: {len(initial_features)}")

    if len(initial_features) < 20:
        print("警告：初始特征筛选后特征数不足20，使用所有特征")
        initial_features = X_train.columns.tolist()

    final_phase1_features = remove_high_correlation(
        X_train[initial_features],
        numerical_features=original_numerical,
        categorical_features=original_categorical,
        threshold=0.90,
        min_features=15
    )

    for core_feature in CORE_CLINICAL_FEATURES:
        if core_feature in X_train.columns and core_feature not in final_phase1_features:
            final_phase1_features.append(core_feature)

    print(f"加入核心临床特征后的Boruta候选特征数: {len(final_phase1_features)}")
    print("Boruta候选特征:", final_phase1_features)

    print("\n" + "=" * 50)
    print("阶段2: Boruta特征筛选")
    print("=" * 50)

    boruta_numerical = [f for f in final_phase1_features if f in original_numerical]
    boruta_categorical = [f for f in final_phase1_features if f in original_categorical]

    X_boruta, boruta_feature_map = prepare_data_for_boruta(
        X_train[final_phase1_features],
        numerical_features=boruta_numerical,
        categorical_features=boruta_categorical
    )

    print(f"Boruta输入特征数（OneHot后）: {X_boruta.shape[1]}")
    print(f"Boruta输入连续变量数: {len(boruta_numerical)}")
    print(f"Boruta输入分类变量数: {len(boruta_categorical)}")

    boruta_features, boruta_encoded_features, boruta_importance_df, boruta_model = boruta_feature_selection(
        X_boruta,
        y_train,
        feature_map=boruta_feature_map,
        min_features=15
    )

    final_phase2_features = list(set(boruta_features) | set(CORE_CLINICAL_FEATURES))

    new_numerical = []
    new_categorical = []

    all_features = original_numerical + original_categorical

    for feature in final_phase2_features:
        if feature in all_features:
            if feature in original_numerical:
                new_numerical.append(feature)
            elif feature in original_categorical:
                new_categorical.append(feature)

    numerical = new_numerical
    categorical = new_categorical

    print(f"\n最终特征数: {len(numerical) + len(categorical)}")
    print("数值特征:", numerical)
    print("分类特征:", categorical)

    print("\n" + "=" * 50)
    print("阶段3: 模型训练")
    print("=" * 50)

    models_info = [
        ("XGBoost", XGBClassifier(use_label_encoder=False, eval_metric="logloss", n_jobs=N_JOBS, tree_method="hist"), "tree"),
        ("CatBoost", CatBoostClassifier(random_state=42, thread_count=N_JOBS, verbose=0), "tree"),
        ("Logistic Regression", LogisticRegression(max_iter=1000), "linear"),
        ("Ridge Regression", RidgeClassifier(), "linear"),
        ("SVM", SVC(probability=True, random_state=42), "linear"),
        ("KNN", KNeighborsClassifier(n_jobs=N_JOBS), "knn"),
        ("LightGBM", LGBMClassifier(random_state=42, n_jobs=N_JOBS, device="cpu"), "tree"),
        ("Decision Tree", DecisionTreeClassifier(random_state=42), "tree"),
        ("Random Forest", RandomForestClassifier(random_state=42, n_jobs=N_JOBS), "tree")
    ]

    results = []
    model_probas = {}
    thresholds_info = {}

    TREE_MODELS_TO_CALIBRATE = [
        "XGBoost",
        "CatBoost",
        "LightGBM",
        "Random Forest",
        "Decision Tree"
    ]

    for name, model, mtype in models_info:
        print(f"\n{'=' * 50}")
        print(f"处理模型: {name}")
        print(f"{'=' * 50}")

        if name == "CatBoost":
            print("CatBoost 使用原始DataFrame并保留分类变量类型")

            X_train_sel = X_train[numerical + categorical].copy()
            X_val_sel = X_val[numerical + categorical].copy()
            X_test_sel = X_test[numerical + categorical].copy()

            for col in categorical:
                X_train_sel[col] = X_train_sel[col].astype(str)
                X_val_sel[col] = X_val_sel[col].astype(str)
                X_test_sel[col] = X_test_sel[col].astype(str)

            X_train_proc = X_train_sel
            X_val_proc = X_val_sel
            X_test_proc = X_test_sel

            fnames = numerical + categorical
            cat_indices = [fnames.index(col) for col in categorical]

        elif mtype == "tree":
            print(f"树模型 {name} 使用筛选后的统一特征集，并对分类变量进行OneHot编码")

            X_train_sel = X_train[numerical + categorical]
            X_val_sel = X_val[numerical + categorical]
            X_test_sel = X_test[numerical + categorical]

            X_train_proc, X_val_proc, X_test_proc, fnames, cat_indices = preprocess_data_for_linear(
                X_train_sel,
                X_val_sel,
                X_test_sel,
                numerical,
                categorical
            )

        else:
            print(f"非树模型 {name} 使用筛选后的特征")

            X_train_sel = X_train[numerical + categorical]
            X_val_sel = X_val[numerical + categorical]
            X_test_sel = X_test[numerical + categorical]

            X_train_proc, X_val_proc, X_test_proc, fnames, cat_indices = preprocess_data_for_linear(
                X_train_sel,
                X_val_sel,
                X_test_sel,
                numerical,
                categorical
            )

        if name in ["XGBoost", "CatBoost", "LightGBM"]:
            X_bal, y_bal = X_train_proc, y_train
            print(f"{name} 使用原始不平衡数据训练，搜索 scale_pos_weight=[2,3]")

        elif name == "KNN":
            X_bal, y_bal = X_train_proc, y_train
            print("KNN跳过过采样处理")

        else:
            X_bal, y_bal = balance_data(X_train_proc, y_train)

        if name in ["SVM", "KNN", "Ridge Regression"]:
            calibrated_model = enhanced_probability_calibration(model, name)
        else:
            calibrated_model = model

        try:
            print(f"开始参数搜索/固定参数复现: {name}...")

            best_model, best_params, cv_score = perform_grid_search(
                calibrated_model,
                param_grids[name],
                X_bal,
                y_bal,
                name,
                cat_indices=cat_indices
            )

            print(f"最佳参数: {best_params}")
            print(f"交叉验证AUC: {cv_score:.4f}")

            if name in TREE_MODELS_TO_CALIBRATE:
                print(f"{name} 使用验证集进行 sigmoid 概率校准")
                best_model_for_eval = SigmoidProbabilityCalibrator(best_model)
                best_model_for_eval.fit(X_val_proc, y_val)
                calibration_status = "sigmoid_validation"
            else:
                best_model_for_eval = best_model
                calibration_status = "none_or_internal"

            threshold_method = "f1" if name == "KNN" else "youden"

            val_metrics, test_metrics, _, test_proba, optimal_threshold = evaluate_model_with_optimal_threshold(
                best_model_for_eval,
                X_val_proc,
                y_val,
                X_test_proc,
                y_test,
                threshold_method=threshold_method
            )

            thresholds_info[name] = {
                "Threshold": optimal_threshold,
                "Method": threshold_method,
                "Calibration": calibration_status
            }

            val_metrics["Model"] = f"{name} (Validation)"
            test_metrics["Model"] = f"{name} (Test)"
            val_metrics["Calibration"] = calibration_status
            test_metrics["Calibration"] = calibration_status

            results.extend([val_metrics, test_metrics])
            model_probas[name] = test_proba

            print(f"\n验证集结果 - {name}:")
            print(
                f"阈值: {optimal_threshold:.4f}, "
                f"AUC: {val_metrics['AUROC']:.4f}, "
                f"Brier: {val_metrics['Brier']:.4f}, "
                f"F1: {val_metrics['F1']:.4f}, "
                f"准确率: {val_metrics['Accuracy']:.4f}"
            )

            print(f"测试集结果 - {name}:")
            print(
                f"阈值: {optimal_threshold:.4f}, "
                f"AUC: {test_metrics['AUROC']:.4f}, "
                f"Brier: {test_metrics['Brier']:.4f}, "
                f"F1: {test_metrics['F1']:.4f}, "
                f"准确率: {test_metrics['Accuracy']:.4f}"
            )

        except Exception as e:
            print(f"处理 {name} 时出错: {str(e)}")
            continue

    if results:
        results_df = pd.DataFrame(results)
        results_df.to_csv("model_results_with_thresholds.csv", index=False)

        thresholds_df = pd.DataFrame(thresholds_info).T
        thresholds_df.to_csv("model_optimal_thresholds.csv")

        print("\n结果已保存至 model_results_with_thresholds.csv")
        print("最佳阈值信息已保存至 model_optimal_thresholds.csv")

        print("生成可视化图表...")
        plot_results(results_df, model_probas, y_val, y_test)
        print("图表已保存为 roc_curves.png 和 performance_heatmap.png")

    else:
        print("\n没有成功处理的模型")

    print("\n训练完成!")

    sys.stdout = original_stdout
    dual_logger.close()

    print(f"训练日志已保存至: {log_filename}")

    try:
        with open(log_filename, "r", encoding="utf-8") as f:
            log_content = f.read()

        best_params = extract_best_params(log_content)
        params_json_file = f"model_best_parameters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(params_json_file, "w", encoding="utf-8") as f:
            json.dump(best_params, f, indent=2, ensure_ascii=False)

        print(f"参数文件已保存: {params_json_file}")

    except Exception as e:
        print(f"提取参数时出错: {str(e)}")

# %% Original notebook code cell 8
# ==================== Boruta Native Z-value Boxplot + Importance Barplot + Selection Summary Plot ====================
# 前提：
# 主程序已经修改并运行完成，且存在：
# X_boruta, boruta_feature_map, boruta_features,
# boruta_encoded_features, boruta_importance_df, boruta_model
#
# 功能：
# 1. Boruta 原生 Z-value boxplot
# 2. Boruta 已确认变量的 aggregated RF importance barplot
# 3. Boruta variable selection summary plot，展示 Confirmed / Tentative / Rejected 变量数
# 4. 输出 Confirmed / Tentative / Rejected 原始变量清单

import os
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


# ==================== 0. 输出目录与绘图风格 ====================
output_dir = "Boruta_native_visualization"
os.makedirs(output_dir, exist_ok=True)

plt.rcParams["font.family"] = "Arial"
plt.rcParams["axes.linewidth"] = 1.0
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["ps.fonttype"] = 42


# 如果前面没有定义 display_feature_name，则使用原始变量名
if "display_feature_name" not in globals():
    def display_feature_name(x):
        return x


# ==================== 1. 检查变量；若内存中没有 boruta_model，则尝试读取保存文件 ====================
required_vars = [
    "X_boruta",
    "boruta_feature_map",
    "boruta_features",
    "boruta_encoded_features",
    "boruta_importance_df"
]

missing_vars = [var for var in required_vars if var not in globals()]

if len(missing_vars) > 0:
    raise NameError(
        "以下变量不存在，请先运行主程序到 Boruta 特征筛选结束：\n"
        + ", ".join(missing_vars)
    )

if "boruta_model" not in globals():
    model_path = os.path.join("Boruta_native_results", "boruta_model.pkl")

    if os.path.exists(model_path):
        with open(model_path, "rb") as f:
            boruta_model = pickle.load(f)
        print(f"已从文件读取 Boruta 原生模型: {model_path}")
    else:
        raise NameError(
            "未检测到 boruta_model，且未找到 Boruta_native_results/boruta_model.pkl。"
            "请先运行修改后的主程序保存 Boruta 原生对象。"
        )

if not hasattr(boruta_model, "importance_history_"):
    raise AttributeError("boruta_model 中不存在 importance_history_，请确认保存的是 BorutaPy 对象。")

print("已检测到 Boruta 原生对象和主程序 Boruta 变量。")
print(f"Boruta确认原始变量数: {len(boruta_features)}")
print(f"Boruta确认编码变量数: {len(boruta_encoded_features)}")


# ==================== 2. 聚合主程序 Boruta Importance ====================
def aggregate_main_boruta_importance(
    boruta_importance_df,
    feature_map,
    boruta_features,
    boruta_encoded_features,
    output_dir
):
    encoded_df = boruta_importance_df.copy()

    if "Encoded_Feature" not in encoded_df.columns:
        raise ValueError("boruta_importance_df 缺少 Encoded_Feature 列")

    if "Importance" not in encoded_df.columns:
        raise ValueError("boruta_importance_df 缺少 Importance 列")

    encoded_df["Original_Feature"] = encoded_df["Encoded_Feature"].map(feature_map)
    encoded_df["Original_Feature"] = encoded_df["Original_Feature"].fillna(
        encoded_df["Encoded_Feature"]
    )

    encoded_df["Original_Feature_Display"] = encoded_df["Original_Feature"].map(display_feature_name)

    encoded_df["Selected_by_Main_Boruta_Encoded"] = encoded_df["Encoded_Feature"].isin(
        boruta_encoded_features
    )

    encoded_df["Selected_by_Main_Boruta_Original"] = encoded_df["Original_Feature"].isin(
        boruta_features
    )

    original_df = (
        encoded_df
        .groupby("Original_Feature", as_index=False)
        .agg(
            Importance=("Importance", "sum"),
            Max_Encoded_Importance=("Importance", "max"),
            Selected_by_Main_Boruta=("Selected_by_Main_Boruta_Original", "max"),
            Any_Encoded_Selected=("Selected_by_Main_Boruta_Encoded", "max")
        )
        .sort_values("Importance", ascending=False)
        .reset_index(drop=True)
    )

    original_df["Original_Feature_Display"] = original_df["Original_Feature"].map(display_feature_name)

    encoded_df.to_csv(
        os.path.join(output_dir, "main_boruta_encoded_feature_importance.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    original_df.to_csv(
        os.path.join(output_dir, "main_boruta_original_feature_importance.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    return original_df, encoded_df


main_boruta_original_importance_df, main_boruta_encoded_importance_df = (
    aggregate_main_boruta_importance(
        boruta_importance_df=boruta_importance_df,
        feature_map=boruta_feature_map,
        boruta_features=boruta_features,
        boruta_encoded_features=boruta_encoded_features,
        output_dir=output_dir
    )
)


# ==================== 3. 提取 Boruta Confirmed / Tentative / Rejected 状态 ====================
def extract_boruta_selection_status(
    boruta_model,
    X_boruta,
    feature_map,
    boruta_features,
    output_dir="Boruta_native_visualization"
):
    """
    基于 BorutaPy 对象提取编码变量层面的 Confirmed / Tentative / Rejected 状态，
    再聚合到原始变量层面。

    原始变量聚合规则：
    1. 只要任一编码变量为 Confirmed，则原始变量为 Confirmed
    2. 若无 Confirmed，但任一编码变量为 Tentative，则原始变量为 Tentative
    3. 其余为 Rejected
    """

    if not hasattr(boruta_model, "support_"):
        raise AttributeError("boruta_model 中不存在 support_，无法识别 Confirmed 特征。")

    support = np.asarray(boruta_model.support_).astype(bool)

    if support.shape[0] != X_boruta.shape[1]:
        raise ValueError(
            f"support_长度({support.shape[0]}) 与 X_boruta列数({X_boruta.shape[1]}) 不一致。"
        )

    if hasattr(boruta_model, "support_weak_"):
        support_weak = np.asarray(boruta_model.support_weak_).astype(bool)
    else:
        support_weak = np.zeros_like(support, dtype=bool)

    encoded_status_df = pd.DataFrame({
        "Encoded_Feature": X_boruta.columns,
        "Confirmed_Encoded": support,
        "Tentative_Encoded": support_weak
    })

    encoded_status_df["Status_Encoded"] = np.select(
        [
            encoded_status_df["Confirmed_Encoded"],
            encoded_status_df["Tentative_Encoded"]
        ],
        [
            "Confirmed",
            "Tentative"
        ],
        default="Rejected"
    )

    encoded_status_df["Original_Feature"] = encoded_status_df["Encoded_Feature"].map(feature_map)
    encoded_status_df["Original_Feature"] = encoded_status_df["Original_Feature"].fillna(
        encoded_status_df["Encoded_Feature"]
    )
    encoded_status_df["Original_Feature_Display"] = encoded_status_df["Original_Feature"].map(display_feature_name)

    original_status_df = (
        encoded_status_df
        .groupby("Original_Feature", as_index=False)
        .agg(
            Any_Confirmed=("Confirmed_Encoded", "max"),
            Any_Tentative=("Tentative_Encoded", "max"),
            Encoded_Feature_Count=("Encoded_Feature", "count")
        )
    )

    original_status_df["Status"] = np.select(
        [
            original_status_df["Any_Confirmed"],
            (~original_status_df["Any_Confirmed"]) & original_status_df["Any_Tentative"]
        ],
        [
            "Confirmed",
            "Tentative"
        ],
        default="Rejected"
    )

    # 与主程序 boruta_features 对齐：如主程序确认，则强制设为 Confirmed
    original_status_df.loc[
        original_status_df["Original_Feature"].isin(boruta_features),
        "Status"
    ] = "Confirmed"

    original_status_df["Original_Feature_Display"] = original_status_df["Original_Feature"].map(display_feature_name)

    status_order = ["Confirmed", "Tentative", "Rejected"]
    original_status_df["Status"] = pd.Categorical(
        original_status_df["Status"],
        categories=status_order,
        ordered=True
    )

    status_summary_df = (
        original_status_df
        .groupby("Status", observed=False)
        .agg(Number_of_variables=("Original_Feature", "count"))
        .reset_index()
    )

    encoded_status_df.to_csv(
        os.path.join(output_dir, "boruta_encoded_feature_selection_status.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    original_status_df.to_csv(
        os.path.join(output_dir, "boruta_original_feature_selection_status.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    status_summary_df.to_csv(
        os.path.join(output_dir, "boruta_selection_summary.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    return encoded_status_df, original_status_df, status_summary_df


boruta_encoded_status_df, boruta_original_status_df, boruta_status_summary_df = (
    extract_boruta_selection_status(
        boruta_model=boruta_model,
        X_boruta=X_boruta,
        feature_map=boruta_feature_map,
        boruta_features=boruta_features,
        output_dir=output_dir
    )
)


# ==================== 4. 绘制 Boruta 筛选结果汇总图：更适合投稿拼图 ====================
def plot_boruta_selection_process(
    status_summary_df,
    original_status_df,
    output_dir="Boruta_native_visualization"
):
    """
    绘制 Boruta variable selection summary：
    Confirmed / Tentative / Rejected 变量数量及比例。
    """

    plot_df = status_summary_df.copy()

    status_order = ["Confirmed", "Tentative", "Rejected"]
    plot_df["Status"] = pd.Categorical(
        plot_df["Status"],
        categories=status_order,
        ordered=True
    )
    plot_df = plot_df.sort_values("Status").reset_index(drop=True)

    total_n = int(plot_df["Number_of_variables"].sum())
    plot_df["Percentage"] = plot_df["Number_of_variables"] / total_n * 100

    # 黑白/灰阶风格，便于SCI拼图
    grayscale_palette = {
        "Confirmed": "#1A1A1A",
        "Tentative": "#7F7F7F",
        "Rejected": "#D9D9D9"
    }

    fig, ax = plt.subplots(figsize=(7.2, 5.6))

    bars = sns.barplot(
        data=plot_df,
        x="Status",
        y="Number_of_variables",
        order=status_order,
        palette=grayscale_palette,
        edgecolor="black",
        linewidth=1.0,
        ax=ax
    )

    max_y = plot_df["Number_of_variables"].max()
    y_offset = max(max_y * 0.045, 0.5)

    for p, (_, row) in zip(ax.patches, plot_df.iterrows()):
        height = p.get_height()
        ax.text(
            p.get_x() + p.get_width() / 2,
            height + y_offset,
            f"{int(row['Number_of_variables'])}\n({row['Percentage']:.1f}%)",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
            color="black"
        )

    ax.set_xlabel("Boruta decision", fontsize=13, fontweight="bold")
    ax.set_ylabel("Number of variables", fontsize=13, fontweight="bold")

    # 投稿拼图时建议不用大标题；图题放在figure legend里
    ax.set_title("")

    ax.set_ylim(0, max_y + y_offset * 4.0)
    ax.tick_params(axis="x", labelsize=12)
    ax.tick_params(axis="y", labelsize=11)

    for label in ax.get_xticklabels():
        label.set_fontweight("bold")

    ax.grid(axis="y", linestyle="--", linewidth=0.8, alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.text(
        0.98,
        0.96,
        f"Total variables: {total_n}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=11,
        fontweight="bold",
        bbox=dict(
            boxstyle="round,pad=0.35",
            facecolor="white",
            edgecolor="black",
            linewidth=0.8
        )
    )

    plt.tight_layout()

    fig_path_png = os.path.join(output_dir, "boruta_variable_selection_summary.png")
    fig_path_tif = os.path.join(output_dir, "boruta_variable_selection_summary.tif")
    fig_path_pdf = os.path.join(output_dir, "boruta_variable_selection_summary.pdf")

    plt.savefig(fig_path_png, dpi=600, bbox_inches="tight")
    plt.savefig(fig_path_tif, dpi=600, bbox_inches="tight")
    plt.savefig(fig_path_pdf, bbox_inches="tight")
    plt.show()

    print(f"Boruta筛选结果汇总图已保存: {fig_path_png}")
    print(f"Boruta筛选结果汇总图TIFF已保存: {fig_path_tif}")
    print(f"Boruta筛选结果汇总图PDF已保存: {fig_path_pdf}")

    return plot_df


boruta_selection_process_plot_df = plot_boruta_selection_process(
    status_summary_df=boruta_status_summary_df,
    original_status_df=boruta_original_status_df,
    output_dir=output_dir
)


# ==================== 5. 直接读取 Boruta 原生 importance_history_ ====================
def extract_native_boruta_importance_history(
    boruta_model,
    X_boruta,
    feature_map,
    boruta_features,
    aggregation_method="max",
    output_dir="Boruta_native_visualization"
):
    importance_history = boruta_model.importance_history_

    if importance_history.shape[1] != X_boruta.shape[1]:
        raise ValueError(
            f"importance_history_列数({importance_history.shape[1]}) "
            f"与 X_boruta列数({X_boruta.shape[1]}) 不一致。"
        )

    importance_history_df = pd.DataFrame(
        importance_history,
        columns=X_boruta.columns
    )

    importance_history_df["Iteration"] = np.arange(
        1,
        len(importance_history_df) + 1
    )

    wide_path = os.path.join(
        output_dir,
        "boruta_native_importance_history_wide.csv"
    )

    importance_history_df.to_csv(
        wide_path,
        index=False,
        encoding="utf-8-sig"
    )

    z_long_df = importance_history_df.melt(
        id_vars="Iteration",
        var_name="Encoded_Feature",
        value_name="Z_value"
    )

    z_long_df["Original_Feature"] = z_long_df["Encoded_Feature"].map(feature_map)
    z_long_df["Original_Feature"] = z_long_df["Original_Feature"].fillna(
        z_long_df["Encoded_Feature"]
    )

    z_long_df["Original_Feature_Display"] = z_long_df["Original_Feature"].map(display_feature_name)

    z_long_df["Selected_by_Main_Boruta"] = z_long_df["Original_Feature"].isin(
        boruta_features
    )

    if aggregation_method == "max":
        z_history_df = (
            z_long_df
            .groupby(
                ["Iteration", "Original_Feature", "Selected_by_Main_Boruta"],
                as_index=False
            )["Z_value"]
            .max()
        )
    elif aggregation_method == "mean":
        z_history_df = (
            z_long_df
            .groupby(
                ["Iteration", "Original_Feature", "Selected_by_Main_Boruta"],
                as_index=False
            )["Z_value"]
            .mean()
        )
    elif aggregation_method == "sum":
        z_history_df = (
            z_long_df
            .groupby(
                ["Iteration", "Original_Feature", "Selected_by_Main_Boruta"],
                as_index=False
            )["Z_value"]
            .sum()
        )
    else:
        raise ValueError("aggregation_method 只能是 'max', 'mean', 或 'sum'")

    long_path = os.path.join(
        output_dir,
        "boruta_native_importance_history_long.csv"
    )

    z_history_df.to_csv(
        long_path,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"Boruta原生importance history宽表已保存: {wide_path}")
    print(f"Boruta原生importance history长表已保存: {long_path}")

    return z_history_df, importance_history_df


boruta_native_z_history_df, boruta_native_z_history_wide_df = (
    extract_native_boruta_importance_history(
        boruta_model=boruta_model,
        X_boruta=X_boruta,
        feature_map=boruta_feature_map,
        boruta_features=boruta_features,
        aggregation_method="max",
        output_dir=output_dir
    )
)


# ==================== 6. 绘制箱线图：从左到右按 median Z-value 递增 ====================
def plot_boruta_native_z_boxplot(
    z_history_df,
    boruta_features,
    top_n=15,
    output_dir="Boruta_native_visualization"
):
    selected_z = z_history_df[
        z_history_df["Original_Feature"].isin(boruta_features)
    ].copy()

    if selected_z.empty:
        raise ValueError("没有找到 Boruta 确认变量对应的原生 Z-value 数据")

    z_summary = (
        selected_z
        .groupby("Original_Feature", as_index=False)
        .agg(
            Median_Z=("Z_value", "median"),
            Mean_Z=("Z_value", "mean"),
            Q1_Z=("Z_value", lambda x: np.percentile(x, 25)),
            Q3_Z=("Z_value", lambda x: np.percentile(x, 75)),
            Min_Z=("Z_value", "min"),
            Max_Z=("Z_value", "max")
        )
        .sort_values("Median_Z", ascending=False)
        .reset_index(drop=True)
    )

    z_summary["Original_Feature_Display"] = z_summary["Original_Feature"].map(display_feature_name)

    top_features = z_summary.head(top_n)["Original_Feature"].tolist()

    feature_order = (
        z_summary[z_summary["Original_Feature"].isin(top_features)]
        .sort_values("Median_Z", ascending=True)["Original_Feature"]
        .tolist()
    )

    plot_df = selected_z[
        selected_z["Original_Feature"].isin(feature_order)
    ].copy()

    feature_order_display = [display_feature_name(f) for f in feature_order]
    plot_df["Original_Feature_Display"] = plot_df["Original_Feature"].map(display_feature_name)

    plot_df.to_csv(
        os.path.join(output_dir, "boruta_native_z_values_top15.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    z_summary.to_csv(
        os.path.join(output_dir, "boruta_native_z_value_summary.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    fig, ax = plt.subplots(figsize=(18, 7))

    sns.boxplot(
        data=plot_df,
        x="Original_Feature_Display",
        y="Z_value",
        order=feature_order_display,
        width=0.6,
        showcaps=True,
        showfliers=False,
        boxprops=dict(facecolor="#BDBDBD", edgecolor="black", alpha=0.85),
        whiskerprops=dict(color="black", linewidth=1),
        medianprops=dict(color="black", linewidth=2),
        capprops=dict(color="black", linewidth=1),
        ax=ax
    )

    sns.stripplot(
        data=plot_df,
        x="Original_Feature_Display",
        y="Z_value",
        order=feature_order_display,
        color="black",
        size=2,
        alpha=0.22,
        jitter=0.25,
        ax=ax
    )

    ax.axhline(
        0,
        linestyle="--",
        linewidth=1.2,
        color="gray",
        alpha=0.8
    )

    ax.set_title("")
    ax.set_xlabel("Variable", fontsize=14, fontweight="bold")
    ax.set_ylabel("Z-value", fontsize=14, fontweight="bold")

    ax.tick_params(axis="x", labelrotation=55, labelsize=11)
    ax.tick_params(axis="y", labelsize=11)

    for label in ax.get_xticklabels():
        label.set_ha("right")

    ax.grid(axis="y", linestyle="--", linewidth=0.8, alpha=0.2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()

    fig_path_png = os.path.join(output_dir, "boruta_native_z_value_boxplot_top15.png")
    fig_path_tif = os.path.join(output_dir, "boruta_native_z_value_boxplot_top15.tif")
    fig_path_pdf = os.path.join(output_dir, "boruta_native_z_value_boxplot_top15.pdf")

    plt.savefig(fig_path_png, dpi=600, bbox_inches="tight")
    plt.savefig(fig_path_tif, dpi=600, bbox_inches="tight")
    plt.savefig(fig_path_pdf, bbox_inches="tight")
    plt.show()

    print(f"Boruta原生 Z-value 箱线图已保存: {fig_path_png}")
    print(f"Boruta原生 Z-value 箱线图TIFF已保存: {fig_path_tif}")
    print(f"Boruta原生 Z-value 箱线图PDF已保存: {fig_path_pdf}")

    return plot_df, z_summary


boruta_native_z_top15_df, boruta_native_z_summary_df = plot_boruta_native_z_boxplot(
    z_history_df=boruta_native_z_history_df,
    boruta_features=boruta_features,
    top_n=15,
    output_dir=output_dir
)


# ==================== 7. 绘制柱状图：从上到下 Importance 递减 ====================
def plot_main_boruta_importance_barplot(
    importance_df,
    boruta_features,
    top_n=15,
    output_dir="Boruta_native_visualization"
):
    plot_df = importance_df[
        importance_df["Original_Feature"].isin(boruta_features)
    ].copy()

    if plot_df.empty:
        raise ValueError("没有找到 Boruta 确认变量对应的 importance 数据")

    plot_df = (
        plot_df
        .sort_values("Importance", ascending=False)
        .head(top_n)
        .copy()
    )

    # 为了让最高重要性显示在最上方，横向条形图使用反向顺序
    plot_df = plot_df.sort_values("Importance", ascending=True).copy()

    feature_order = plot_df["Original_Feature"].tolist()
    feature_order_display = [display_feature_name(f) for f in feature_order]
    plot_df["Original_Feature_Display"] = plot_df["Original_Feature"].map(display_feature_name)

    plot_df["Original_Feature_Display"] = pd.Categorical(
        plot_df["Original_Feature_Display"],
        categories=feature_order_display,
        ordered=True
    )

    plot_df.to_csv(
        os.path.join(output_dir, "main_boruta_importance_top15.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    fig, ax = plt.subplots(figsize=(10, 7))

    sns.barplot(
        data=plot_df,
        x="Importance",
        y="Original_Feature_Display",
        order=feature_order_display,
        color="#4D4D4D",
        edgecolor="black",
        linewidth=0.8,
        ax=ax
    )

    # 添加数值标签
    max_importance = plot_df["Importance"].max()
    for p in ax.patches:
        width = p.get_width()
        ax.text(
            width + max_importance * 0.015,
            p.get_y() + p.get_height() / 2,
            f"{width:.3f}",
            va="center",
            ha="left",
            fontsize=10,
            color="black"
        )

    ax.set_title("")
    ax.set_xlabel("Aggregated RF importance", fontsize=13, fontweight="bold")
    ax.set_ylabel("Variable", fontsize=13, fontweight="bold")

    ax.tick_params(axis="x", labelsize=11)
    ax.tick_params(axis="y", labelsize=11)

    ax.set_xlim(0, max_importance * 1.15)

    ax.grid(axis="x", linestyle="--", linewidth=0.8, alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()

    fig_path_png = os.path.join(output_dir, "main_boruta_original_importance_top15.png")
    fig_path_tif = os.path.join(output_dir, "main_boruta_original_importance_top15.tif")
    fig_path_pdf = os.path.join(output_dir, "main_boruta_original_importance_top15.pdf")

    plt.savefig(fig_path_png, dpi=600, bbox_inches="tight")
    plt.savefig(fig_path_tif, dpi=600, bbox_inches="tight")
    plt.savefig(fig_path_pdf, bbox_inches="tight")
    plt.show()

    print(f"Boruta importance 柱状图已保存: {fig_path_png}")
    print(f"Boruta importance 柱状图TIFF已保存: {fig_path_tif}")
    print(f"Boruta importance 柱状图PDF已保存: {fig_path_pdf}")

    return plot_df.sort_values("Importance", ascending=False).reset_index(drop=True)


main_boruta_importance_top15_df = plot_main_boruta_importance_barplot(
    importance_df=main_boruta_original_importance_df,
    boruta_features=boruta_features,
    top_n=15,
    output_dir=output_dir
)


# ==================== 8. 显示结果 ====================
print("\nBoruta筛选过程汇总：")
display(boruta_status_summary_df)

print("\nBoruta Confirmed / Tentative / Rejected 原始变量清单：")
display(
    boruta_original_status_df
    .sort_values(["Status", "Original_Feature"])
    [["Original_Feature", "Original_Feature_Display", "Status", "Encoded_Feature_Count"]]
)

print("\nBoruta确认变量：")
print(boruta_features)

print("\nBoruta原生 Z-value summary Top 15：")
display(boruta_native_z_summary_df.head(15))

print("\nImportance Top 15：")
display(main_boruta_importance_top15_df)

print("\n绘图完成。")

# %% Original notebook code cell 9
def plot_pr_curves(model_probas, y_test):
    """绘制专业PR曲线（按AUPRC值降序排列），标记每个模型的最优阈值点"""
    from sklearn.metrics import precision_recall_curve, auc as auc_func
    
    # 计算每个模型的AUPRC并排序
    models_auprc = {}
    for name, probas in model_probas.items():
        precision, recall, _ = precision_recall_curve(y_test, probas)
        auprc = auc_func(recall, precision)
        models_auprc[name] = auprc
    
    # 按AUPRC降序排序
    sorted_models = sorted(models_auprc.items(), key=lambda x: x[1], reverse=True)
    
    # Lancet配色方案
    lancet_palette = ['#00468B', '#ED0000', '#42B540', '#0099B4', '#925E9F', '#FDAF91', '#AD002A', '#1B1919', '#FFCC00']
    marker_symbols = ['o', 's', 'D', '^', 'v', '<', '>', 'p', '*', 'X']  # 不同形状的标记
    
    # 设置Times New Roman字体
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman'] + plt.rcParams['font.serif']
    plt.rcParams['axes.edgecolor'] = '#444444'
    plt.rcParams['axes.linewidth'] = 1.2
    
    # 创建图形
    plt.figure(figsize=(12, 9))
    
    # 使用白色网格背景
    plt.grid(True, color='#EEEEEE', linestyle='-', which='both', alpha=0.8)
    
    # 绘制基准线（正样本比例）
    baseline = np.mean(y_test)
    plt.axhline(y=baseline, color='k', linestyle='--', alpha=0.7, linewidth=1.5, label='Baseline')
    
    # 创建图例信息列表
    legend_handles = []
    legend_labels = []
    
    # 按AUPRC降序绘制每个模型的PR曲线
    for idx, (model_name, auprc) in enumerate(sorted_models):
        precision, recall, thresholds = precision_recall_curve(y_test, model_probas[model_name])
        
        # 计算每个点到左上角(0,1)的距离
        distances = (1 - recall)**2 + (1 - precision)**2
        
        # 找到距离最小的点 - 最接近左上角的点
        optimal_idx = np.argmin(distances)
        optimal_recall = recall[optimal_idx]
        optimal_precision = precision[optimal_idx]
        optimal_threshold = thresholds[optimal_idx]
        
        # 绘制PR曲线
        line, = plt.plot(recall, precision, 
                         label=f'{model_name} (AUPRC = {auprc:.3f})', 
                         color=lancet_palette[idx % len(lancet_palette)],
                         linewidth=2.5)
        
        # 保存图例句柄
        legend_handles.append(line)
        legend_labels.append(f'{model_name} (AUPRC={auprc:.3f}, Threshold={optimal_threshold:.3f})')
        
        # 标记最优阈值点
        plt.scatter(optimal_recall, optimal_precision, 
                   s=100,  # 点的大小
                   color=lancet_palette[idx % len(lancet_palette)],
                   marker=marker_symbols[idx % len(marker_symbols)],  # 不同模型使用不同标记形状
                   edgecolors='black',
                   zorder=5)  # 确保点在线上方
    
    # 添加参考线 - 最佳性能参考点 (0,1)
    plt.scatter(0, 1, s=200, marker='*', color='gold', edgecolors='black', label='Ideal Point (0,1)')
    legend_handles.append(plt.Line2D([0], [0], marker='*', color='w', markerfacecolor='gold', markersize=12, markeredgecolor='black'))
    legend_labels.append('Ideal Point (0,1)')
    
    # Lancet风格的图标题和标签
    plt.title('Precision-Recall Curves with Optimal Threshold Points', 
              fontsize=16, pad=15)
    plt.xlabel('Recall (Sensitivity)', fontsize=14)
    plt.ylabel('Precision (Positive Predictive Value)', fontsize=14)
    
    # Lancet风格的图例和网格
    plt.legend(legend_handles, legend_labels, loc='lower left', fontsize=10, 
               frameon=True, facecolor='white', framealpha=0.95, bbox_to_anchor=(0.05, 0.05))
    
    # 坐标轴设置
    plt.xlim([-0.005, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    
    # 保存为高分辨率TIFF文件
    plt.savefig('pr_curves_optimized.tiff', dpi=600, bbox_inches='tight', format='tiff')
    print("已生成优化阈值的PR曲线图: 'pr_curves_optimized.tiff'")
    plt.close()

def plot_auc_curves(model_probas, y_test):
    """绘制ROC曲线比较图（按AUROC值降序排列）"""
    # 计算每个模型的AUROC并排序
    models_auc = {}
    for name, probas in model_probas.items():
        auc = roc_auc_score(y_test, probas)
        models_auc[name] = auc
    
    # 按AUROC降序排序
    sorted_models = sorted(models_auc.items(), key=lambda x: x[1], reverse=True)
    
    # Lancet配色方案
    lancet_palette = ['#00468B', '#ED0000', '#42B540', '#0099B4', '#925E9F', '#FDAF91', '#AD002A', '#1B1919', '#FFCC00']
    
    # 设置Times New Roman字体
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman'] + plt.rcParams['font.serif']
    plt.rcParams['axes.edgecolor'] = '#444444'
    plt.rcParams['axes.linewidth'] = 1.2
    
    # 创建图形
    plt.figure(figsize=(12, 9))
    
    # 使用白色网格背景
    plt.grid(True, color='#EEEEEE', linestyle='-', which='both', alpha=0.8)
    
    # 绘制基准线（随机模型）
    plt.plot([0, 1], [0, 1], 'k--', alpha=0.7, linewidth=1.5, label='Random')
    
    # 按AUROC降序绘制每个模型的ROC曲线
    for idx, (model_name, auc) in enumerate(sorted_models):
        fpr, tpr, _ = roc_curve(y_test, model_probas[model_name])
        plt.plot(fpr, tpr, 
                 label=f'{model_name} (AUROC = {auc:.3f})', 
                 color=lancet_palette[idx % len(lancet_palette)],
                 linewidth=2.5)
    
    # Lancet风格的图标题和标签
    plt.title('ROC Curves Comparison', fontsize=16, pad=15)
    plt.xlabel('False Positive Rate', fontsize=14)
    plt.ylabel('True Positive Rate', fontsize=14)
    
    # Lancet风格的图例和网格
    plt.legend(loc='lower right', fontsize=10, 
               frameon=True, facecolor='white', framealpha=0.95)
    
    # 坐标轴设置
    plt.xlim([-0.005, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    
    # 保存为高分辨率TIFF文件
    plt.savefig('roc_curves.tiff', dpi=600, bbox_inches='tight', format='tiff')
    print("已生成ROC曲线图: 'roc_curves.tiff'")
    plt.close()

def plot_calibration_curves(model_probas, y_test):
    """绘制校准曲线"""
    from sklearn.calibration import calibration_curve
    
    # 计算每个模型的AUROC并排序
    models_auc = {name: roc_auc_score(y_test, probas) for name, probas in model_probas.items()}
    sorted_models = sorted(models_auc.items(), key=lambda x: x[1], reverse=True)
    
    # Lancet配色方案
    lancet_palette = ['#00468B', '#ED0000', '#42B540', '#0099B4', '#925E9F', '#FDAF91', '#AD002A', '#1B1919', '#FFCC00']
    
    # 设置Times New Roman字体
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman'] + plt.rcParams['font.serif']
    plt.rcParams['axes.edgecolor'] = '#444444'
    plt.rcParams['axes.linewidth'] = 1.2
    
    # 创建图形
    plt.figure(figsize=(12, 9))
    
    # 使用白色网格背景
    plt.grid(True, color='#EEEEEE', linestyle='-', which='both', alpha=0.8)
    
    # 绘制基准线（完美校准）
    plt.plot([0, 1], [0, 1], 'k--', alpha=0.7, linewidth=1.5, label='Perfectly Calibrated')
    
    # 按AUROC降序绘制每个模型的校准曲线
    for idx, (model_name, auc) in enumerate(sorted_models):
        prob_true, prob_pred = calibration_curve(y_test, model_probas[model_name], n_bins=10)
        plt.plot(prob_pred, prob_true, 's-', 
                 label=f'{model_name} (AUROC = {auc:.3f})', 
                 color=lancet_palette[idx % len(lancet_palette)])
    
    # Lancet风格的图标题和标签
    plt.title('Calibration Curves', fontsize=16, pad=15)
    plt.xlabel('Mean Predicted Probability', fontsize=14)
    plt.ylabel('Fraction of Positives', fontsize=14)
    
    # Lancet风格的图例和网格
    plt.legend(loc='lower right', fontsize=10, 
               frameon=True, facecolor='white', framealpha=0.95)
    
    # 坐标轴设置
    plt.xlim([-0.005, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    
    # 保存为高分辨率TIFF文件
    plt.savefig('calibration_curves.tiff', dpi=600, bbox_inches='tight', format='tiff')
    print("已生成校准曲线图: 'calibration_curves.tiff'")
    plt.close()

# 在原有代码中添加调用
print("生成专业可视化图表...")
plot_auc_curves(model_probas, y_test)  # 绘制ROC曲线（按AUROC降序）
plot_calibration_curves(model_probas, y_test)  # 绘制校准曲线（按AUROC降序）
plot_pr_curves(model_probas, y_test)  # 绘制PR曲线（按AUPRC降序）

# %% Original notebook code cell 10
def plot_dca_curves(model_probas, y_test):
    """绘制决策曲线分析（DCA）曲线（按AUROC值降序排列）"""
    import numpy as np
    
    # 计算每个模型的AUROC并排序
    models_auc = {}
    for name, probas in model_probas.items():
        auc = roc_auc_score(y_test, probas)
        models_auc[name] = auc
    
    # 按AUROC降序排序
    sorted_models = sorted(models_auc.items(), key=lambda x: x[1], reverse=True)
    
    # Lancet配色方案
    lancet_palette = ['#00468B', '#ED0000', '#42B540', '#0099B4', '#925E9F', 
                      '#FDAF91', '#AD002A', '#1B1919', '#FFCC00']
    
    # 设置Times New Roman字体
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman'] + plt.rcParams['font.serif']
    plt.rcParams['axes.edgecolor'] = '#444444'
    plt.rcParams['axes.linewidth'] = 1.2
    
    # 创建图形
    plt.figure(figsize=(12, 9))
    
    # 使用白色网格背景
    plt.grid(True, color='#EEEEEE', linestyle='-', which='both', alpha=0.8)
    
    # 创建阈值网格
    thresholds = np.linspace(0.01, 0.99, 100)
    
    # 计算所有样本都是阳性和阴性时的净收益
    prevalence = np.mean(y_test)
    net_benefit_all = prevalence - (1 - prevalence) * thresholds / (1 - thresholds)
    net_benefit_none = np.zeros_like(thresholds)
    
    # 绘制参考线
    plt.plot(thresholds, net_benefit_all, 'k--', linewidth=1.5, alpha=0.7, label='Treat All')
    plt.plot(thresholds, net_benefit_none, 'k:', linewidth=1.5, alpha=0.7, label='Treat None')
    
    # 按AUROC降序绘制每个模型的决策曲线
    for idx, (model_name, auc) in enumerate(sorted_models):
        net_benefits = []
        probas = model_probas[model_name]
        
        for threshold in thresholds:
            # 预测为阳性的样本
            predict_positive = (probas >= threshold).astype(int)
            
            # 计算真阳性和假阳性
            true_positives = np.sum((predict_positive == 1) & (y_test == 1))
            false_positives = np.sum((predict_positive == 1) & (y_test == 0))
            
            # 计算净收益
            n = len(y_test)
            net_benefit = (true_positives / n) - (false_positives / n) * (threshold / (1 - threshold))
            net_benefits.append(net_benefit)
        
        # 绘制决策曲线
        plt.plot(thresholds, net_benefits, 
                 label=f'{model_name} (AUROC = {auc:.3f})', 
                 color=lancet_palette[idx % len(lancet_palette)],
                 linewidth=2.5)
    
    # Lancet风格的图标题和标签
    plt.title('Decision Curve Analysis', fontsize=16, pad=15)
    plt.xlabel('Threshold Probability', fontsize=14)
    plt.ylabel('Net Benefit', fontsize=14)
    
    # Lancet风格的图例和网格
    plt.legend(loc='upper right', fontsize=10, 
               frameon=True, facecolor='white', framealpha=0.95,
               bbox_to_anchor=(0.95, 0.95))
    
    # 坐标轴设置
    plt.xlim([0.0, 0.5])
    plt.ylim([-0.05,0.15 ])  # 设置y轴范围
    
    # 保存为高分辨率TIFF文件
    plt.savefig('dca_curves.tiff', dpi=600, bbox_inches='tight', format='tiff')
    print("已生成决策曲线分析图: 'dca_curves.tiff'")
    plt.close()

# 在原有代码中添加调用
print("生成专业可视化图表...")
plot_dca_curves(model_probas, y_test)  # 新增：绘制决策曲线分析（按AUROC降序）

# %% Original notebook code cell 14
# ==================== Historical descriptive risk stratification (not a numbered final figure) ====================
# 作用：
# 1. 使用最终 CatBoost 模型在测试集上的预测概率
# 2. 按预测概率三分位数将测试集患者分为 Low / Intermediate / High risk
# 3. 绘制各风险层的实际 SAD 发生率柱状图
# 4. 进行三组间卡方检验和线性趋势检验
#
# 建议放置位置：
# 在模型性能评估完成之后、SHAP分析之前。
#
# 分组依据：
# Tertiles of predicted probabilities generated by the final CatBoost model in the test set.

import os
import glob
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from catboost import CatBoostClassifier
from sklearn.metrics import roc_auc_score
from scipy.stats import chi2_contingency, norm

RISK_OUTPUT_DIR = "Risk_stratification"
os.makedirs(RISK_OUTPUT_DIR, exist_ok=True)


# ==================== 1. 基础绘图设置 ====================
def set_publication_style():
    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.serif"] = ["Times New Roman"] + plt.rcParams["font.serif"]
    plt.rcParams["axes.edgecolor"] = "#444444"
    plt.rcParams["axes.linewidth"] = 1.2
    plt.rcParams["figure.dpi"] = 150


# ==================== 2. 读取最新CatBoost最优参数 ====================
def load_latest_catboost_params_for_risk():
    json_files = glob.glob("model_best_parameters_*.json")

    if not json_files:
        raise FileNotFoundError(
            "未找到 model_best_parameters_*.json。请先运行主模型训练cell，使其输出最佳参数JSON文件。"
        )

    latest_file = max(json_files, key=os.path.getctime)
    print(f"加载CatBoost最优参数文件: {latest_file}")

    with open(latest_file, "r", encoding="utf-8") as f:
        all_params = json.load(f)

    if "CatBoost" not in all_params:
        raise KeyError("JSON文件中未找到 CatBoost 参数。")

    params = all_params["CatBoost"]

    clean_params = {}
    for k, v in params.items():
        clean_k = k.replace("estimator__", "")
        clean_params[clean_k] = v[0] if isinstance(v, list) else v

    return clean_params, latest_file


# ==================== 3. 准备CatBoost测试集数据 ====================
def prepare_catboost_dataframe_for_risk(X_train, X_val, X_test, numerical, categorical):
    final_features = numerical + categorical

    X_train_cb = X_train[final_features].copy()
    X_val_cb = X_val[final_features].copy()
    X_test_cb = X_test[final_features].copy()

    for col in categorical:
        if col in X_train_cb.columns:
            X_train_cb[col] = X_train_cb[col].astype(str)
            X_val_cb[col] = X_val_cb[col].astype(str)
            X_test_cb[col] = X_test_cb[col].astype(str)

    cat_indices = [final_features.index(col) for col in categorical if col in final_features]

    return X_train_cb, X_val_cb, X_test_cb, final_features, cat_indices


# ==================== 4. 获取最终CatBoost测试集预测概率 ====================
def get_final_catboost_test_predictions_for_risk():
    """
    优先使用主模型评估阶段已经生成的 model_probas['CatBoost']。
    如果当前内存中不存在该对象，则根据最新最佳参数重新训练CatBoost，并生成测试集预测概率。
    """

    if "model_probas" in globals() and isinstance(model_probas, dict) and "CatBoost" in model_probas:
        print("使用主模型评估阶段已生成的 model_probas['CatBoost']。")
        test_proba = np.asarray(model_probas["CatBoost"])
        return test_proba, "model_probas['CatBoost']"

    print("未检测到 model_probas['CatBoost']，将根据最新最佳参数重新训练最终CatBoost。")

    catboost_params, params_file = load_latest_catboost_params_for_risk()

    X_train_cb, X_val_cb, X_test_cb, final_features, cat_indices = prepare_catboost_dataframe_for_risk(
        X_train=X_train,
        X_val=X_val,
        X_test=X_test,
        numerical=numerical,
        categorical=categorical
    )

    final_model = CatBoostClassifier(
        random_state=42,
        verbose=0,
        **catboost_params
    )

    final_model.fit(
        X_train_cb,
        y_train,
        cat_features=cat_indices
    )

    val_proba = final_model.predict_proba(X_val_cb)[:, 1]
    test_proba = final_model.predict_proba(X_test_cb)[:, 1]

    val_auc = roc_auc_score(y_val, val_proba)
    test_auc = roc_auc_score(y_test, test_proba)

    print(f"Retrained CatBoost Validation AUROC: {val_auc:.4f}")
    print(f"Retrained CatBoost Test AUROC: {test_auc:.4f}")

    return test_proba, params_file


# ==================== 5. Cochran-Armitage趋势检验 ====================
def cochran_armitage_trend_test(events, totals, scores=None):
    """
    Cochran-Armitage trend test for ordered risk groups.
    events: 每组事件数
    totals: 每组总人数
    scores: 有序组得分，默认 1, 2, 3
    """
    events = np.asarray(events, dtype=float)
    totals = np.asarray(totals, dtype=float)

    if scores is None:
        scores = np.arange(1, len(events) + 1, dtype=float)
    else:
        scores = np.asarray(scores, dtype=float)

    n_total = totals.sum()
    x_total = events.sum()
    p_hat = x_total / n_total

    score_mean = np.sum(totals * scores) / n_total

    numerator = np.sum(scores * (events - totals * p_hat))
    denominator = np.sqrt(
        p_hat * (1 - p_hat) * np.sum(totals * (scores - score_mean) ** 2)
    )

    z_stat = numerator / denominator
    p_value = 2 * (1 - norm.cdf(abs(z_stat)))

    return z_stat, p_value


# ==================== 6. 构建风险分层表 ====================
def build_risk_stratification_dataframe(y_test, test_proba):
    risk_df = pd.DataFrame({
        "SAD": pd.Series(y_test).reset_index(drop=True).astype(int),
        "predicted_probability": np.asarray(test_proba)
    })

    risk_df["risk_group"] = pd.qcut(
        risk_df["predicted_probability"],
        q=3,
        labels=["Low risk", "Intermediate risk", "High risk"],
        duplicates="drop"
    )

    if risk_df["risk_group"].isna().any():
        raise ValueError(
            "风险分层失败：预测概率分布中存在过多重复值，无法按三分位数稳定分组。"
        )

    risk_df["risk_group"] = pd.Categorical(
        risk_df["risk_group"],
        categories=["Low risk", "Intermediate risk", "High risk"],
        ordered=True
    )

    summary_df = (
        risk_df
        .groupby("risk_group", observed=True)
        .agg(
            n=("SAD", "size"),
            sad_events=("SAD", "sum"),
            observed_sad_incidence=("SAD", "mean"),
            mean_predicted_probability=("predicted_probability", "mean"),
            median_predicted_probability=("predicted_probability", "median"),
            min_predicted_probability=("predicted_probability", "min"),
            max_predicted_probability=("predicted_probability", "max")
        )
        .reset_index()
    )

    summary_df["observed_sad_incidence_percent"] = summary_df["observed_sad_incidence"] * 100
    summary_df["mean_predicted_probability_percent"] = summary_df["mean_predicted_probability"] * 100

    return risk_df, summary_df


# ==================== 7. 统计检验 ====================
def risk_stratification_statistical_tests(summary_df):
    events = summary_df["sad_events"].values
    totals = summary_df["n"].values
    non_events = totals - events

    contingency_table = np.vstack([events, non_events]).T

    chi2, chi2_p, dof, expected = chi2_contingency(contingency_table)

    z_trend, p_trend = cochran_armitage_trend_test(
        events=events,
        totals=totals,
        scores=np.arange(1, len(events) + 1)
    )

    stats_results = {
        "chi_square": float(chi2),
        "chi_square_p": float(chi2_p),
        "chi_square_dof": int(dof),
        "cochran_armitage_z": float(z_trend),
        "p_for_trend": float(p_trend)
    }

    return stats_results


# ==================== 8. 绘制风险分层柱状图 ====================
def plot_risk_stratification_bar(summary_df, stats_results, output_dir=RISK_OUTPUT_DIR):
    set_publication_style()

    plot_df = summary_df.copy()
    x = np.arange(plot_df.shape[0])
    y = plot_df["observed_sad_incidence_percent"].values

    fig, ax = plt.subplots(figsize=(7.2, 5.6))

    bars = ax.bar(
        x,
        y,
        width=0.62,
        edgecolor="black",
        linewidth=1.0
    )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [
            f"{row['risk_group']}\n(n={int(row['n'])})"
            for _, row in plot_df.iterrows()
        ],
        fontsize=11
    )

    ax.set_ylabel("Observed SAD incidence (%)", fontsize=12)
    ax.set_xlabel("Risk strata based on predicted probability tertiles", fontsize=12)
    ax.set_title("Risk stratification of sepsis-associated delirium", fontsize=13, pad=12)

    ymax = max(y) * 1.35 if max(y) > 0 else 10
    ax.set_ylim(0, ymax)

    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, incidence, events, n in zip(
        bars,
        plot_df["observed_sad_incidence_percent"],
        plot_df["sad_events"],
        plot_df["n"]
    ):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + ymax * 0.03,
            f"{incidence:.1f}%\n{int(events)}/{int(n)}",
            ha="center",
            va="bottom",
            fontsize=10
        )

    if stats_results["p_for_trend"] < 0.001:
        trend_text = "P for trend < 0.001"
    else:
        trend_text = f"P for trend = {stats_results['p_for_trend']:.3f}"

    ax.text(
        0.98,
        0.96,
        trend_text,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10
    )

    plt.tight_layout()

    fig_path_png = os.path.join(output_dir, "risk_stratification_bar_plot.png")
    fig_path_pdf = os.path.join(output_dir, "risk_stratification_bar_plot.pdf")
    plt.savefig(fig_path_png, dpi=600, bbox_inches="tight")
    plt.savefig(fig_path_pdf, bbox_inches="tight")
    plt.show()
    plt.close()

    print(f"风险分层柱状图已保存：{fig_path_png}")
    print(f"风险分层柱状图PDF已保存：{fig_path_pdf}")


# ==================== 9. 总入口 ====================
def run_risk_stratification_analysis():
    test_proba, prediction_source = get_final_catboost_test_predictions_for_risk()

    risk_df, summary_df = build_risk_stratification_dataframe(
        y_test=y_test,
        test_proba=test_proba
    )

    stats_results = risk_stratification_statistical_tests(summary_df)

    risk_df.to_csv(
        os.path.join(RISK_OUTPUT_DIR, "risk_stratification_patient_level.csv"),
        index=False
    )

    summary_df.to_csv(
        os.path.join(RISK_OUTPUT_DIR, "risk_stratification_summary.csv"),
        index=False
    )

    with open(
        os.path.join(RISK_OUTPUT_DIR, "risk_stratification_statistics.json"),
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(stats_results, f, ensure_ascii=False, indent=4)

    print("\n风险分层汇总：")
    display(summary_df)

    print("\n风险分层统计检验：")
    print(f"Chi-square test: χ² = {stats_results['chi_square']:.3f}, "
          f"P = {stats_results['chi_square_p']:.3e}")
    print(f"Cochran-Armitage trend test: Z = {stats_results['cochran_armitage_z']:.3f}, "
          f"P for trend = {stats_results['p_for_trend']:.3e}")

    plot_risk_stratification_bar(
        summary_df=summary_df,
        stats_results=stats_results,
        output_dir=RISK_OUTPUT_DIR
    )

    run_info = {
        "risk_grouping_method": "Tertiles of predicted probabilities in the test set",
        "prediction_source": prediction_source,
        "output_dir": RISK_OUTPUT_DIR,
        "km_curve": "Not performed because the model was developed for binary prediction of 7-day SAD rather than time-to-event prediction."
    }

    with open(
        os.path.join(RISK_OUTPUT_DIR, "risk_stratification_run_info.json"),
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(run_info, f, ensure_ascii=False, indent=4)

    print("\nRisk stratification analysis completed.")
    print(f"所有结果已保存至: {RISK_OUTPUT_DIR}")

    return {
        "risk_df": risk_df,
        "summary_df": summary_df,
        "stats_results": stats_results,
        "test_proba": test_proba
    }


# ==================== 运行 ====================
risk_stratification_result = run_risk_stratification_analysis()

# %% Original notebook code cell 15
# ==================== CatBoost Final Model SHAP Explanation ====================
# 作用：
# 1. 读取最新 CatBoost 最优参数
# 2. 使用当前主pipeline得到的最终变量：numerical + categorical
# 3. 训练最终 CatBoost 模型
# 4. 计算测试集 SHAP values
# 5. 生成 SHAP summary plot、bar plot、dependence plot
# 6. 从 Low / Intermediate / High risk 三个风险层中各随机抽取2例，绘制 waterfall plot
# 7. 所有结果保存到当前目录下的 SHAP_explanation 文件夹

import os
import glob
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import shap

from catboost import CatBoostClassifier, Pool
from sklearn.metrics import roc_auc_score


# ==================== 1. 创建输出目录 ====================
SHAP_OUTPUT_DIR = "SHAP_explanation"
os.makedirs(SHAP_OUTPUT_DIR, exist_ok=True)


# ==================== 2. 读取最新CatBoost最优参数 ====================
def load_latest_catboost_params():
    """从最新 model_best_parameters_*.json 中读取 CatBoost 最优参数"""

    json_files = glob.glob("model_best_parameters_*.json")

    if not json_files:
        raise FileNotFoundError("未找到 model_best_parameters_*.json 文件")

    latest_file = max(json_files, key=os.path.getctime)
    print(f"加载CatBoost最优参数文件: {latest_file}")

    with open(latest_file, "r", encoding="utf-8") as f:
        all_params = json.load(f)

    if "CatBoost" not in all_params:
        raise KeyError("JSON文件中未找到 CatBoost 参数")

    params = all_params["CatBoost"]

    clean_params = {}
    for k, v in params.items():
        clean_k = k.replace("estimator__", "")
        clean_params[clean_k] = v[0] if isinstance(v, list) else v

    return clean_params, latest_file


# ==================== 3. 准备CatBoost输入数据 ====================
def prepare_catboost_dataframe(X_train, X_val, X_test, numerical, categorical):
    final_features = numerical + categorical

    X_train_cb = X_train[final_features].copy()
    X_val_cb = X_val[final_features].copy()
    X_test_cb = X_test[final_features].copy()

    for col in categorical:
        if col in X_train_cb.columns:
            X_train_cb[col] = X_train_cb[col].astype(str)
            X_val_cb[col] = X_val_cb[col].astype(str)
            X_test_cb[col] = X_test_cb[col].astype(str)

    cat_indices = [final_features.index(col) for col in categorical if col in final_features]

    return X_train_cb, X_val_cb, X_test_cb, final_features, cat_indices


# ==================== 4. 训练最终CatBoost模型 ====================
def train_final_catboost_model(
    X_train_cb,
    y_train,
    X_val_cb,
    y_val,
    X_test_cb,
    y_test,
    catboost_params,
    cat_indices
):
    model = CatBoostClassifier(
        random_state=42,
        verbose=0,
        **catboost_params
    )

    model.fit(
        X_train_cb,
        y_train,
        cat_features=cat_indices
    )

    val_proba = model.predict_proba(X_val_cb)[:, 1]
    test_proba = model.predict_proba(X_test_cb)[:, 1]

    val_auc = roc_auc_score(y_val, val_proba)
    test_auc = roc_auc_score(y_test, test_proba)

    print(f"Final CatBoost Validation AUROC: {val_auc:.4f}")
    print(f"Final CatBoost Test AUROC: {test_auc:.4f}")

    return model, val_proba, test_proba, val_auc, test_auc


# ==================== 5. 计算CatBoost SHAP值 ====================
def get_catboost_shap_values(model, X, y=None, cat_indices=None):
    pool = Pool(
        data=X,
        label=y,
        cat_features=cat_indices
    )

    shap_raw = model.get_feature_importance(
        data=pool,
        type="ShapValues"
    )

    shap_values = shap_raw[:, :-1]
    expected_value = shap_raw[0, -1]

    return shap_values, expected_value


# ==================== 6. 构建或读取风险分层 ====================
def build_or_get_risk_df_for_waterfall(y_test, test_proba):
    """
    优先读取前面风险分层cell生成的 risk_stratification_result["risk_df"]。
    如果不存在，则根据test_proba重新按三分位数分组。
    """

    if (
        "risk_stratification_result" in globals()
        and isinstance(risk_stratification_result, dict)
        and "risk_df" in risk_stratification_result
    ):
        print("使用已有 risk_stratification_result['risk_df'] 选择waterfall病例。")
        risk_df = risk_stratification_result["risk_df"].copy()

        if "predicted_probability" not in risk_df.columns:
            risk_df["predicted_probability"] = np.asarray(test_proba)

        if "SAD" not in risk_df.columns:
            risk_df["SAD"] = pd.Series(y_test).reset_index(drop=True).astype(int)

        return risk_df.reset_index(drop=True)

    print("未检测到已有风险分层结果，将根据test_proba重新按三分位数分组。")

    risk_df = pd.DataFrame({
        "SAD": pd.Series(y_test).reset_index(drop=True).astype(int),
        "predicted_probability": np.asarray(test_proba)
    })

    risk_df["risk_group"] = pd.qcut(
        risk_df["predicted_probability"],
        q=3,
        labels=["Low risk", "Intermediate risk", "High risk"],
        duplicates="drop"
    )

    risk_df["risk_group"] = pd.Categorical(
        risk_df["risk_group"],
        categories=["Low risk", "Intermediate risk", "High risk"],
        ordered=True
    )

    return risk_df.reset_index(drop=True)


# ==================== 7. 从三种风险层中各随机抽取2例 ====================
def select_random_cases_by_risk_group(
    risk_df,
    n_per_group=2,
    random_state=42,
    output_dir=SHAP_OUTPUT_DIR
):
    rng = np.random.default_rng(random_state)

    selected_records = []

    for group in ["Low risk", "Intermediate risk", "High risk"]:
        group_df = risk_df[risk_df["risk_group"] == group].copy()

        if group_df.empty:
            print(f"警告：{group} 组为空，跳过。")
            continue

        n_select = min(n_per_group, group_df.shape[0])

        selected_indices = rng.choice(
            group_df.index.to_numpy(),
            size=n_select,
            replace=False
        )

        for idx in selected_indices:
            selected_records.append({
                "sample_index": int(idx),
                "risk_group": group,
                "SAD": int(risk_df.loc[idx, "SAD"]),
                "predicted_probability": float(risk_df.loc[idx, "predicted_probability"])
            })

    selected_df = pd.DataFrame(selected_records)

    selected_df.to_csv(
        os.path.join(output_dir, "selected_waterfall_cases_by_risk_group.csv"),
        index=False
    )

    print("\nSelected waterfall cases:")
    display(selected_df)

    return selected_df


# ==================== 8. SHAP绘图 ====================
def generate_final_catboost_shap_plots(
    model,
    X_data,
    y_data,
    test_proba,
    feature_names,
    categorical,
    cat_indices,
    output_dir=SHAP_OUTPUT_DIR,
    max_display=20,
    n_waterfall_per_group=2,
    random_state=42
):
    os.makedirs(output_dir, exist_ok=True)

    print("计算SHAP值...")
    shap_values, expected_value = get_catboost_shap_values(
        model=model,
        X=X_data,
        y=y_data,
        cat_indices=cat_indices
    )

    # 显示名称仅用于绘图和展示，不改变原始特征名
    feature_display_names = display_feature_names(feature_names)
    original_to_display = dict(zip(feature_names, feature_display_names))

    # 保存SHAP矩阵
    shap_values_df = pd.DataFrame(
        shap_values,
        columns=feature_names
    )

    shap_values_df.to_csv(
        os.path.join(output_dir, "catboost_shap_values.csv"),
        index=False
    )

    # 保存mean(|SHAP|)重要性
    shap_importance_df = pd.DataFrame({
        "Feature": feature_names,
        "Feature_Display": feature_display_names,
        "MeanAbsSHAP": np.abs(shap_values).mean(axis=0)
    }).sort_values(
        by="MeanAbsSHAP",
        ascending=False
    ).reset_index(drop=True)

    shap_importance_df.to_csv(
        os.path.join(output_dir, "catboost_shap_feature_importance.csv"),
        index=False
    )

    # SHAP绘图用数据：分类变量转category codes，避免字符串绘图异常
    X_plot = X_data.copy()

    for col in categorical:
        if col in X_plot.columns:
            X_plot[col] = X_plot[col].astype("category").cat.codes

    X_plot_display = X_plot.copy()
    X_plot_display.columns = feature_display_names

    # ==================== 8.1 SHAP summary dot plot ====================
    plt.figure()
    shap.summary_plot(
        shap_values,
        X_plot_display,
        feature_names=feature_display_names,
        max_display=max_display,
        show=False
    )
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "shap_summary_plot.png"),
        dpi=600,
        bbox_inches="tight"
    )
    plt.close()

    # ==================== 8.2 SHAP bar plot ====================
    plt.figure()
    shap.summary_plot(
        shap_values,
        X_plot_display,
        feature_names=feature_display_names,
        plot_type="bar",
        max_display=max_display,
        show=False
    )
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "shap_bar_plot.png"),
        dpi=600,
        bbox_inches="tight"
    )
    plt.close()

    # ==================== 8.3 SHAP dependence plots for top 5 features ====================
    top_features = shap_importance_df["Feature"].head(5).tolist()

    for feature in top_features:
        display_feature = original_to_display.get(feature, feature)

        plt.figure()
        shap.dependence_plot(
            display_feature,
            shap_values,
            X_plot_display,
            feature_names=feature_display_names,
            show=False
        )
        plt.tight_layout()

        safe_name = safe_filename_from_label(display_feature)

        plt.savefig(
            os.path.join(output_dir, f"shap_dependence_{safe_name}.png"),
            dpi=600,
            bbox_inches="tight"
        )
        plt.close()

    # ==================== 8.4 按风险层随机抽取病例绘制waterfall plots ====================
    risk_df = build_or_get_risk_df_for_waterfall(
        y_test=y_data,
        test_proba=test_proba
    )

    selected_waterfall_cases = select_random_cases_by_risk_group(
        risk_df=risk_df,
        n_per_group=n_waterfall_per_group,
        random_state=random_state,
        output_dir=output_dir
    )

    for _, row in selected_waterfall_cases.iterrows():
        idx = int(row["sample_index"])
        group = str(row["risk_group"]).replace(" ", "_").lower()
        sad_status = int(row["SAD"])
        pred_prob = float(row["predicted_probability"])

        explanation = shap.Explanation(
            values=shap_values[idx, :],
            base_values=expected_value,
            data=X_plot_display.iloc[idx, :].values,
            feature_names=feature_display_names
        )

        plt.figure(figsize=(8.5, 6.2))
        shap.plots.waterfall(
            explanation,
            max_display=15,
            show=False
        )

        plt.title(
            f"{row['risk_group']} | SAD={sad_status} | Predicted probability={pred_prob:.3f}",
            fontsize=11,
            pad=10
        )

        plt.tight_layout()

        file_prefix = (
            f"shap_waterfall_{group}_"
            f"idx{idx + 1}_"
            f"sad{sad_status}_"
            f"prob{pred_prob:.3f}"
        )

        plt.savefig(
            os.path.join(output_dir, f"{file_prefix}.png"),
            dpi=600,
            bbox_inches="tight"
        )
        plt.savefig(
            os.path.join(output_dir, f"{file_prefix}.pdf"),
            bbox_inches="tight"
        )
        plt.close()

    print(f"SHAP解释图和数据已保存至: {output_dir}")

    return shap_values, expected_value, shap_importance_df, selected_waterfall_cases


# ==================== 9. 总入口 ====================
def run_final_catboost_shap_explanation():
    """
    运行最终CatBoost模型SHAP解释流程。

    前提：
    1. 主pipeline已经运行完成
    2. X_train, X_val, X_test, y_train, y_val, y_test 已存在
    3. numerical, categorical 已经是Boruta筛选后的最终变量
    4. model_best_parameters_*.json 已存在
    5. 如果前面已运行risk stratification cell，则优先使用已有风险分层结果
    """

    catboost_params, params_file = load_latest_catboost_params()

    X_train_cb, X_val_cb, X_test_cb, feature_names, cat_indices = prepare_catboost_dataframe(
        X_train=X_train,
        X_val=X_val,
        X_test=X_test,
        numerical=numerical,
        categorical=categorical
    )

    final_model, val_proba, test_proba, val_auc, test_auc = train_final_catboost_model(
        X_train_cb=X_train_cb,
        y_train=y_train,
        X_val_cb=X_val_cb,
        y_val=y_val,
        X_test_cb=X_test_cb,
        y_test=y_test,
        catboost_params=catboost_params,
        cat_indices=cat_indices
    )

    shap_values, expected_value, shap_importance_df, selected_waterfall_cases = generate_final_catboost_shap_plots(
        model=final_model,
        X_data=X_test_cb,
        y_data=y_test,
        test_proba=test_proba,
        feature_names=feature_names,
        categorical=categorical,
        cat_indices=cat_indices,
        output_dir=SHAP_OUTPUT_DIR,
        max_display=20,
        n_waterfall_per_group=2,
        random_state=42
    )

    # 保存模型与运行信息
    run_info = {
        "params_file": params_file,
        "final_features": feature_names,
        "categorical_features": categorical,
        "cat_indices": cat_indices,
        "validation_auc": float(val_auc),
        "test_auc": float(test_auc),
        "expected_value": float(expected_value),
        "waterfall_case_selection": "Two randomly selected patients from each risk stratum using a fixed random seed.",
        "waterfall_random_state": 42
    }

    with open(
        os.path.join(SHAP_OUTPUT_DIR, "catboost_shap_run_info.json"),
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(run_info, f, ensure_ascii=False, indent=4)

    # 保存验证集预测概率
    pred_df = pd.DataFrame({
        "y_val": pd.Series(y_val).reset_index(drop=True).values,
        "val_proba": val_proba
    })
    pred_df.to_csv(
        os.path.join(SHAP_OUTPUT_DIR, "catboost_validation_predictions.csv"),
        index=False
    )

    # 保存测试集预测概率
    test_pred_df = pd.DataFrame({
        "y_test": pd.Series(y_test).reset_index(drop=True).values,
        "test_proba": test_proba
    })
    test_pred_df.to_csv(
        os.path.join(SHAP_OUTPUT_DIR, "catboost_test_predictions.csv"),
        index=False
    )

    print("\nFinal CatBoost SHAP explanation completed.")
    print(f"所有结果已保存至: {SHAP_OUTPUT_DIR}")

    return {
        "model": final_model,
        "shap_values": shap_values,
        "expected_value": expected_value,
        "shap_importance_df": shap_importance_df,
        "selected_waterfall_cases": selected_waterfall_cases,
        "validation_auc": val_auc,
        "test_auc": test_auc,
        "test_proba": test_proba
    }


# ==================== 运行 ====================
final_catboost_shap_result = run_final_catboost_shap_explanation()

# 查看前20个SHAP重要特征
display(
    final_catboost_shap_result["shap_importance_df"][
        ["Feature", "Feature_Display", "MeanAbsSHAP"]
    ].head(20)
)

# 查看被随机抽取用于waterfall plot的病例
display(final_catboost_shap_result["selected_waterfall_cases"])

# %% Original notebook code cell 18
# ==================== CatBoost SHAP 最佳简化模型构建 + ROC/Calibration/DCA 对比 ====================

import os
import glob
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import shap

from catboost import CatBoostClassifier, Pool
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.calibration import calibration_curve


# ==================== 1. 读取最新CatBoost最优参数 ====================
def load_latest_catboost_params():
    json_files = glob.glob("model_best_parameters_*.json")
    if not json_files:
        raise FileNotFoundError("未找到 model_best_parameters_*.json 文件")

    latest_file = max(json_files, key=os.path.getctime)
    print(f"加载CatBoost最优参数文件: {latest_file}")

    with open(latest_file, "r", encoding="utf-8") as f:
        all_params = json.load(f)

    if "CatBoost" not in all_params:
        raise KeyError("JSON文件中未找到 CatBoost 参数")

    params = all_params["CatBoost"]

    clean_params = {}
    for k, v in params.items():
        clean_k = k.replace("estimator__", "")
        clean_params[clean_k] = v[0] if isinstance(v, list) else v

    return clean_params


# ==================== 2. 准备CatBoost输入数据 ====================
def prepare_catboost_dataframe(X_train, X_val, X_test, numerical, categorical):
    final_features = numerical + categorical

    X_train_cb = X_train[final_features].copy()
    X_val_cb = X_val[final_features].copy()
    X_test_cb = X_test[final_features].copy()

    for col in categorical:
        X_train_cb[col] = X_train_cb[col].astype(str)
        X_val_cb[col] = X_val_cb[col].astype(str)
        X_test_cb[col] = X_test_cb[col].astype(str)

    cat_indices = [final_features.index(col) for col in categorical]

    return X_train_cb, X_val_cb, X_test_cb, final_features, cat_indices


# ==================== 3. CatBoost SHAP ====================
def get_catboost_shap_values(model, X, y=None, cat_indices=None):
    pool = Pool(
        data=X,
        label=y,
        cat_features=cat_indices
    )

    shap_raw = model.get_feature_importance(
        data=pool,
        type="ShapValues"
    )

    shap_values = shap_raw[:, :-1]
    expected_value = shap_raw[0, -1]

    return shap_values, expected_value


# ==================== 4. DCA函数 ====================
def calculate_net_benefit(y_true, y_proba, thresholds):
    y_true = np.asarray(y_true)
    y_proba = np.asarray(y_proba)

    n = len(y_true)
    prevalence = np.mean(y_true)

    rows = []

    for pt in thresholds:
        pred_positive = y_proba >= pt

        tp = np.sum((pred_positive == 1) & (y_true == 1))
        fp = np.sum((pred_positive == 1) & (y_true == 0))

        nb_model = (tp / n) - (fp / n) * (pt / (1 - pt))
        nb_all = prevalence - (1 - prevalence) * (pt / (1 - pt))
        nb_none = 0

        rows.append({
            "threshold": pt,
            "net_benefit_model": nb_model,
            "net_benefit_all": nb_all,
            "net_benefit_none": nb_none
        })

    return pd.DataFrame(rows)


# ==================== 5. 构建SHAP最佳简化模型 ====================
def build_catboost_shap_simplified_model(
    X_train_cb,
    y_train,
    X_val_cb,
    y_val,
    X_test_cb,
    y_test,
    catboost_params,
    feature_names,
    categorical,
    min_features=8,
    max_features=40,
    selection_strategy="max_val",
    tolerance=0.01
):
    cat_indices_full = [
        feature_names.index(col)
        for col in categorical
        if col in feature_names
    ]

    print("训练全特征CatBoost模型...")
    full_model = CatBoostClassifier(
        random_state=42,
        verbose=0,
        **catboost_params
    )

    full_model.fit(
        X_train_cb,
        y_train,
        cat_features=cat_indices_full
    )

    full_val_proba = full_model.predict_proba(X_val_cb)[:, 1]
    full_test_proba = full_model.predict_proba(X_test_cb)[:, 1]

    full_val_auc = roc_auc_score(y_val, full_val_proba)
    full_test_auc = roc_auc_score(y_test, full_test_proba)

    print(f"全特征模型 Validation AUROC: {full_val_auc:.4f}")
    print(f"全特征模型 Test AUROC: {full_test_auc:.4f}")

    print("计算全特征CatBoost SHAP值...")
    shap_values, expected_value = get_catboost_shap_values(
        model=full_model,
        X=X_train_cb,
        y=y_train,
        cat_indices=cat_indices_full
    )

    mean_abs_shap = np.abs(shap_values).mean(axis=0)

    feature_display_names = display_feature_names(feature_names)

    shap_importance_df = pd.DataFrame({
        "Feature": feature_names,
        "Feature_Display": feature_display_names,
        "MeanAbsSHAP": mean_abs_shap
    }).sort_values("MeanAbsSHAP", ascending=False).reset_index(drop=True)

    shap_importance_df.to_csv(
        "catboost_full_model_shap_importance.csv",
        index=False,
        encoding="utf-8-sig"
    )

    sorted_features = shap_importance_df["Feature"].tolist()
    max_k = min(max_features, len(sorted_features))

    records = []
    candidate_models = {}

    print(f"开始搜索简化特征数: k={min_features}..{max_k}")

    for k in range(min_features, max_k + 1):
        selected_features = sorted_features[:k]

        selected_categorical = [
            f for f in selected_features
            if f in categorical
        ]

        selected_cat_indices = [
            selected_features.index(f)
            for f in selected_categorical
        ]

        X_train_k = X_train_cb[selected_features].copy()
        X_val_k = X_val_cb[selected_features].copy()
        X_test_k = X_test_cb[selected_features].copy()

        model_k = CatBoostClassifier(
            random_state=42,
            verbose=0,
            **catboost_params
        )

        model_k.fit(
            X_train_k,
            y_train,
            cat_features=selected_cat_indices
        )

        y_val_proba = model_k.predict_proba(X_val_k)[:, 1]
        y_test_proba = model_k.predict_proba(X_test_k)[:, 1]

        val_auc = roc_auc_score(y_val, y_val_proba)
        test_auc = roc_auc_score(y_test, y_test_proba)

        records.append({
            "k": k,
            "Validation_AUROC": val_auc,
            "Test_AUROC": test_auc,
            "Selected_Features": selected_features
        })

        candidate_models[k] = model_k

        print(
            f"k={k}, "
            f"Validation AUROC={val_auc:.4f}, "
            f"Test AUROC={test_auc:.4f}"
        )

    auc_df = pd.DataFrame(records)
    auc_df.to_csv("catboost_shap_simplified_auc_by_k.csv", index=False, encoding="utf-8-sig")

    best_val_auc_overall = auc_df["Validation_AUROC"].max()

    if selection_strategy == "max_val":
        selected_row = auc_df.loc[
            auc_df["Validation_AUROC"].idxmax()
        ]

    elif selection_strategy == "within_1se":
        eligible = auc_df[
            auc_df["Validation_AUROC"] >= best_val_auc_overall - tolerance
        ].copy()

        selected_row = eligible.sort_values(
            by=["k"],
            ascending=False
        ).iloc[0]

    else:
        raise ValueError("selection_strategy 只能是 'max_val' 或 'within_1se'")

    best_k = int(selected_row["k"])
    best_features = selected_row["Selected_Features"]
    best_model = candidate_models[best_k]
    best_val_auc = float(selected_row["Validation_AUROC"])
    best_test_auc = float(selected_row["Test_AUROC"])

    print("\n[SHAP最佳简化模型选择结果]")
    print(f"选择策略: {selection_strategy}")
    print(f"tolerance: {tolerance}")
    print(f"最终特征数: {best_k}")
    print(f"简化模型 Validation AUROC: {best_val_auc:.4f}")
    print(f"简化模型 Test AUROC: {best_test_auc:.4f}")
    print("最终入选特征:")
    print(best_features)

    simplified_importance_df = shap_importance_df[
        shap_importance_df["Feature"].isin(best_features)
    ].copy()

    simplified_importance_df.to_csv(
        "catboost_shap_simplified_features.csv",
        index=False,
        encoding="utf-8-sig"
    )

    return {
        "full_model": full_model,
        "best_model": best_model,
        "best_features": best_features,
        "best_k": best_k,
        "best_val_auc": best_val_auc,
        "best_test_auc": best_test_auc,
        "full_val_auc": full_val_auc,
        "full_test_auc": full_test_auc,
        "full_val_proba": full_val_proba,
        "full_test_proba": full_test_proba,
        "auc_df": auc_df,
        "shap_importance_df": shap_importance_df,
        "expected_value": expected_value
    }


# ==================== 6. SHAP可视化 ====================
def generate_catboost_shap_plots(
    model,
    X_data,
    y_data,
    feature_names,
    categorical,
    output_dir="catboost_shap_visualizations",
    max_display=20,
    sample_indices=None
):
    os.makedirs(output_dir, exist_ok=True)

    cat_indices = [
        feature_names.index(col)
        for col in categorical
        if col in feature_names
    ]

    shap_values, expected_value = get_catboost_shap_values(
        model=model,
        X=X_data,
        y=y_data,
        cat_indices=cat_indices
    )

    feature_display_names = display_feature_names(feature_names)

    X_plot = X_data.copy()
    for col in categorical:
        if col in X_plot.columns:
            X_plot[col] = X_plot[col].astype("category").cat.codes

    X_plot_display = X_plot.copy()
    X_plot_display.columns = feature_display_names

    plt.figure()
    shap.summary_plot(
        shap_values,
        X_plot_display,
        feature_names=feature_display_names,
        max_display=max_display,
        show=False
    )
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "shap_summary_plot.png"),
        dpi=600,
        bbox_inches="tight"
    )
    plt.close()

    plt.figure()
    shap.summary_plot(
        shap_values,
        X_plot_display,
        feature_names=feature_display_names,
        plot_type="bar",
        max_display=max_display,
        show=False
    )
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "shap_bar_plot.png"),
        dpi=600,
        bbox_inches="tight"
    )
    plt.close()

    print(f"SHAP图已保存至: {output_dir}")

    return shap_values, expected_value


# ==================== 7. Full vs Simplified ROC ====================
def plot_full_vs_simplified_roc(
    y_test,
    full_proba,
    simplified_proba,
    output_file="catboost_full_vs_simplified_roc.png"
):
    full_auc = roc_auc_score(y_test, full_proba)
    simplified_auc = roc_auc_score(y_test, simplified_proba)

    fpr_full, tpr_full, _ = roc_curve(y_test, full_proba)
    fpr_simp, tpr_simp, _ = roc_curve(y_test, simplified_proba)

    plt.figure(figsize=(8, 7))

    plt.plot(
        fpr_full,
        tpr_full,
        linewidth=2.5,
        label=f"Full CatBoost (AUROC = {full_auc:.4f})"
    )

    plt.plot(
        fpr_simp,
        tpr_simp,
        linewidth=2.5,
        linestyle="--",
        label=f"SHAP-Simplified CatBoost (AUROC = {simplified_auc:.4f})"
    )

    plt.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1.2)

    plt.xlabel("False Positive Rate", fontsize=12)
    plt.ylabel("True Positive Rate", fontsize=12)
    plt.title("ROC Curves: Full vs SHAP-Simplified CatBoost", fontsize=14)
    plt.legend(loc="lower right")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_file, dpi=600, bbox_inches="tight")
    plt.show()

    print(f"ROC对比图已保存: {output_file}")


# ==================== 8. Full vs Simplified Calibration ====================
def plot_full_vs_simplified_calibration(
    y_test,
    full_proba,
    simplified_proba,
    output_file="catboost_full_vs_simplified_calibration.png"
):
    prob_true_full, prob_pred_full = calibration_curve(
        y_test,
        full_proba,
        n_bins=10,
        strategy="quantile"
    )

    prob_true_simp, prob_pred_simp = calibration_curve(
        y_test,
        simplified_proba,
        n_bins=10,
        strategy="quantile"
    )

    plt.figure(figsize=(8, 7))

    plt.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1.5, label="Perfect calibration")

    plt.plot(
        prob_pred_full,
        prob_true_full,
        marker="o",
        linewidth=2.5,
        label="Full CatBoost"
    )

    plt.plot(
        prob_pred_simp,
        prob_true_simp,
        marker="s",
        linewidth=2.5,
        linestyle="--",
        label="SHAP-Simplified CatBoost"
    )

    plt.xlabel("Mean predicted probability", fontsize=12)
    plt.ylabel("Observed event rate", fontsize=12)
    plt.title("Calibration Curves: Full vs SHAP-Simplified CatBoost", fontsize=14)
    plt.legend(loc="upper left")
    plt.grid(alpha=0.3)
    plt.xlim(0, 1)
    plt.ylim(0, 1)
    plt.tight_layout()
    plt.savefig(output_file, dpi=600, bbox_inches="tight")
    plt.show()

    print(f"Calibration对比图已保存: {output_file}")


# ==================== 9. Full vs Simplified DCA ====================
def plot_full_vs_simplified_dca(
    y_test,
    full_proba,
    simplified_proba,
    output_file="catboost_full_vs_simplified_dca.png"
):
    thresholds = np.linspace(0.01, 0.99, 99)

    dca_full = calculate_net_benefit(y_test, full_proba, thresholds)
    dca_simp = calculate_net_benefit(y_test, simplified_proba, thresholds)

    plt.figure(figsize=(9, 7))

    plt.plot(
        dca_full["threshold"],
        dca_full["net_benefit_model"],
        linewidth=2.5,
        label="Full CatBoost"
    )

    plt.plot(
        dca_simp["threshold"],
        dca_simp["net_benefit_model"],
        linewidth=2.5,
        linestyle="--",
        label="SHAP-Simplified CatBoost"
    )

    plt.plot(
        dca_full["threshold"],
        dca_full["net_benefit_all"],
        color="gray",
        linestyle="-.",
        linewidth=1.8,
        label="Treat all"
    )

    plt.plot(
        dca_full["threshold"],
        dca_full["net_benefit_none"],
        color="black",
        linestyle=":",
        linewidth=1.8,
        label="Treat none"
    )

    dca_output_df = pd.DataFrame({
        "threshold": thresholds,
        "full_model_net_benefit": dca_full["net_benefit_model"],
        "simplified_model_net_benefit": dca_simp["net_benefit_model"],
        "treat_all_net_benefit": dca_full["net_benefit_all"],
        "treat_none_net_benefit": dca_full["net_benefit_none"]
    })

    dca_output_df.to_csv(
        "catboost_full_vs_simplified_dca_values.csv",
        index=False,
        encoding="utf-8-sig"
    )

    plt.xlabel("Threshold probability", fontsize=12)
    plt.ylabel("Net benefit", fontsize=12)
    plt.title("Decision Curve Analysis: Full vs SHAP-Simplified CatBoost", fontsize=14)
    plt.legend(loc="upper right")
    plt.grid(alpha=0.3)

    plt.xlim(0, 0.6)
    plt.ylim(
        min(
            dca_output_df[
                ["full_model_net_benefit", "simplified_model_net_benefit", "treat_all_net_benefit", "treat_none_net_benefit"]
            ].min()
        ) - 0.02,
        max(
            dca_output_df[
                ["full_model_net_benefit", "simplified_model_net_benefit", "treat_all_net_benefit", "treat_none_net_benefit"]
            ].max()
        ) + 0.02
    )

    plt.tight_layout()
    plt.savefig(output_file, dpi=600, bbox_inches="tight")
    plt.show()

    print(f"DCA对比图已保存: {output_file}")


# ==================== 10. 总入口 ====================
def run_catboost_shap_simplification(
    selection_strategy="max_val",
    tolerance=0.01,
    min_features=8,
    max_features=40
):
    catboost_params = load_latest_catboost_params()

    print("\n准备CatBoost专用数据...")
    X_train_cb, X_val_cb, X_test_cb, feature_names, cat_indices = prepare_catboost_dataframe(
        X_train,
        X_val,
        X_test,
        numerical,
        categorical
    )

    result = build_catboost_shap_simplified_model(
        X_train_cb=X_train_cb,
        y_train=y_train,
        X_val_cb=X_val_cb,
        y_val=y_val,
        X_test_cb=X_test_cb,
        y_test=y_test,
        catboost_params=catboost_params,
        feature_names=feature_names,
        categorical=categorical,
        min_features=min_features,
        max_features=max_features,
        selection_strategy=selection_strategy,
        tolerance=tolerance
    )

    best_features = result["best_features"]

    X_train_simplified = X_train_cb[best_features].copy()
    X_test_simplified = X_test_cb[best_features].copy()

    simplified_categorical = [
        f for f in best_features
        if f in categorical
    ]

    simplified_test_proba = result["best_model"].predict_proba(X_test_simplified)[:, 1]
    full_test_proba = result["full_test_proba"]

    prediction_df = pd.DataFrame({
        "y_test": np.asarray(y_test),
        "full_catboost_proba": full_test_proba,
        "simplified_catboost_proba": simplified_test_proba
    })

    prediction_df.to_csv(
        "catboost_full_vs_simplified_test_predictions.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\n生成最佳简化模型SHAP图...")
    generate_catboost_shap_plots(
        model=result["best_model"],
        X_data=X_train_simplified,
        y_data=y_train,
        feature_names=best_features,
        categorical=simplified_categorical,
        output_dir="catboost_best_simplified_shap_visualizations",
        max_display=min(20, len(best_features)),
        sample_indices=list(range(min(5, X_train_simplified.shape[0])))
    )

    print("\n生成全模型SHAP图...")
    generate_catboost_shap_plots(
        model=result["full_model"],
        X_data=X_train_cb,
        y_data=y_train,
        feature_names=feature_names,
        categorical=categorical,
        output_dir="catboost_full_model_shap_visualizations",
        max_display=min(20, len(feature_names)),
        sample_indices=list(range(min(5, X_train_cb.shape[0])))
    )

    print("\n绘制Full vs Simplified ROC...")
    plot_full_vs_simplified_roc(
        y_test=y_test,
        full_proba=full_test_proba,
        simplified_proba=simplified_test_proba,
        output_file="catboost_full_vs_best_simplified_roc.png"
    )

    print("\n绘制Full vs Simplified Calibration...")
    plot_full_vs_simplified_calibration(
        y_test=y_test,
        full_proba=full_test_proba,
        simplified_proba=simplified_test_proba,
        output_file="catboost_full_vs_best_simplified_calibration.png"
    )

    print("\n绘制Full vs Simplified DCA...")
    plot_full_vs_simplified_dca(
        y_test=y_test,
        full_proba=full_test_proba,
        simplified_proba=simplified_test_proba,
        output_file="catboost_full_vs_best_simplified_dca.png"
    )

    with open("catboost_shap_best_simplified_model_info.json", "w", encoding="utf-8") as f:
        json.dump({
            "selection_strategy": selection_strategy,
            "tolerance": tolerance,
            "best_k": int(result["best_k"]),
            "selected_features": result["best_features"],
            "selected_features_display": display_feature_names(result["best_features"]),
            "full_validation_auc": float(result["full_val_auc"]),
            "full_test_auc": float(result["full_test_auc"]),
            "simplified_validation_auc": float(result["best_val_auc"]),
            "simplified_test_auc": float(result["best_test_auc"])
        }, f, ensure_ascii=False, indent=4)

    print("\nCatBoost SHAP最佳简化模型流程完成。")
    print("最佳简化模型信息已保存: catboost_shap_best_simplified_model_info.json")

    return result


# ==================== 运行 ====================
catboost_shap_result = run_catboost_shap_simplification(
    selection_strategy="max_val",
    tolerance=0.01,
    min_features=8,
    max_features=40
)

# %% Original notebook code cell 21
# ==================== 保存最终SHAP简化CatBoost模型 ====================

import os
import json
import joblib

SAVE_DIR = str(_sad_private_path("mimic_study", '外部验证'))
os.makedirs(SAVE_DIR, exist_ok=True)

# 确认对象存在
print(type(catboost_shap_result))
print(catboost_shap_result.keys())

# 1. 保存最终简化模型
joblib.dump(
    catboost_shap_result["best_model"],
    os.path.join(SAVE_DIR, "SAD_7day_SHAP_simplified_CatBoost_model.pkl")
)

# 2. 保存最终入选特征
with open(
    os.path.join(SAVE_DIR, "SAD_7day_SHAP_simplified_features.json"),
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        catboost_shap_result["best_features"],
        f,
        ensure_ascii=False,
        indent=4
    )

# 3. 保存简化模型的分类变量
simplified_categorical = [
    f for f in catboost_shap_result["best_features"]
    if f in categorical
]

with open(
    os.path.join(SAVE_DIR, "SAD_7day_SHAP_simplified_categorical_features.json"),
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        simplified_categorical,
        f,
        ensure_ascii=False,
        indent=4
    )

# 4. 保存模型基本信息
model_info = {
    "model_type": "CatBoostClassifier",
    "outcome": "SAD_7days",
    "best_k": int(catboost_shap_result["best_k"]),
    "best_features": catboost_shap_result["best_features"],
    "best_features_display": display_feature_names(catboost_shap_result["best_features"]),
    "simplified_validation_auc": float(catboost_shap_result["best_val_auc"]),
    "simplified_test_auc": float(catboost_shap_result["best_test_auc"]),
    "full_validation_auc": float(catboost_shap_result["full_val_auc"]),
    "full_test_auc": float(catboost_shap_result["full_test_auc"]),
    "categorical_features": simplified_categorical
}

with open(
    os.path.join(SAVE_DIR, "SAD_7day_SHAP_simplified_model_info.json"),
    "w",
    encoding="utf-8"
) as f:
    json.dump(model_info, f, ensure_ascii=False, indent=4)

print("=" * 80)
print("最终SHAP简化模型保存完成")
print(f"保存目录: {SAVE_DIR}")
print(f"最终特征数: {len(catboost_shap_result['best_features'])}")
print("最终特征:")
print(catboost_shap_result["best_features"])
print("最终特征（发表显示名）:")
print(display_feature_names(catboost_shap_result["best_features"]))
print(f"分类变量: {simplified_categorical}")
print("=" * 80)

# %% Original notebook code cell 24
# ==================== TRIPOD+AI reporting export ====================
# Purpose:
# 1. Report participant and outcome-event counts for the overall, training,
#    validation, and test datasets.
# 2. Document the exact class-imbalance, calibration, hyperparameter-tuning,
#    and threshold-selection procedures used in this notebook.
# 3. Calculate stratified-bootstrap 95% confidence intervals for final-model
#    performance without re-optimizing the threshold in the test set.
# 4. Export all results to a Word document and supporting CSV files.
#
# Run this cell after all preceding model-development and simplification cells.

import os
import sys
import json
import platform
import numpy as np
import pandas as pd
import sklearn
import catboost
from IPython.display import display

from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    roc_curve,
)
from sklearn.linear_model import LogisticRegression

try:
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
except ImportError as exc:
    raise ImportError(
        "python-docx is required for Word export. Install it with: pip install python-docx"
    ) from exc


# -------------------- 0. Configuration and required objects --------------------
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260608

required_objects = [
    "X_train", "X_val", "X_test",
    "y_train", "y_val", "y_test",
    "numerical", "categorical",
    "catboost_shap_result",
]
missing_objects = [name for name in required_objects if name not in globals()]
if missing_objects:
    raise RuntimeError(
        "Run all preceding notebook cells first. Missing objects: "
        + ", ".join(missing_objects)
    )

output_dir = PROJECT_DIR if "PROJECT_DIR" in globals() and os.path.isdir(PROJECT_DIR) else os.getcwd()
os.makedirs(output_dir, exist_ok=True)

output_docx = os.path.join(output_dir, "TRIPOD_AI_reporting_supplement.docx")
output_counts_csv = os.path.join(output_dir, "TRIPOD_AI_dataset_event_counts.csv")
output_performance_csv = os.path.join(output_dir, "TRIPOD_AI_model_performance_95CI.csv")
output_hyperparameters_csv = os.path.join(output_dir, "TRIPOD_AI_final_hyperparameters.csv")
output_imbalance_csv = os.path.join(output_dir, "TRIPOD_AI_class_imbalance_methods.csv")


# -------------------- 1. Utility functions --------------------
def _as_binary_array(y):
    arr = np.asarray(y).astype(int).reshape(-1)
    unique_values = np.unique(arr)
    if not np.all(np.isin(unique_values, [0, 1])):
        raise ValueError(f"Outcome must be binary 0/1; observed values: {unique_values.tolist()}")
    return arr


def _prepare_catboost_frame(X, feature_names, categorical_names):
    frame = X[feature_names].copy()
    for column in categorical_names:
        if column in frame.columns:
            frame[column] = frame[column].astype(str)
    return frame


def _youden_threshold(y_true, y_probability):
    y_true = _as_binary_array(y_true)
    y_probability = np.asarray(y_probability, dtype=float)
    fpr, tpr, thresholds = roc_curve(y_true, y_probability)
    j_statistic = tpr - fpr
    finite_mask = np.isfinite(thresholds)
    if finite_mask.any():
        finite_indices = np.flatnonzero(finite_mask)
        best_local_index = int(np.argmax(j_statistic[finite_mask]))
        best_index = int(finite_indices[best_local_index])
    else:
        best_index = int(np.argmax(j_statistic))
    return float(thresholds[best_index])


def _fit_sigmoid_calibrator(validation_probability, y_validation, target_probability):
    validation_probability = np.clip(
        np.asarray(validation_probability, dtype=float), 1e-6, 1 - 1e-6
    )
    target_probability = np.clip(
        np.asarray(target_probability, dtype=float), 1e-6, 1 - 1e-6
    )
    validation_logit = np.log(
        validation_probability / (1 - validation_probability)
    ).reshape(-1, 1)
    target_logit = np.log(
        target_probability / (1 - target_probability)
    ).reshape(-1, 1)

    calibrator = LogisticRegression(solver="lbfgs", max_iter=1000)
    calibrator.fit(validation_logit, _as_binary_array(y_validation))
    calibrated_target_probability = calibrator.predict_proba(target_logit)[:, 1]
    calibrated_validation_probability = calibrator.predict_proba(validation_logit)[:, 1]
    return calibrated_validation_probability, calibrated_target_probability


def _calculate_performance(y_true, probability, threshold=None):
    y_true = _as_binary_array(y_true)
    probability = np.asarray(probability, dtype=float)

    results = {
        "AUROC": float(roc_auc_score(y_true, probability)),
        "AUPRC": float(average_precision_score(y_true, probability)),
        "Brier score": float(brier_score_loss(y_true, probability)),
    }

    if threshold is not None:
        predicted = (probability >= float(threshold)).astype(int)
        tn, fp, fn, tp = confusion_matrix(
            y_true, predicted, labels=[0, 1]
        ).ravel()

        results.update({
            "Accuracy": float(accuracy_score(y_true, predicted)),
            "Sensitivity": float(recall_score(y_true, predicted, zero_division=0)),
            "Specificity": float(tn / (tn + fp)) if (tn + fp) else np.nan,
            "PPV": float(precision_score(y_true, predicted, zero_division=0)),
            "NPV": float(tn / (tn + fn)) if (tn + fn) else np.nan,
            "F1 score": float(f1_score(y_true, predicted, zero_division=0)),
            "True negatives": int(tn),
            "False positives": int(fp),
            "False negatives": int(fn),
            "True positives": int(tp),
        })
    return results


def _stratified_bootstrap_ci(
    y_true,
    probability,
    threshold=None,
    n_bootstrap=2000,
    seed=20260608,
):
    y_true = _as_binary_array(y_true)
    probability = np.asarray(probability, dtype=float)

    positive_indices = np.flatnonzero(y_true == 1)
    negative_indices = np.flatnonzero(y_true == 0)
    if len(positive_indices) == 0 or len(negative_indices) == 0:
        raise ValueError("Both outcome classes are required for bootstrap confidence intervals.")

    point_estimates = _calculate_performance(y_true, probability, threshold)
    metric_names = [
        metric for metric in point_estimates
        if metric not in {
            "True negatives", "False positives", "False negatives", "True positives"
        }
    ]

    rng = np.random.default_rng(seed)
    bootstrap_values = {metric: [] for metric in metric_names}

    for _ in range(int(n_bootstrap)):
        sampled_positive = rng.choice(
            positive_indices, size=len(positive_indices), replace=True
        )
        sampled_negative = rng.choice(
            negative_indices, size=len(negative_indices), replace=True
        )
        sampled_indices = np.concatenate([sampled_positive, sampled_negative])
        rng.shuffle(sampled_indices)

        replicate = _calculate_performance(
            y_true[sampled_indices],
            probability[sampled_indices],
            threshold,
        )
        for metric in metric_names:
            bootstrap_values[metric].append(replicate[metric])

    rows = []
    for metric in metric_names:
        values = np.asarray(bootstrap_values[metric], dtype=float)
        rows.append({
            "Metric": metric,
            "Estimate": point_estimates[metric],
            "CI_lower": float(np.nanpercentile(values, 2.5)),
            "CI_upper": float(np.nanpercentile(values, 97.5)),
        })

    confusion_counts = {
        key: value for key, value in point_estimates.items()
        if key in {
            "True negatives", "False positives", "False negatives", "True positives"
        }
    }
    return pd.DataFrame(rows), confusion_counts


def _set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _add_dataframe_table(document, dataframe, font_size=8):
    table = document.add_table(rows=1, cols=len(dataframe.columns))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"

    header_row = table.rows[0]
    header_cells = header_row.cells
    header_properties = header_row._tr.get_or_add_trPr()
    repeat_header = OxmlElement("w:tblHeader")
    repeat_header.set(qn("w:val"), "true")
    header_properties.append(repeat_header)
    for index, column in enumerate(dataframe.columns):
        header_cells[index].text = str(column)
        _set_cell_shading(header_cells[index], "D9EAF7")
        header_cells[index].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for paragraph in header_cells[index].paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(font_size)

    for _, row in dataframe.iterrows():
        cells = table.add_row().cells
        for index, value in enumerate(row):
            if isinstance(value, (float, np.floating)):
                text = f"{value:.4f}"
            else:
                text = str(value)
            cells[index].text = text
            cells[index].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for paragraph in cells[index].paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.size = Pt(font_size)
    return table


# -------------------- 2. Dataset and outcome-event counts --------------------
dataset_rows = []
for dataset_name, y_dataset in [
    ("Overall cohort", pd.concat([pd.Series(y_train), pd.Series(y_val), pd.Series(y_test)])),
    ("Training set", y_train),
    ("Validation set", y_val),
    ("Test set", y_test),
]:
    y_array = _as_binary_array(y_dataset)
    event_count = int(y_array.sum())
    total_count = int(len(y_array))
    dataset_rows.append({
        "Dataset": dataset_name,
        "Participants": total_count,
        "SAD events": event_count,
        "Non-events": total_count - event_count,
        "Event rate (%)": 100.0 * event_count / total_count,
    })

dataset_counts_df = pd.DataFrame(dataset_rows)
dataset_counts_df.to_csv(output_counts_csv, index=False, encoding="utf-8-sig")

training_events = int(_as_binary_array(y_train).sum())
full_predictor_count = int(len(numerical) + len(categorical))
simplified_predictor_count = int(catboost_shap_result["best_k"])
full_events_per_predictor = training_events / full_predictor_count
simplified_events_per_predictor = training_events / simplified_predictor_count


# -------------------- 3. Final-model predictions and thresholds --------------------
full_features = list(numerical) + list(categorical)
full_categorical = [feature for feature in categorical if feature in full_features]
simplified_features = list(catboost_shap_result["best_features"])
simplified_categorical = [
    feature for feature in categorical if feature in simplified_features
]

X_val_full = _prepare_catboost_frame(X_val, full_features, full_categorical)
X_test_full = _prepare_catboost_frame(X_test, full_features, full_categorical)
X_val_simplified = _prepare_catboost_frame(
    X_val, simplified_features, simplified_categorical
)
X_test_simplified = _prepare_catboost_frame(
    X_test, simplified_features, simplified_categorical
)

full_model = catboost_shap_result["full_model"]
simplified_model = catboost_shap_result["best_model"]

full_val_raw_probability = full_model.predict_proba(X_val_full)[:, 1]
full_test_raw_probability = full_model.predict_proba(X_test_full)[:, 1]
simplified_val_probability = simplified_model.predict_proba(X_val_simplified)[:, 1]
simplified_test_probability = simplified_model.predict_proba(X_test_simplified)[:, 1]

# Use the exact calibrated CatBoost test probabilities and threshold already generated
# by the main model-comparison pipeline whenever available.
if (
    "model_probas" in globals()
    and isinstance(model_probas, dict)
    and "CatBoost" in model_probas
    and "thresholds_info" in globals()
    and isinstance(thresholds_info, dict)
    and "CatBoost" in thresholds_info
):
    full_test_probability = np.asarray(model_probas["CatBoost"], dtype=float)
    full_threshold = float(thresholds_info["CatBoost"]["Threshold"])
    full_calibration_description = str(
        thresholds_info["CatBoost"].get("Calibration", "sigmoid_validation")
    )

    full_val_probability, _ = _fit_sigmoid_calibrator(
        full_val_raw_probability,
        y_val,
        full_test_raw_probability,
    )
    full_probability_source = (
        "Existing CatBoost probabilities from model_probas; sigmoid calibration "
        "was fitted on the validation set in the main pipeline."
    )
else:
    full_val_probability, full_test_probability = _fit_sigmoid_calibrator(
        full_val_raw_probability,
        y_val,
        full_test_raw_probability,
    )
    full_threshold = _youden_threshold(y_val, full_val_probability)
    full_calibration_description = "sigmoid_validation_reconstructed"
    full_probability_source = (
        "Sigmoid calibration reconstructed from the final full CatBoost model "
        "using the validation set."
    )

# The original simplification cell did not define a classification threshold.
# This cell adds a threshold selected exclusively in the validation set by the
# Youden index and applies it unchanged to the test set.
simplified_threshold = _youden_threshold(y_val, simplified_val_probability)


# -------------------- 4. Bootstrap 95% confidence intervals --------------------
performance_frames = []

for model_label, dataset_label, y_dataset, probability, threshold in [
    (
        "Full CatBoost",
        "Validation",
        y_val,
        full_val_probability,
        None,
    ),
    (
        "Full CatBoost",
        "Test",
        y_test,
        full_test_probability,
        full_threshold,
    ),
    (
        f"SHAP-simplified CatBoost ({simplified_predictor_count} predictors)",
        "Validation",
        y_val,
        simplified_val_probability,
        None,
    ),
    (
        f"SHAP-simplified CatBoost ({simplified_predictor_count} predictors)",
        "Test",
        y_test,
        simplified_test_probability,
        simplified_threshold,
    ),
]:
    ci_df, confusion_counts = _stratified_bootstrap_ci(
        y_true=y_dataset,
        probability=probability,
        threshold=threshold,
        n_bootstrap=BOOTSTRAP_REPLICATES,
        seed=BOOTSTRAP_SEED,
    )
    ci_df.insert(0, "Dataset", dataset_label)
    ci_df.insert(0, "Model", model_label)
    ci_df["Threshold"] = np.nan if threshold is None else float(threshold)

    for count_name, count_value in confusion_counts.items():
        ci_df[count_name] = int(count_value)

    performance_frames.append(ci_df)

performance_df = pd.concat(performance_frames, ignore_index=True)
performance_df["Estimate (95% CI)"] = performance_df.apply(
    lambda row: (
        f"{row['Estimate']:.4f} "
        f"({row['CI_lower']:.4f}-{row['CI_upper']:.4f})"
    ),
    axis=1,
)
performance_df.to_csv(output_performance_csv, index=False, encoding="utf-8-sig")


# -------------------- 5. Exact class-imbalance and calibration methods --------------------
imbalance_methods_df = pd.DataFrame([
    {
        "Model": "XGBoost",
        "Training data": "Original imbalanced training data",
        "Imbalance method": "scale_pos_weight tuned over 2 and 3",
        "Probability calibration": "Sigmoid calibration fitted on validation set",
        "Threshold method": "Youden index in validation set",
    },
    {
        "Model": "CatBoost",
        "Training data": "Original imbalanced training data",
        "Imbalance method": "scale_pos_weight tuned over 2 and 3",
        "Probability calibration": "Sigmoid calibration fitted on validation set",
        "Threshold method": "Youden index in validation set",
    },
    {
        "Model": "LightGBM",
        "Training data": "Original imbalanced training data",
        "Imbalance method": "scale_pos_weight tuned over 2 and 3",
        "Probability calibration": "Sigmoid calibration fitted on validation set",
        "Threshold method": "Youden index in validation set",
    },
    {
        "Model": "Logistic regression",
        "Training data": "SMOTE-Tomek-resampled training data",
        "Imbalance method": "SMOTETomek(sampling_strategy=0.33, random_state=42) plus class_weight='balanced'",
        "Probability calibration": "No additional calibration",
        "Threshold method": "Youden index in validation set",
    },
    {
        "Model": "Ridge classifier",
        "Training data": "SMOTE-Tomek-resampled training data",
        "Imbalance method": "SMOTETomek(sampling_strategy=0.33, random_state=42)",
        "Probability calibration": "Isotonic calibration with 5-fold cross-validation",
        "Threshold method": "Youden index in validation set",
    },
    {
        "Model": "Support vector machine",
        "Training data": "SMOTE-Tomek-resampled training data",
        "Imbalance method": "SMOTETomek(sampling_strategy=0.33, random_state=42) plus class_weight='balanced'",
        "Probability calibration": "Isotonic calibration with 5-fold cross-validation",
        "Threshold method": "Youden index in validation set",
    },
    {
        "Model": "K-nearest neighbors",
        "Training data": "Original imbalanced training data",
        "Imbalance method": "No resampling or class weighting",
        "Probability calibration": "Isotonic calibration with 5-fold cross-validation",
        "Threshold method": "Maximum F1 score in validation set",
    },
    {
        "Model": "Decision tree",
        "Training data": "SMOTE-Tomek-resampled training data",
        "Imbalance method": "SMOTETomek(sampling_strategy=0.33, random_state=42)",
        "Probability calibration": "Sigmoid calibration fitted on validation set",
        "Threshold method": "Youden index in validation set",
    },
    {
        "Model": "Random forest",
        "Training data": "SMOTE-Tomek-resampled training data",
        "Imbalance method": "SMOTETomek(sampling_strategy=0.33, random_state=42) plus class_weight='balanced'",
        "Probability calibration": "Sigmoid calibration fitted on validation set",
        "Threshold method": "Youden index in validation set",
    },
])
imbalance_methods_df.to_csv(output_imbalance_csv, index=False, encoding="utf-8-sig")


# -------------------- 6. Final CatBoost hyperparameters --------------------
explicit_parameter_names = [
    "iterations",
    "learning_rate",
    "depth",
    "l2_leaf_reg",
    "min_data_in_leaf",
    "grow_policy",
    "scale_pos_weight",
    "random_state",
    "verbose",
]
final_model_parameters = simplified_model.get_params()

hyperparameter_rows = []
for parameter_name in explicit_parameter_names:
    if parameter_name in final_model_parameters:
        parameter_value = final_model_parameters[parameter_name]
    elif parameter_name == "random_state":
        parameter_value = 42
    elif parameter_name == "verbose":
        parameter_value = 0
    else:
        parameter_value = "Not returned by get_params()"
    hyperparameter_rows.append({
        "Parameter": parameter_name,
        "Final value": parameter_value,
    })

hyperparameters_df = pd.DataFrame(hyperparameter_rows)
hyperparameters_df.to_csv(
    output_hyperparameters_csv, index=False, encoding="utf-8-sig"
)


# -------------------- 7. Word export --------------------
document = Document()
section = document.sections[0]
section.top_margin = Inches(0.65)
section.bottom_margin = Inches(0.65)
section.left_margin = Inches(0.65)
section.right_margin = Inches(0.65)

title = document.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
title_run = title.add_run(
    "Supplementary Methods and Results for TRIPOD+AI Reporting"
)
title_run.bold = True
title_run.font.size = Pt(15)

subtitle = document.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
subtitle_run = subtitle.add_run(
    "Prediction of sepsis-associated delirium within 7 days after sepsis diagnosis"
)
subtitle_run.italic = True
subtitle_run.font.size = Pt(10)

document.add_heading("1. Dataset partition and outcome-event counts", level=1)
document.add_paragraph(
    "All eligible patients in the available retrospective cohort were included. "
    "The cohort was first divided into an 80% development portion and a 20% "
    "independent test set using stratified random sampling (random_state=42). "
    "The development portion was then divided at an 80:20 ratio into training "
    "and validation sets, producing final proportions of 64%, 16%, and 20%."
)
_add_dataframe_table(document, dataset_counts_df, font_size=8)

document.add_heading("2. Study-size basis", level=1)
document.add_paragraph(
    "No a priori sample-size calculation was performed because the study used "
    "all eligible patients available in MIMIC-IV after application of the "
    "prespecified eligibility criteria. The training set contained "
    f"{training_events:,} SAD events. The full model used {full_predictor_count} "
    f"predictors ({full_events_per_predictor:.1f} training events per predictor), "
    f"and the SHAP-simplified model used {simplified_predictor_count} predictors "
    f"({simplified_events_per_predictor:.1f} training events per predictor). "
    "These event-to-predictor ratios are descriptive indicators of data support "
    "and are not presented as a substitute for a formal prediction-model "
    "sample-size calculation. Precision of model performance is quantified by "
    "95% confidence intervals in Section 6."
)

document.add_heading(
    "3. Class-imbalance handling, probability calibration, and threshold selection",
    level=1,
)
document.add_paragraph(
    "The exact procedures implemented in the model-comparison code are shown "
    "below. SMOTE-Tomek resampling was applied only to the training data. "
    "Classification thresholds were selected using the validation set and then "
    "applied unchanged to the independent test set."
)
_add_dataframe_table(document, imbalance_methods_df, font_size=7)

document.add_paragraph(
    f"For the selected full CatBoost model, the validation-derived threshold was "
    f"{full_threshold:.6f}; the recorded calibration status was "
    f"'{full_calibration_description}'. {full_probability_source}"
)
document.add_paragraph(
    f"The original SHAP-simplification cell generated probabilities but did not "
    f"define a binary classification threshold. For complete TRIPOD+AI reporting, "
    f"this export cell selected a threshold of {simplified_threshold:.6f} by "
    f"maximizing the Youden index in the validation set and applied it unchanged "
    f"to the test set."
)
document.add_paragraph(
    "The low-, intermediate-, and high-risk groups shown in the risk-stratification "
    "analysis were defined by tertiles of predicted probabilities in the test set. "
    "Those tertiles were used for descriptive risk-stratification analysis and "
    "should not be interpreted as prespecified clinical decision thresholds."
)

document.add_heading("4. Hyperparameter optimization", level=1)
document.add_paragraph(
    "Hyperparameters were evaluated with five-fold stratified cross-validation "
    "with shuffling and random_state=42, using AUROC as the optimization metric. "
    "For CatBoost, the fixed parameter combinations were evaluated manually "
    "because of GridSearchCV compatibility considerations. The only parameter "
    "with more than one tested value in the final CatBoost search was "
    "scale_pos_weight (2 or 3); scale_pos_weight=2 achieved the higher mean "
    "cross-validated AUROC and was retained."
)
_add_dataframe_table(document, hyperparameters_df, font_size=8)

document.add_heading("5. SHAP-guided model simplification", level=1)
document.add_paragraph(
    "Predictors were ranked by mean absolute SHAP value from the 19-predictor "
    "CatBoost model. Models containing the top k predictors were fitted for "
    "k=8 through k=19. The number of predictors was selected by the maximum "
    "validation-set AUROC (selection_strategy='max_val'). This procedure selected "
    f"{simplified_predictor_count} predictors."
)
feature_table = pd.DataFrame({
    "Order": np.arange(1, simplified_predictor_count + 1),
    "Predictor": simplified_features,
    "Display name": (
        display_feature_names(simplified_features)
        if "display_feature_names" in globals()
        else simplified_features
    ),
})
_add_dataframe_table(document, feature_table, font_size=8)

document.add_heading("6. Model performance with 95% confidence intervals", level=1)
document.add_paragraph(
    f"Confidence intervals were calculated using {BOOTSTRAP_REPLICATES:,} "
    "stratified nonparametric bootstrap replicates (seed="
    f"{BOOTSTRAP_SEED}). Positive and negative observations were resampled "
    "separately with replacement to preserve the observed class counts in each "
    "replicate. For threshold-dependent metrics, the threshold selected in the "
    "validation set was held fixed during test-set bootstrapping."
)

performance_display_df = performance_df[
    ["Model", "Dataset", "Metric", "Estimate (95% CI)", "Threshold"]
].copy()
performance_display_df["Threshold"] = performance_display_df["Threshold"].apply(
    lambda value: "" if pd.isna(value) else f"{value:.6f}"
)
_add_dataframe_table(document, performance_display_df, font_size=7)

document.add_heading("7. Reproducibility details", level=1)
reproducibility_df = pd.DataFrame([
    {"Component": "Python", "Version": platform.python_version()},
    {"Component": "scikit-learn", "Version": sklearn.__version__},
    {"Component": "CatBoost", "Version": catboost.__version__},
    {"Component": "Bootstrap seed", "Version": BOOTSTRAP_SEED},
    {"Component": "Bootstrap replicates", "Version": BOOTSTRAP_REPLICATES},
])
_add_dataframe_table(document, reproducibility_df, font_size=8)

document.add_paragraph(
    "Generated automatically from the final in-memory models and data partitions "
    "of the Jupyter notebook. The accompanying CSV files contain machine-readable "
    "versions of all reported tables."
)

document.save(output_docx)

print("=" * 88)
print("TRIPOD+AI reporting export completed.")
print(f"Word document: {output_docx}")
print(f"Dataset counts: {output_counts_csv}")
print(f"Performance with 95% CIs: {output_performance_csv}")
print(f"Final hyperparameters: {output_hyperparameters_csv}")
print(f"Class-imbalance methods: {output_imbalance_csv}")
print(f"Full CatBoost threshold: {full_threshold:.6f}")
print(f"Simplified CatBoost threshold: {simplified_threshold:.6f}")
print("=" * 88)

display(dataset_counts_df)
display(hyperparameters_df)
display(performance_display_df)

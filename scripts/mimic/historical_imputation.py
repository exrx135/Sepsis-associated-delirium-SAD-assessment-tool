# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

from IPython.display import display

# %% Original notebook code cell 2
import pandas as pd

file_path = str(_sad_private_path("mimic_study", '数据清洗后插补/SAD_cleaned_ordered.csv'))

data = pd.read_csv(file_path)

print("=" * 80)
print("数据维度：")
print(data.shape)

print("\n" + "=" * 80)
print("各变量数据类型：")
print(data.dtypes)

object_cols = data.select_dtypes(include=["object"]).columns.tolist()

print("\n" + "=" * 80)
print("Object类型变量：")
print(object_cols)

print("\nObject变量数量：", len(object_cols))

for col in object_cols:
    print("\n" + "=" * 80)
    print(f"变量名：{col}")
    print(f"唯一值个数：{data[col].nunique(dropna=False)}")
    print("前10个取值：")
    print(data[col].head(10))

# %% Original notebook code cell 3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import missingno as msno
import miceforest as mf
from sklearn.metrics import mean_squared_error
import numpy as np
import os

# 设置 Pandas 显示选项，确保不截断输出
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)

# 定义颜色
original_color = "#4C72B0"
imputed_color = "#C44E52"


# =========================
# 变量显示名称映射（仅用于输出展示；不改变插补流程中的原始变量名）
# =========================
feature_display_names = {
    "SAD_7days": "SAD",
    "sad_7days": "SAD",
    "subject_id": "Subject ID",
    "hadm_id": "Hospital admission ID",
    "stay_id": "ICU stay ID",
    "patientunitstayid": "ICU stay ID",

    "gender": "Sex",
    "sex": "Sex",
    "admission_age": "Age",
    "weight": "Weight",
    "los_before_icu": "Pre-ICU LOS",
    "hypertension": "Hypertension",
    "diabetes": "Diabetes",
    "chronic_neurological": "Chronic neurological disease",
    "chronic_lung_disease": "Chronic lung disease",
    "chronic_liver_disease": "Chronic liver disease",
    "chronic_kidney_disease": "Chronic kidney disease",
    "chronic_heart_disease": "Chronic heart disease",

    "invasive_vent_12h_24h_pre_dx": "Mechanical ventilation",
    "vasoactive_agent": "Vasoactive agent",

    "avg_heart_rate": "Heart rate",
    "avg_hr": "Heart rate",
    "avg_sbp": "SBP",
    "avg_dbp": "DBP",
    "avg_mbp": "MAP",
    "avg_resp_rate": "Respiratory rate",
    "avg_temperature": "Temperature",
    "avg_temp": "Temperature",
    "avg_spo2": "SpO₂",

    "avg_po2": "PaO₂",
    "avg_pao2": "PaO₂",
    "avg_pco2": "PaCO₂",
    "avg_paco2": "PaCO₂",
    "avg_po2fio2": "PaO₂/FiO₂",
    "avg_ph": "pH",
    "avg_baseexcess": "Base excess",
    "avg_bicarbonate": "Bicarbonate",
    "avg_totalco2": "Total CO₂",
    "avg_lactate": "Lactate",

    "avg_hematocrit": "Hematocrit",
    "avg_hemoglobin": "Hemoglobin",
    "avg_mch": "MCH",
    "avg_mchc": "MCHC",
    "avg_mcv": "MCV",
    "avg_platelet": "Platelet count",
    "avg_plt": "Platelet count",
    "avg_rbc": "RBC count",
    "avg_rdw": "RDW",
    "avg_wbc": "WBC count",

    "avg_inr": "INR",
    "avg_pt": "PT",
    "avg_ptt": "PTT",

    "avg_aniongap": "Anion gap",
    "avg_anion_gap": "Anion gap",
    "avg_bun": "BUN",
    "avg_calcium": "Calcium",
    "avg_chloride": "Chloride",
    "avg_creatinine": "Creatinine",
    "avg_sodium": "Sodium",
    "avg_potassium": "Potassium",
    "avg_glucose": "Glucose",

    "hr_before_sepsis_urineoutput": "Urine output",
    "urineoutput": "Urine output",
    "urineoutput_24h": "Urine output",

    "sofa": "SOFA",
    "avg_sofa": "SOFA",
    "sirs": "SIRS"
}

def display_name(col):
    return feature_display_names.get(col, col)

def display_index(obj):
    return obj.rename(index=feature_display_names)

def display_columns(df):
    return df.rename(columns=feature_display_names)


# =========================
# 读取数据
# =========================
file_path = str(_sad_private_path("mimic_study", '数据清洗后插补/SAD_cleaned_ordered.csv'))
output_dir = str(_sad_private_path("mimic_study", '数据清洗后插补'))
os.makedirs(output_dir, exist_ok=True)

data = pd.read_csv(file_path)


# 查看数据基本信息
def inspect_data(df):
    print("Data shape:", df.shape)
    print("Columns:", df.columns)
    print("Data types:\n", df.dtypes)
    print("Summary statistics:\n", df.describe(include='all'))

inspect_data(data)


# =========================
# 稳健处理 gender / sex 列
# 不会因为原始值已经是0/1或存在其他编码而被错误映射成全缺失
# =========================
def safe_encode_sex_column(df):
    sex_col = None

    if "gender" in df.columns:
        sex_col = "gender"
    elif "sex" in df.columns:
        sex_col = "sex"

    if sex_col is None:
        print("未检测到 gender 或 sex 列，跳过性别编码。")
        return df

    original_missing = df[sex_col].isnull().sum()
    unique_before = df[sex_col].dropna().unique()
    print(f"{sex_col} 编码前唯一值:", unique_before)

    # 如果已经是数值型，且主要是0/1，则直接保留
    if pd.api.types.is_numeric_dtype(df[sex_col]):
        print(f"{sex_col} 已为数值型，保留原始编码。")
        print(f"{sex_col} 缺失数: {df[sex_col].isnull().sum()}")
        return df

    # 字符型时进行稳健映射
    s = df[sex_col].astype(str).str.strip().str.upper()

    mapping = {
        "M": 1,
        "MALE": 1,
        "MAN": 1,
        "1": 1,
        "F": 0,
        "FEMALE": 0,
        "WOMAN": 0,
        "0": 0
    }

    mapped = s.map(mapping)
    mapped[df[sex_col].isnull()] = np.nan

    new_missing = mapped.isnull().sum()
    additional_missing = new_missing - original_missing

    if additional_missing > 0:
        unmapped_values = df.loc[mapped.isnull() & df[sex_col].notnull(), sex_col].unique()
        print(f"警告：{sex_col} 中有 {additional_missing} 个非缺失值未能映射。")
        print("未能映射的原始值:", unmapped_values)
        print("为避免人为制造缺失，保留原始列不变。")
    else:
        df[sex_col] = mapped.astype(float)
        print(f"{sex_col} 已成功编码为 M/Male=1, F/Female=0。")

    print(f"{sex_col} 编码后缺失数: {df[sex_col].isnull().sum()}")

    return df


data = safe_encode_sex_column(data)


# =========================
# 检查缺失值 + 保存可用缺失值图
# =========================
def check_missingness(df, output_dir):
    print("Missing values per column:\n", df.isnull().sum())

    missing_summary = pd.DataFrame({
        "Variable": df.columns,
        "Display_name": [display_name(col) for col in df.columns],
        "Missing_count": df.isnull().sum().values,
        "Missing_percentage": df.isnull().mean().values * 100,
        "Complete_count": df.notnull().sum().values,
        "Complete_percentage": df.notnull().mean().values * 100,
        "Original_order": np.arange(len(df.columns))
    })

    missing_summary.to_csv(
        os.path.join(output_dir, "SAD_missingness_summary.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    # 只展示存在缺失的变量
    plot_df_all_missing = missing_summary[missing_summary["Missing_count"] > 0].copy()

    if plot_df_all_missing.empty:
        print("No missing values detected. Missingness plots were not generated.")
        return missing_summary

    # =========================
    # A. 缺失率横向柱状图
    # 只显示有缺失的变量，按缺失率从高到低排序
    # =========================
    plot_df_bar = plot_df_all_missing.sort_values(
        "Missing_percentage",
        ascending=True
    ).reset_index(drop=True)

    fig_height = max(8, 0.30 * len(plot_df_bar))
    fig, ax = plt.subplots(figsize=(10, fig_height))

    ax.barh(
        plot_df_bar["Display_name"],
        plot_df_bar["Missing_percentage"],
        color="#4C72B0",
        edgecolor="black",
        linewidth=0.4
    )

    ax.axvline(
        30,
        color="#C44E52",
        linestyle="--",
        linewidth=1.5,
        label="30% threshold"
    )

    ax.set_xlabel("Missing percentage (%)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Variable", fontsize=12, fontweight="bold")
    ax.set_title("Missingness of Variables With Missing Values", fontsize=15, fontweight="bold")

    ax.tick_params(axis="y", labelsize=9)
    ax.tick_params(axis="x", labelsize=10)

    ax.set_xlim(0, max(35, plot_df_bar["Missing_percentage"].max() * 1.10))
    ax.grid(axis="x", linestyle="--", alpha=0.25)

    ax.legend(
        frameon=False,
        fontsize=10,
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0
    )

    sns.despine()
    plt.tight_layout(rect=[0, 0, 0.88, 1])

    bar_png = os.path.join(output_dir, "SAD_missingness_percentage_barplot_missing_variables_only.png")
    bar_tif = os.path.join(output_dir, "SAD_missingness_percentage_barplot_missing_variables_only.tif")
    bar_pdf = os.path.join(output_dir, "SAD_missingness_percentage_barplot_missing_variables_only.pdf")

    plt.savefig(bar_png, dpi=600, bbox_inches="tight")
    plt.savefig(bar_tif, dpi=600, bbox_inches="tight")
    plt.savefig(bar_pdf, bbox_inches="tight")
    plt.show()

    print(f"Missingness barplot 已保存: {bar_png}")
    print(f"Missingness barplot TIFF 已保存: {bar_tif}")
    print(f"Missingness barplot PDF 已保存: {bar_pdf}")

    # =========================
    # B. 自定义 Missingness matrix
    # 只显示有缺失的变量，但按原始数据列顺序排列
    # 行=变量，列=患者/观测；变量名与矩阵严格对应
    # 蓝色=observed，白色=missing
    # =========================
    plot_df_matrix = plot_df_all_missing.sort_values(
        "Original_order",
        ascending=True
    ).reset_index(drop=True)

    missing_cols = plot_df_matrix["Variable"].tolist()

    matrix_bool = df[missing_cols].notnull().T
    matrix_bool.index = [display_name(col) for col in missing_cols]

    fig_height_matrix = max(8, 0.25 * len(missing_cols))
    fig_width_matrix = 14

    fig, ax = plt.subplots(figsize=(fig_width_matrix, fig_height_matrix))

    ax.imshow(
        matrix_bool.values,
        aspect="auto",
        interpolation="nearest",
        cmap=plt.cm.Blues,
        vmin=0,
        vmax=1
    )

    ax.set_yticks(np.arange(len(matrix_bool.index)))
    ax.set_yticklabels(matrix_bool.index, fontsize=8)

    n_obs = matrix_bool.shape[1]
    ax.set_xticks([0, n_obs - 1])
    ax.set_xticklabels(["1", str(n_obs)], fontsize=10)

    ax.set_xlabel("Patients", fontsize=12, fontweight="bold")
    ax.set_ylabel("Variable", fontsize=12, fontweight="bold")
    ax.set_title(
        "Missing Data Pattern for Variables With Missing Values",
        fontsize=15,
        fontweight="bold",
        pad=15
    )

    observed_patch = plt.Line2D(
        [0],
        [0],
        marker="s",
        color="w",
        label="Observed",
        markerfacecolor="#4C72B0",
        markersize=10
    )

    missing_patch = plt.Line2D(
        [0],
        [0],
        marker="s",
        color="w",
        label="Missing",
        markerfacecolor="white",
        markeredgecolor="black",
        markersize=10
    )

    ax.legend(
        handles=[observed_patch, missing_patch],
        frameon=False,
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        fontsize=10,
        borderaxespad=0
    )

    plt.tight_layout(rect=[0, 0, 0.88, 1])

    matrix_png = os.path.join(output_dir, "SAD_missingness_matrix_missing_variables_only.png")
    matrix_tif = os.path.join(output_dir, "SAD_missingness_matrix_missing_variables_only.tif")
    matrix_pdf = os.path.join(output_dir, "SAD_missingness_matrix_missing_variables_only.pdf")

    plt.savefig(matrix_png, dpi=600, bbox_inches="tight")
    plt.savefig(matrix_tif, dpi=600, bbox_inches="tight")
    plt.savefig(matrix_pdf, bbox_inches="tight")
    plt.show()

    print(f"Missingness matrix 已保存: {matrix_png}")
    print(f"Missingness matrix TIFF 已保存: {matrix_tif}")
    print(f"Missingness matrix PDF 已保存: {matrix_pdf}")

    return missing_summary


missing_summary = check_missingness(data, output_dir)


# =========================
# 删除缺失值 >30% 的列
# =========================
missing_percentage = data.isnull().sum() / len(data) * 100

# 原始逻辑：只检查 avg_lactate 及其之前的变量
sirs_index = data.columns.get_loc('avg_lactate')
columns_to_check = data.columns[:sirs_index + 1]

columns_to_drop = columns_to_check[missing_percentage[columns_to_check] > 30]
data = data.drop(columns=columns_to_drop)

print("被删除的列名：", [display_name(col) for col in columns_to_drop])


# =========================
# 提取需要插补的变量
# =========================
# 若 avg_lactate 因缺失率 >30% 被删除，则不再重新查找 avg_lactate；
# 直接使用 columns_to_check 中仍然保留的变量，保持原始流程逻辑。
columns_to_impute = [col for col in columns_to_check if col in data.columns]
data_to_impute = data[columns_to_impute]


# 记录插补前每个变量的缺失值数量
missing_counts_before = data_to_impute.isnull().sum()


# 创建 ImputationKernel 对象
kernel = mf.ImputationKernel(data_to_impute)


# 运行 MICE 插补
kernel.mice(iterations=5, verbose=True)


# 获取插补后的完整数据
imputed_data = kernel.complete_data(dataset=0)


# 替换原始数据中的插补列
data[columns_to_impute] = imputed_data


# 记录插补后每个变量的缺失值数量
missing_counts_after = data[columns_to_impute].isnull().sum()


# 计算每个变量被插补的数量
imputed_counts = missing_counts_before - missing_counts_after
print("每个变量的缺失值数量（即插补数量）：")
print(display_index(imputed_counts))


# 筛选出有插补值的变量（插补数量大于0）
columns_with_imputations = imputed_counts[imputed_counts > 0].index.tolist()


# 提取有缺失值的变量
data_with_missing = data_to_impute[columns_with_imputations].copy()


# 提取仅插补部分的数据
imputed_only_data = pd.DataFrame(
    index=data_with_missing.index,
    columns=data_with_missing.columns,
    data=np.nan
)

for col in columns_with_imputations:
    missing_mask = data_with_missing[col].isnull()
    imputed_only_data.loc[missing_mask, col] = imputed_data.loc[missing_mask, col]


# 打印有插补值的变量
if not columns_with_imputations:
    print("没有变量被插补。")
else:
    print("有插补值的变量及其插补数量：")
    print(display_index(imputed_counts[columns_with_imputations]))


# =========================
# 绘制密度分布图
# =========================
if columns_with_imputations:
    num_vars = len(columns_with_imputations)
    cols_per_row = 4
    num_rows = (num_vars + cols_per_row - 1) // cols_per_row

    fig, axes = plt.subplots(
        nrows=num_rows,
        ncols=cols_per_row,
        figsize=(20, 5 * num_rows)
    )

    axes = axes.flatten()

    for i, col in enumerate(columns_with_imputations):
        original_values = data_with_missing[col].dropna()
        imputed_values = imputed_only_data[col].dropna()

        if original_values.nunique() > 1:
            sns.kdeplot(
                original_values,
                ax=axes[i],
                label='Original',
                linestyle="--",
                color=original_color,
                warn_singular=False
            )
        else:
            print(f"Warning: Column '{col}' has no variance in original data.")

        if imputed_values.nunique() > 1:
            sns.kdeplot(
                imputed_values,
                ax=axes[i],
                label='Imputed',
                color=imputed_color,
                warn_singular=False
            )
        else:
            print(f"Warning: Column '{col}' has no variance in imputed data.")

        axes[i].set_title(display_name(col))

        handles, labels = axes[i].get_legend_handles_labels()
        if handles:
            axes[i].legend(handles, labels, loc='upper right', fontsize=8)
        else:
            axes[i].legend([], [], frameon=False)

    for j in range(i + 1, num_rows * cols_per_row):
        fig.delaxes(axes[j])

    plt.tight_layout()

    plt.savefig(
        os.path.join(output_dir, "SAD_density_plot.png"),
        dpi=600,
        bbox_inches="tight"
    )

    plt.savefig(
        os.path.join(output_dir, "SAD_density_plot.tif"),
        dpi=600,
        bbox_inches="tight"
    )

    plt.show()


# =========================
# 绘制散点图
# =========================
if columns_with_imputations:
    num_vars = len(columns_with_imputations)
    cols_per_row = 5
    num_rows = (num_vars + cols_per_row - 1) // cols_per_row

    fig, axes = plt.subplots(
        nrows=num_rows,
        ncols=cols_per_row,
        figsize=(20, 5 * num_rows)
    )

    axes = axes.flatten()

    for i, col in enumerate(columns_with_imputations):
        sns.scatterplot(
            x=data_with_missing.index,
            y=data_with_missing[col],
            label='Original',
            alpha=0.7,
            color=original_color,
            ax=axes[i]
        )

        sns.scatterplot(
            x=imputed_only_data.index,
            y=imputed_only_data[col],
            label='Imputed',
            alpha=0.7,
            color=imputed_color,
            ax=axes[i]
        )

        axes[i].set_title(f'Scatter Plot of {display_name(col)}')
        axes[i].legend()

    for j in range(i + 1, num_rows * cols_per_row):
        fig.delaxes(axes[j])

    plt.tight_layout()

    plt.savefig(
        os.path.join(output_dir, "SAD_scatter_plot.png"),
        dpi=600,
        bbox_inches="tight"
    )

    plt.savefig(
        os.path.join(output_dir, "SAD_scatter_plot.tif"),
        dpi=600,
        bbox_inches="tight"
    )

    plt.show()

# %% Original notebook code cell 4
# 绘制箱线图
if columns_with_imputations:
    # 计算子图的行列数
    num_vars = len(columns_with_imputations)
    cols_per_row = 5  # 每行显示5个子图
    num_rows = (num_vars + cols_per_row - 1) // cols_per_row  # 计算需要的行数

    # 创建足够的子图
    fig, axes = plt.subplots(nrows=num_rows, ncols=cols_per_row, figsize=(25, 5 * num_rows))
    axes = axes.flatten()  # 将二维的axes数组展平为一维，方便后续操作

    # 绘制每个进行了插补的变量的箱线图
    for i, col in enumerate(columns_with_imputations):
        # 准备数据
        plot_data = pd.DataFrame({
            'Value': pd.concat([data_with_missing[col].dropna(), imputed_only_data[col].dropna()]),
            'Type': ['Original'] * len(data_with_missing[col].dropna()) + ['Imputed'] * len(imputed_only_data[col].dropna())
        })

        # 绘制箱线图
        sns.boxplot(x='Type', y='Value', data=plot_data, ax=axes[i], hue='Type', palette={'Original': 'blue', 'Imputed': 'red'}, legend=False)
        axes[i].set_title(display_name(col))
        axes[i].set_xlabel('')  # 隐藏x轴标签
        axes[i].set_ylabel('')  # 隐藏y轴标签
        axes[i].tick_params(axis='both', labelsize=8)  # 调整刻度字体大小

    # 隐藏剩余的空白子图
    for j in range(i + 1, num_rows * cols_per_row):
        fig.delaxes(axes[j])

    # 调整布局
    plt.tight_layout()
    # 保存图片
    plt.savefig(
        str(_sad_private_path("mimic_study", '数据清洗后插补/SAD_boxplot.png')),
        dpi=600,
        bbox_inches="tight"
    )

    print("箱线图已保存：SAD_boxplot.png")

    plt.show()

# %% Original notebook code cell 5
# 如果使用了多重插补，可以对多次插补结果进行汇总
if kernel.num_datasets > 1:
    # 提取多次插补结果
    imputed_datasets = [kernel.complete_data(dataset=i) for i in range(kernel.num_datasets)]

    # 计算多次插补结果的均值和标准差
    imputed_mean = pd.concat(imputed_datasets).groupby(level=0).mean()
    imputed_std = pd.concat(imputed_datasets).groupby(level=0).std()

    # 打印汇总结果
    print("Mean of imputed datasets:\n", imputed_mean)
    print("Standard deviation of imputed datasets:\n", imputed_std)

# 汇总评估结果
summary = pd.DataFrame(columns=['Original Mean', 'Imputed Mean', 'Original Std', 'Imputed Std'])

for col in columns_with_imputations:
    original_mean = data_with_missing[col].mean()
    imputed_mean = imputed_only_data[col].mean()
    original_std = data_with_missing[col].std()
    imputed_std = imputed_only_data[col].std()


    summary.loc[col] = [original_mean, imputed_mean, original_std, imputed_std]

print(display_index(summary))

# %% Original notebook code cell 6
inspect_data(imputed_data)

# %% Original notebook code cell 7
output_file_path = str(_sad_private_path("mimic_study", '数据清洗后插补/imputed_merge_data.csv'))
data.to_csv(output_file_path, index=False)
print(f"插补后的数据已导出到 {output_file_path}")

# 同时导出仅用于论文表格/图形展示的变量名映射版本
# 注意：该文件仅改变列名显示，不改变任何插补过程和数据数值。
display_output_file_path = str(_sad_private_path("mimic_study", '数据清洗后插补/imputed_merge_data_display_names.csv'))
display_columns(data).to_csv(display_output_file_path, index=False, encoding="utf-8-sig")
print(f"插补后的展示变量名版本已导出到 {display_output_file_path}")

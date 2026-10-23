# ========================================
# Main Table 1: Baseline Characteristics by SAD Status
# ========================================

library(dplyr)
library(purrr)
library(openxlsx)

# ================================
# 路径设置
# ================================
data_dir <- Sys.getenv("SAD_TABLE_DIR", "./private_inputs/tables")

input_path <- file.path(data_dir, "imputed_merge_data.csv")

csv_path  <- file.path(data_dir, "Table1_Baseline_Characteristics_by_SAD.csv")
xlsx_path <- file.path(data_dir, "Table1_Baseline_Characteristics_by_SAD.xlsx")

# ================================
# 读取数据
# ================================
df <- read.csv(input_path, header = TRUE, stringsAsFactors = FALSE)

# ================================
# 分组变量
# ================================
outcome_var <- "sad_7days"

df[[outcome_var]] <- factor(
  df[[outcome_var]],
  levels = c(0, 1),
  labels = c("Non-SAD", "SAD")
)

# ================================
# 变量定义
# ================================
demographics_vars <- c(
  "gender",
  "admission_age",
  "weight",
  "los_before_icu",
  "los_hospital",
  "los_icu"
)

vital_signs_vars <- c(
  "avg_heart_rate",
  "avg_sbp",
  "avg_dbp",
  "avg_mbp",
  "avg_sbp_ni",
  "avg_dbp_ni",
  "avg_mbp_ni",
  "avg_resp_rate",
  "avg_temperature",
  "avg_spo2"
)

comorbidity_vars <- c(
  "chronic_heart_disease",
  "hypertension",
  "chronic_lung_disease",
  "chronic_neurological",
  "chronic_liver_disease",
  "chronic_kidney_disease",
  "diabetes"
)

treatment_vars <- c(
  "dopamine",
  "epinephrine",
  "norepinephrine",
  "phenylephrine",
  "vasopressin",
  "dobutamine",
  "milrinone",
  "vasoactive_agent",
  "neuroblock",
  "acei",
  "nsaid",
  "penicillin",
  "cephalosporin",
  "carbapenem",
  "macrolide",
  "lincosamide",
  "aminoglycoside",
  "quinolone",
  "tetracycline",
  "other_antibiotic",
  "antibiotic",
  "invasive_vent_12h_24h_pre_dx"
)

laboratory_vars <- c(
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
)

clinical_score_vars <- c(
  "final_gcs_score",
  "apsiii",
  "charlson_comorbidity_index",
  "lods",
  "oasis",
  "sapsii"
)

# 主表默认不纳入死亡结局，如需纳入可改为 TRUE
include_mortality_outcomes <- FALSE

mortality_vars <- c(
  "d3_mortality_icu",
  "d7_mortality_icu",
  "d28_mortality_icu",
  "mortality_icu"
)

# ================================
# 变量显示名映射
# ================================
var_labels <- c(
  gender = "Male sex",
  admission_age = "Age, years",
  weight = "Weight, kg",
  los_before_icu = "Pre-ICU length of stay, days",
  los_hospital = "Hospital length of stay, days",
  los_icu = "ICU length of stay, days",
  
  avg_heart_rate = "Heart rate, beats/min",
  avg_sbp = "Systolic blood pressure, mmHg",
  avg_dbp = "Diastolic blood pressure, mmHg",
  avg_mbp = "Mean arterial pressure, mmHg",
  avg_sbp_ni = "Non-invasive systolic blood pressure, mmHg",
  avg_dbp_ni = "Non-invasive diastolic blood pressure, mmHg",
  avg_mbp_ni = "Non-invasive mean arterial pressure, mmHg",
  avg_resp_rate = "Respiratory rate, breaths/min",
  avg_temperature = "Temperature, °C",
  avg_spo2 = "SpO2, %",
  
  chronic_heart_disease = "Chronic heart disease",
  hypertension = "Hypertension",
  chronic_lung_disease = "Chronic pulmonary disease",
  chronic_neurological = "Chronic neurological disease",
  chronic_liver_disease = "Chronic liver disease",
  chronic_kidney_disease = "Chronic kidney disease",
  diabetes = "Diabetes mellitus",
  
  dopamine = "Dopamine",
  epinephrine = "Epinephrine",
  norepinephrine = "Norepinephrine",
  phenylephrine = "Phenylephrine",
  vasopressin = "Vasopressin",
  dobutamine = "Dobutamine",
  milrinone = "Milrinone",
  vasoactive_agent = "Any vasoactive agent",
  neuroblock = "Neuromuscular blocking agent",
  acei = "ACE inhibitor",
  nsaid = "NSAID",
  penicillin = "Penicillin",
  cephalosporin = "Cephalosporin",
  carbapenem = "Carbapenem",
  macrolide = "Macrolide",
  lincosamide = "Lincosamide",
  aminoglycoside = "Aminoglycoside",
  quinolone = "Quinolone",
  tetracycline = "Tetracycline",
  other_antibiotic = "Other antibiotic",
  antibiotic = "Any antibiotic",
  invasive_vent_12h_24h_pre_dx = "Invasive mechanical ventilation",
  
  avg_glucose = "Glucose, mg/dL",
  hr_before_sepsis_urineoutput = "Urine output, mL",
  avg_hematocrit = "Hematocrit, %",
  avg_hemoglobin = "Hemoglobin, g/dL",
  avg_mch = "Mean corpuscular hemoglobin, pg",
  avg_mchc = "Mean corpuscular hemoglobin concentration, g/dL",
  avg_mcv = "Mean corpuscular volume, fL",
  avg_platelet = "Platelet count, 10^9/L",
  avg_rbc = "Red blood cell count, 10^12/L",
  avg_rdw = "Red cell distribution width, %",
  avg_wbc = "White blood cell count, 10^9/L",
  avg_inr = "International normalized ratio",
  avg_pt = "Prothrombin time, s",
  avg_ptt = "Partial thromboplastin time, s",
  avg_aniongap = "Anion gap, mmol/L",
  avg_bicarbonate = "Bicarbonate, mmol/L",
  avg_bun = "Blood urea nitrogen, mg/dL",
  avg_calcium = "Calcium, mg/dL",
  avg_chloride = "Chloride, mmol/L",
  avg_creatinine = "Creatinine, mg/dL",
  avg_sodium = "Sodium, mmol/L",
  avg_potassium = "Potassium, mmol/L",
  avg_po2 = "PaO2, mmHg",
  avg_pco2 = "PaCO2, mmHg",
  avg_ph = "pH",
  avg_baseexcess = "Base excess, mmol/L",
  avg_totalco2 = "Total CO2, mmol/L",
  
  final_gcs_score = "Glasgow Coma Scale score",
  apsiii = "Acute Physiology Score III",
  charlson_comorbidity_index = "Charlson comorbidity index",
  lods = "Logistic Organ Dysfunction System score",
  oasis = "Oxford Acute Severity of Illness Score",
  sapsii = "Simplified Acute Physiology Score II",
  
  d3_mortality_icu = "3-day mortality",
  d7_mortality_icu = "7-day mortality",
  d28_mortality_icu = "28-day mortality",
  mortality_icu = "ICU mortality"
)
get_label <- function(var_name) {
  ifelse(var_name %in% names(var_labels), var_labels[[var_name]], var_name)
}

# ================================
# 自动保留数据中存在的变量
# ================================
demographics_vars <- intersect(demographics_vars, names(df))
vital_signs_vars <- intersect(vital_signs_vars, names(df))
comorbidity_vars <- intersect(comorbidity_vars, names(df))
treatment_vars <- intersect(treatment_vars, names(df))
laboratory_vars <- intersect(laboratory_vars, names(df))
clinical_score_vars <- intersect(clinical_score_vars, names(df))
mortality_vars <- intersect(mortality_vars, names(df))

continuous_vars <- c(
  setdiff(demographics_vars, "gender"),
  vital_signs_vars,
  laboratory_vars,
  clinical_score_vars
)

categorical_vars <- c(
  "gender",
  comorbidity_vars,
  treatment_vars
)

if (include_mortality_outcomes) {
  categorical_vars <- c(categorical_vars, mortality_vars)
}

continuous_vars <- intersect(continuous_vars, names(df))
categorical_vars <- intersect(categorical_vars, names(df))

# ================================
# 工具函数
# ================================
format_p <- function(p) {
  if (is.na(p)) return("")
  if (p < 0.001) return("<0.001")
  sprintf("%.3f", p)
}

format_mean_sd <- function(x) {
  x <- as.numeric(x)
  x <- x[!is.na(x)]
  sprintf("%.2f ± %.2f", mean(x), sd(x))
}

format_median_iqr <- function(x) {
  x <- as.numeric(x)
  x <- x[!is.na(x)]
  q <- quantile(x, c(0.25, 0.75), na.rm = TRUE)
  sprintf("%.2f (%.2f–%.2f)", median(x), q[1], q[2])
}

safe_shapiro_p <- function(x) {
  x <- as.numeric(x)
  x <- x[!is.na(x)]
  if (length(x) < 3) return(NA)
  if (length(unique(x)) < 3) return(NA)
  if (length(x) > 5000) {
    set.seed(123)
    x <- sample(x, 5000)
  }
  suppressWarnings(shapiro.test(x)$p.value)
}

make_section_row <- function(section_name) {
  data.frame(
    Variable = section_name,
    `Non-SAD` = "",
    SAD = "",
    `P-value` = "",
    Significance = "",
    check.names = FALSE
  )
}

get_significance <- function(p_text) {
  if (p_text == "") return("")
  if (p_text == "<0.001") return("***")
  p <- suppressWarnings(as.numeric(p_text))
  if (is.na(p)) return("")
  if (p < 0.001) return("***")
  if (p < 0.01) return("**")
  if (p < 0.05) return("*")
  return("")
}

# ================================
# 连续变量分析
# ================================
analyze_continuous <- function(var_name, data) {
  
  temp <- data %>%
    select(all_of(outcome_var), all_of(var_name)) %>%
    rename(group = all_of(outcome_var), value = all_of(var_name)) %>%
    filter(!is.na(group), !is.na(value)) %>%
    mutate(value = as.numeric(value))
  
  groups <- levels(data[[outcome_var]])
  
  shapiro_p <- sapply(groups, function(g) {
    safe_shapiro_p(temp$value[temp$group == g])
  })
  
  is_normal <- all(!is.na(shapiro_p) & shapiro_p > 0.05)
  
  desc_values <- sapply(groups, function(g) {
    x <- temp$value[temp$group == g]
    if (is_normal) {
      format_mean_sd(x)
    } else {
      format_median_iqr(x)
    }
  })
  
  if (is_normal) {
    test <- tryCatch(
      t.test(value ~ group, data = temp),
      error = function(e) NULL
    )
  } else {
    test <- tryCatch(
      wilcox.test(value ~ group, data = temp),
      error = function(e) NULL
    )
  }
  
  p_val <- ifelse(is.null(test), NA, test$p.value)
  p_text <- format_p(p_val)
  
  data.frame(
    Variable = get_label(var_name),
    `Non-SAD` = desc_values["Non-SAD"],
    SAD = desc_values["SAD"],
    `P-value` = p_text,
    Significance = get_significance(p_text),
    check.names = FALSE
  )
}

# ================================
# 二分类变量分析
# ================================
analyze_categorical <- function(var_name, data) {
  
  temp <- data %>%
    select(all_of(outcome_var), all_of(var_name)) %>%
    rename(group = all_of(outcome_var), value = all_of(var_name)) %>%
    filter(!is.na(group), !is.na(value)) %>%
    mutate(
      group = factor(group, levels = c("Non-SAD", "SAD")),
      value = as.numeric(value)
    )
  
  groups <- levels(temp$group)
  
  desc_values <- sapply(groups, function(g) {
    vals <- temp$value[temp$group == g]
    n_total <- length(vals)
    n1 <- sum(vals == 1, na.rm = TRUE)
    sprintf("%d (%.2f%%)", n1, n1 / n_total * 100)
  })
  
  tab <- table(temp$group, temp$value)
  
  test <- tryCatch({
    expected <- suppressWarnings(chisq.test(tab, correct = FALSE)$expected)
    if (any(expected < 5)) {
      fisher.test(tab, simulate.p.value = TRUE, B = 10000)
    } else {
      chisq.test(tab, correct = FALSE)
    }
  }, error = function(e) NULL)
  
  p_val <- ifelse(is.null(test), NA, test$p.value)
  p_text <- format_p(p_val)
  
  data.frame(
    Variable = get_label(var_name),
    `Non-SAD` = desc_values["Non-SAD"],
    SAD = desc_values["SAD"],
    `P-value` = p_text,
    Significance = get_significance(p_text),
    check.names = FALSE
  )
}

# ================================
# 执行分析
# ================================
continuous_results <- map_dfr(continuous_vars, analyze_continuous, data = df)
categorical_results <- map_dfr(categorical_vars, analyze_categorical, data = df)

all_results <- bind_rows(continuous_results, categorical_results)

get_var_rows <- function(var_vector, table_data) {
  labels <- sapply(var_vector, get_label)
  table_data %>% filter(Variable %in% labels)
}

# ================================
# 生成主表
# ================================
table1 <- bind_rows(
  make_section_row("Demographics"),
  get_var_rows(demographics_vars, all_results),
  
  make_section_row("Vital signs"),
  get_var_rows(vital_signs_vars, all_results),
  
  make_section_row("Comorbidities"),
  get_var_rows(comorbidity_vars, all_results),
  
  make_section_row("Treatment"),
  get_var_rows(treatment_vars, all_results),
  
  make_section_row("Laboratory measurements"),
  get_var_rows(laboratory_vars, all_results),
  
  make_section_row("Clinical scores"),
  get_var_rows(clinical_score_vars, all_results)
)

if (include_mortality_outcomes) {
  table1 <- bind_rows(
    table1,
    make_section_row("Mortality outcomes"),
    get_var_rows(mortality_vars, all_results)
  )
}

# ================================
# 保存结果
# ================================
write.csv(table1, csv_path, row.names = FALSE, na = "", fileEncoding = "UTF-8")
write.xlsx(table1, file = xlsx_path, rowNames = FALSE, overwrite = TRUE)

# ================================
# 输出提示
# ================================
print(table1)

cat("\nTable 1 已生成：\n")
cat(csv_path, "\n")
cat(xlsx_path, "\n")
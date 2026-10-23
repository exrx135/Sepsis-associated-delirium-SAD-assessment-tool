# ========================================
# Supplementary Table S3
# Detailed statistical comparison by SAD status
# ========================================

library(dplyr)
library(purrr)
library(car)
library(openxlsx)

# ================================
# 路径设置
# ================================
data_dir <- Sys.getenv("SAD_TABLE_DIR", "./private_inputs/tables")

input_path <- file.path(data_dir, "imputed_merge_data.csv")

csv_path  <- file.path(data_dir, "Supplementary_Table_S3_Detailed_Statistics_by_SAD.csv")
xlsx_path <- file.path(data_dir, "Supplementary_Table_S3_Detailed_Statistics_by_SAD.xlsx")

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
  sapsii = "Simplified Acute Physiology Score II"
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

continuous_vars <- intersect(continuous_vars, names(df))
categorical_vars <- intersect(categorical_vars, names(df))

# ================================
# 工具函数
# ================================
format_p <- function(p) {
  if (is.na(p)) return("")
  if (p < 0.001) return("<0.001")
  sprintf("%.4f", p)
}

mean_ci <- function(x) {
  x <- as.numeric(x)
  x <- x[!is.na(x)]
  n <- length(x)
  m <- mean(x)
  se <- sd(x) / sqrt(n)
  ci <- qt(0.975, df = n - 1) * se
  sprintf("%.2f (%.2f-%.2f)", m, m - ci, m + ci)
}

median_iqr <- function(x) {
  x <- as.numeric(x)
  x <- x[!is.na(x)]
  q <- quantile(x, c(0.25, 0.75), na.rm = TRUE)
  sprintf("%.2f (%.2f-%.2f)", median(x), q[1], q[2])
}

n_percent <- function(n, total) {
  if (total == 0) return("0 (0.00%)")
  sprintf("%d (%.2f%%)", n, n / total * 100)
}

safe_shapiro_p <- function(x) {
  x <- as.numeric(x)
  x <- x[!is.na(x)]
  
  if (length(x) < 3) return(NA)
  if (length(unique(x)) < 3) return(NA)
  
  # shapiro.test 在 R 中最多支持 5000 个样本
  if (length(x) > 5000) {
    set.seed(123)
    x <- sample(x, 5000)
  }
  
  suppressWarnings(shapiro.test(x)$p.value)
}

make_section_row <- function(section_name) {
  data.frame(
    Variable = section_name,
    `Non-SAD` = "-",
    SAD = "-",
    Statistical_Method = "-",
    `P-value` = "-",
    Effect_Method = "-",
    Effect_Size = "-",
    Normality_Test = "-",
    Normality_Result = "-",
    check.names = FALSE
  )
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
  
  x0 <- temp$value[temp$group == "Non-SAD"]
  x1 <- temp$value[temp$group == "SAD"]
  
  if (length(x0) < 3 || length(x1) < 3) {
    return(data.frame(
      Variable = get_label(var_name),
      `Non-SAD` = "",
      SAD = "",
      Statistical_Method = "",
      `P-value` = "",
      Effect_Method = "",
      Effect_Size = "",
      Normality_Test = "Shapiro-Wilk test",
      Normality_Result = "Insufficient sample size",
      check.names = FALSE
    ))
  }
  
  shapiro0 <- safe_shapiro_p(x0)
  shapiro1 <- safe_shapiro_p(x1)
  
  is_normal <- all(!is.na(c(shapiro0, shapiro1)) & c(shapiro0, shapiro1) > 0.05)
  
  normality_result <- ifelse(
    is_normal,
    "Approximately normal",
    "Non-normal"
  )
  
  if (is_normal) {
    
    levene_p <- tryCatch(
      car::leveneTest(value ~ group, data = temp)$`Pr(>F)`[1],
      error = function(e) NA
    )
    
    var_equal <- ifelse(is.na(levene_p), FALSE, levene_p > 0.05)
    
    test <- tryCatch(
      t.test(value ~ group, data = temp, var.equal = var_equal),
      error = function(e) NULL
    )
    
    statistical_method <- ifelse(var_equal, "Student's t-test", "Welch t-test")
    
    nonsad_value <- mean_ci(x0)
    sad_value <- mean_ci(x1)
    
    n0 <- length(x0)
    n1 <- length(x1)
    sd0 <- sd(x0)
    sd1 <- sd(x1)
    mean0 <- mean(x0)
    mean1 <- mean(x1)
    
    pooled_sd <- sqrt(((n0 - 1) * sd0^2 + (n1 - 1) * sd1^2) / (n0 + n1 - 2))
    
    if (pooled_sd == 0 || is.na(pooled_sd)) {
      effect_size <- ""
    } else {
      cohen_d <- (mean1 - mean0) / pooled_sd
      correction <- 1 - (3 / (4 * (n0 + n1) - 9))
      hedges_g <- cohen_d * correction
      effect_size <- sprintf("%.4f", hedges_g)
    }
    
    effect_method <- "Hedges' g, SAD vs Non-SAD"
    
  } else {
    
    test <- tryCatch(
      wilcox.test(value ~ group, data = temp, exact = FALSE),
      error = function(e) NULL
    )
    
    statistical_method <- "Wilcoxon rank-sum test"
    
    nonsad_value <- median_iqr(x0)
    sad_value <- median_iqr(x1)
    
    n0 <- length(x0)
    n1 <- length(x1)
    
    ranks <- rank(temp$value)
    rank_sum0 <- sum(ranks[temp$group == "Non-SAD"])
    U0 <- rank_sum0 - n0 * (n0 + 1) / 2
    U1 <- n0 * n1 - U0
    
    rank_biserial <- (U1 - U0) / (n0 * n1)
    
    effect_method <- "Rank-biserial correlation, SAD vs Non-SAD"
    effect_size <- sprintf("%.4f", rank_biserial)
  }
  
  p_val <- ifelse(is.null(test), NA, test$p.value)
  
  data.frame(
    Variable = get_label(var_name),
    `Non-SAD` = nonsad_value,
    SAD = sad_value,
    Statistical_Method = statistical_method,
    `P-value` = format_p(p_val),
    Effect_Method = effect_method,
    Effect_Size = effect_size,
    Normality_Test = "Shapiro-Wilk test",
    Normality_Result = normality_result,
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
      value = factor(as.numeric(value), levels = c(0, 1))
    )
  
  tab <- table(temp$group, temp$value)
  
  chi_tmp <- suppressWarnings(chisq.test(tab, correct = FALSE))
  
  if (any(chi_tmp$expected < 5)) {
    test <- fisher.test(tab)
    statistical_method <- "Fisher's exact test"
  } else {
    test <- chisq.test(tab, correct = FALSE)
    statistical_method <- "Chi-square test"
  }
  
  p <- test$p.value
  
  total_nonsad <- sum(tab["Non-SAD", ])
  total_sad <- sum(tab["SAD", ])
  
  n_nonsad <- ifelse("1" %in% colnames(tab), tab["Non-SAD", "1"], 0)
  n_sad <- ifelse("1" %in% colnames(tab), tab["SAD", "1"], 0)
  
  # Odds ratio: SAD group, level 1 vs level 0
  if (all(c("0", "1") %in% colnames(tab))) {
    
    a <- tab["SAD", "1"]
    b <- tab["Non-SAD", "1"]
    c <- tab["SAD", "0"]
    d <- tab["Non-SAD", "0"]
    
    if (any(c(a, b, c, d) == 0)) {
      a <- a + 0.5
      b <- b + 0.5
      c <- c + 0.5
      d <- d + 0.5
    }
    
    OR <- as.numeric((a * d) / (b * c))
    effect_method <- "Odds ratio for SAD, level 1 vs level 0"
    effect_size <- sprintf("%.4f", OR)
    
  } else {
    effect_method <- "Odds ratio"
    effect_size <- ""
  }
  
  data.frame(
    Variable = get_label(var_name),
    `Non-SAD` = n_percent(n_nonsad, total_nonsad),
    SAD = n_percent(n_sad, total_sad),
    Statistical_Method = statistical_method,
    `P-value` = format_p(p),
    Effect_Method = effect_method,
    Effect_Size = effect_size,
    Normality_Test = "",
    Normality_Result = "",
    check.names = FALSE
  )
}

# ================================
# 执行分析
# ================================
continuous_results <- map_dfr(continuous_vars, analyze_continuous, data = df)
categorical_results <- map_dfr(categorical_vars, analyze_categorical, data = df)

all_results <- bind_rows(
  continuous_results,
  categorical_results
)

# ================================
# 提取与排序
# ================================
get_var_rows <- function(var_vector, table_data) {
  labels <- sapply(var_vector, get_label)
  table_data %>% filter(Variable %in% labels)
}

# ================================
# 最终 Supplementary Table S3
# ================================
supp_table_s1 <- bind_rows(
  
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

# ================================
# 保存结果
# ================================
write.csv(
  supp_table_s1,
  csv_path,
  row.names = FALSE,
  na = "",
  fileEncoding = "UTF-8"
)

write.xlsx(
  supp_table_s1,
  file = xlsx_path,
  rowNames = FALSE,
  overwrite = TRUE
)

print(supp_table_s1)

cat("\nSupplementary Table S3 已生成：\n")
cat(csv_path, "\n")
cat(xlsx_path, "\n")
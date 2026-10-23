clear all
set more off

global rawdir "./private_inputs/raw"
global datadir "./private_inputs/cohort"
global outdir "./private_outputs/cohort"

capture mkdir "$outdir"
capture log close
log using "$outdir\define_SAD_7days_exclude_pre24_positive.log", replace text

tempname flow
postfile `flow' str120 step double n using "$outdir\cohort_flow_exclude_pre24_positive.dta", replace

import delimited "$rawdir\CAM-ICU_core.csv", clear varnames(1) stringcols(_all)
gen double cam_icu_time = clock(charttime, "DMYhms")
replace cam_icu_time = clock(charttime, "YMDhms") if missing(cam_icu_time)
format cam_icu_time %tc
destring subject_id hadm_id stay_id itemid, replace force
drop if missing(subject_id)
drop if missing(stay_id)
drop if missing(cam_icu_time)
gen cam_icu1 = 0
replace cam_icu1 = 1 if itemid == 228300 & value == "Yes (Continue)"
gen cam_icu2 = 0
replace cam_icu2 = 1 if itemid == 228301 & value == "Yes (3 or more errors, then Continue)"
gen cam_icu3 = 0
replace cam_icu3 = 1 if itemid == 228302 & value == "Yes"
gen cam_icu4 = 0
replace cam_icu4 = 1 if itemid == 228303 & value == "Yes"
gen cam_any_record = 1
collapse (max) cam_icu1 cam_icu2 cam_icu3 cam_icu4 cam_any_record, by(subject_id hadm_id stay_id cam_icu_time)
gen cam_icu_positive = 0
replace cam_icu_positive = 1 if cam_icu1 == 1 & cam_icu2 == 1 & (cam_icu3 == 1 | cam_icu4 == 1)
gen cam_icu_source = "core"
save "$outdir\cam_icu_all_core.dta", replace

import delimited "$rawdir\CAM-ICU_backup.csv", clear varnames(1) stringcols(_all)
gen double cam_icu_time = clock(charttime, "DMYhms")
replace cam_icu_time = clock(charttime, "YMDhms") if missing(cam_icu_time)
format cam_icu_time %tc
destring subject_id hadm_id stay_id itemid, replace force
drop if missing(subject_id)
drop if missing(stay_id)
drop if missing(cam_icu_time)
gen cam_icu1 = 0
replace cam_icu1 = 1 if itemid == 228337 & value == "Yes"
gen cam_icu2 = 0
replace cam_icu2 = 1 if itemid == 228336 & value == "Yes"
gen cam_icu3 = 0
replace cam_icu3 = 1 if itemid == 228334 & value == "Yes"
gen cam_icu4 = 0
replace cam_icu4 = 1 if itemid == 228335 & value == "Yes"
gen cam_any_record = 1
collapse (max) cam_icu1 cam_icu2 cam_icu3 cam_icu4 cam_any_record, by(subject_id hadm_id stay_id cam_icu_time)
gen cam_icu_positive = 0
replace cam_icu_positive = 1 if cam_icu1 == 1 & cam_icu2 == 1 & (cam_icu3 == 1 | cam_icu4 == 1)
gen cam_icu_source = "backup"
save "$outdir\cam_icu_all_backup.dta", replace

import delimited "$rawdir\CAM-ICU_oldsys.csv", clear varnames(1) stringcols(_all)
gen double cam_icu_time = clock(charttime, "DMYhms")
replace cam_icu_time = clock(charttime, "YMDhms") if missing(cam_icu_time)
format cam_icu_time %tc
destring subject_id hadm_id stay_id itemid, replace force
drop if missing(subject_id)
drop if missing(stay_id)
drop if missing(cam_icu_time)
gen cam_icu1 = 0
replace cam_icu1 = 1 if itemid == 229326 & value == "Yes"
gen cam_icu2 = 0
replace cam_icu2 = 1 if itemid == 229325 & value == "Yes"
gen cam_icu3 = .
gen cam_icu4 = 0
replace cam_icu4 = 1 if itemid == 229324 & value == "Yes"
gen cam_any_record = 1
collapse (max) cam_icu1 cam_icu2 cam_icu3 cam_icu4 cam_any_record, by(subject_id hadm_id stay_id cam_icu_time)
gen cam_icu_positive = 0
replace cam_icu_positive = 1 if cam_icu1 == 1 & cam_icu2 == 1 & cam_icu4 == 1
gen cam_icu_source = "oldsys"
save "$outdir\cam_icu_all_oldsys.dta", replace

use "$outdir\cam_icu_all_core.dta", clear
append using "$outdir\cam_icu_all_backup.dta"
append using "$outdir\cam_icu_all_oldsys.dta"
duplicates drop subject_id hadm_id stay_id cam_icu_time, force
gen long cam_id = _n
count
post `flow' ("All CAM-ICU assessment time points") (r(N))
save "$outdir\cam_icu_all_raw.dta", replace

import delimited "$rawdir\RASS.csv", clear varnames(1) stringcols(_all)
gen double rass_time = clock(charttime, "DMYhms")
replace rass_time = clock(charttime, "YMDhms") if missing(rass_time)
format rass_time %tc
destring subject_id hadm_id stay_id itemid valuenum, replace force
keep if itemid == 228096
rename valuenum rass_score
keep subject_id hadm_id stay_id rass_time rass_score value
drop if missing(subject_id)
drop if missing(stay_id)
drop if missing(rass_time)
drop if missing(rass_score)
duplicates drop subject_id hadm_id stay_id rass_time rass_score, force
save "$outdir\rass_clean.dta", replace

capture which rangejoin
if _rc ssc install rangejoin

use "$outdir\cam_icu_all_raw.dta", clear
gen double cam_start = cam_icu_time - 60*60*1000
gen double cam_end = cam_icu_time + 60*60*1000
format cam_start cam_end %tc
rangejoin rass_time cam_start cam_end using "$outdir\rass_clean.dta", by(subject_id hadm_id stay_id)
gen double time_diff_ms = abs(rass_time - cam_icu_time)
gen double time_diff_min = time_diff_ms / 60000
bysort cam_id (time_diff_ms): keep if _n == 1
gen rass_available = !missing(rass_score)
gen valid_cam_icu = 0
replace valid_cam_icu = 1 if rass_available == 1 & rass_score >= -3
gen invalid_deep_sedation_or_coma = 0
replace invalid_deep_sedation_or_coma = 1 if rass_available == 1 & rass_score < -3
label define camvalid 0 "Invalid or no RASS within +/-1h" 1 "Valid CAM-ICU with RASS >= -3"
label values valid_cam_icu camvalid
save "$outdir\cam_icu_all_with_nearest_rass_1h.dta", replace
count
post `flow' ("CAM-ICU assessments after nearest RASS matching") (r(N))
count if valid_cam_icu == 1
post `flow' ("Valid CAM-ICU assessments with RASS >= -3") (r(N))
count if valid_cam_icu == 0
post `flow' ("Invalid CAM-ICU assessments or no eligible RASS") (r(N))

keep if valid_cam_icu == 1
gen valid_cam_positive = cam_icu_positive
gen valid_cam_negative = 1 - cam_icu_positive
save "$outdir\valid_cam_icu_all_1h.dta", replace
count
post `flow' ("All valid CAM-ICU assessments retained") (r(N))
count if valid_cam_positive == 1
post `flow' ("Valid CAM-ICU positive assessments") (r(N))
count if valid_cam_negative == 1
post `flow' ("Valid CAM-ICU negative assessments") (r(N))

import delimited "$datadir\sepsis患者的ICU住院人口统计学各种时间.csv", clear varnames(1) stringcols(_all)
destring subject_id hadm_id stay_id hospstay_seq icustay_seq hospital_expire_flag mortality_icu d3_mortality_icu d7_mortality_icu d28_mortality_icu, replace force
destring los_hospital admission_age los_icu, replace force
gen double diagnosis_time_dt = clock(diagnosis_time, "DMYhms")
replace diagnosis_time_dt = clock(diagnosis_time, "YMDhms") if missing(diagnosis_time_dt)
format diagnosis_time_dt %tc
gen double admittime_dt = clock(admittime, "DMYhms")
replace admittime_dt = clock(admittime, "YMDhms") if missing(admittime_dt)
format admittime_dt %tc
gen double dischtime_dt = clock(dischtime, "DMYhms")
replace dischtime_dt = clock(dischtime, "YMDhms") if missing(dischtime_dt)
format dischtime_dt %tc
gen double icu_intime_dt = clock(icu_intime, "DMYhms")
replace icu_intime_dt = clock(icu_intime, "YMDhms") if missing(icu_intime_dt)
format icu_intime_dt %tc
gen double icu_outtime_dt = clock(icu_outtime, "DMYhms")
replace icu_outtime_dt = clock(icu_outtime, "YMDhms") if missing(icu_outtime_dt)
format icu_outtime_dt %tc
gen first_hosp = 0
replace first_hosp = 1 if first_hosp_stay == "t" | first_hosp_stay == "true" | first_hosp_stay == "TRUE" | hospstay_seq == 1
gen first_icu = 0
replace first_icu = 1 if first_icu_stay == "t" | first_icu_stay == "true" | first_icu_stay == "TRUE" | icustay_seq == 1
drop if missing(subject_id)
drop if missing(stay_id)
drop if missing(diagnosis_time_dt)
duplicates drop subject_id hadm_id stay_id, force
count
post `flow' ("Initial sepsis ICU cohort") (r(N))
keep if first_hosp == 1
count
post `flow' ("After restricting to first hospital stay") (r(N))
keep if first_icu == 1
count
post `flow' ("After restricting to first ICU stay") (r(N))
capture drop _merge
save "$outdir\sepsis_first_hosp_first_icu.dta", replace

use "$outdir\valid_cam_icu_all_1h.dta", clear
capture drop _merge
merge m:1 subject_id hadm_id stay_id using "$outdir\sepsis_first_hosp_first_icu.dta"
keep if _merge == 3
drop _merge
count
post `flow' ("Valid CAM-ICU assessments linked to first-stay sepsis cohort") (r(N))
save "$outdir\valid_cam_icu_linked_to_sepsis.dta", replace

use "$outdir\valid_cam_icu_linked_to_sepsis.dta", clear
gen pre24_cam = 0
replace pre24_cam = 1 if cam_icu_time >= diagnosis_time_dt - 24*60*60*1000 & cam_icu_time < diagnosis_time_dt
gen pre24_valid_cam_positive_n = pre24_cam * valid_cam_positive
gen pre24_valid_cam_any_n = pre24_cam
gen first_pre24_positive_temp = cam_icu_time if pre24_cam == 1 & valid_cam_positive == 1
collapse (sum) pre24_valid_cam_any_n pre24_valid_cam_positive_n (min) first_pre24_positive_time = first_pre24_positive_temp, by(subject_id hadm_id stay_id)
format first_pre24_positive_time %tc
gen pre24_delirium_positive = 0
replace pre24_delirium_positive = 1 if pre24_valid_cam_positive_n >= 1
label define pre24pos 0 "No documented pre-sepsis delirium within 24h" 1 "Documented pre-sepsis delirium within 24h"
label values pre24_delirium_positive pre24pos
capture drop _merge
save "$outdir\pre24_positive_status.dta", replace

use "$outdir\sepsis_first_hosp_first_icu.dta", clear
capture drop _merge
merge 1:1 subject_id hadm_id stay_id using "$outdir\pre24_positive_status.dta"
replace pre24_valid_cam_any_n = 0 if missing(pre24_valid_cam_any_n)
replace pre24_valid_cam_positive_n = 0 if missing(pre24_valid_cam_positive_n)
replace pre24_delirium_positive = 0 if missing(pre24_delirium_positive)
gen exclude_pre24_delirium = 0
replace exclude_pre24_delirium = 1 if pre24_delirium_positive == 1
count
post `flow' ("First-stay sepsis cohort before excluding pre-24h CAM-ICU positive") (r(N))
count if exclude_pre24_delirium == 1
post `flow' ("Excluded: valid CAM-ICU positive during 24h before sepsis diagnosis") (r(N))
keep if exclude_pre24_delirium == 0
count
post `flow' ("Eligible cohort after excluding pre-24h CAM-ICU positive") (r(N))
drop _merge
save "$outdir\eligible_cohort_exclude_pre24_positive.dta", replace
export delimited using "$outdir\eligible_cohort_exclude_pre24_positive.csv", replace

use "$outdir\valid_cam_icu_linked_to_sepsis.dta", clear
capture drop _merge
merge m:1 subject_id hadm_id stay_id using "$outdir\eligible_cohort_exclude_pre24_positive.dta", keepusing(pre24_valid_cam_any_n pre24_valid_cam_positive_n pre24_delirium_positive)
keep if _merge == 3
drop _merge
gen post7_cam = 0
replace post7_cam = 1 if cam_icu_time >= diagnosis_time_dt & cam_icu_time <= diagnosis_time_dt + 7*24*60*60*1000
keep if post7_cam == 1
gen post7_valid_cam_n = 1
gen post7_valid_cam_positive_n = valid_cam_positive
gen post7_valid_cam_negative_n = valid_cam_negative
gen pos_time_temp = cam_icu_time if valid_cam_positive == 1
gen neg_time_temp = cam_icu_time if valid_cam_negative == 1
collapse (sum) post7_valid_cam_n post7_valid_cam_positive_n post7_valid_cam_negative_n (min) first_post7_cam_time = cam_icu_time (min) first_post7_positive_time = pos_time_temp (min) first_post7_negative_time = neg_time_temp, by(subject_id hadm_id stay_id)
format first_post7_cam_time first_post7_positive_time first_post7_negative_time %tc
gen SAD_7days = .
replace SAD_7days = 1 if post7_valid_cam_positive_n >= 1
replace SAD_7days = 0 if post7_valid_cam_positive_n == 0 & post7_valid_cam_negative_n >= 1
label variable SAD_7days "SAD-7days"
label define sad7 0 "No SAD within 7 days" 1 "SAD within 7 days"
label values SAD_7days sad7
capture drop _merge
save "$outdir\post7_valid_cam_status_exclude_pre24_positive.dta", replace

use "$outdir\eligible_cohort_exclude_pre24_positive.dta", clear
capture drop _merge
merge 1:1 subject_id hadm_id stay_id using "$outdir\post7_valid_cam_status_exclude_pre24_positive.dta"
gen no_valid_cam_post7 = 0
replace no_valid_cam_post7 = 1 if _merge == 1
replace post7_valid_cam_n = 0 if missing(post7_valid_cam_n)
replace post7_valid_cam_positive_n = 0 if missing(post7_valid_cam_positive_n)
replace post7_valid_cam_negative_n = 0 if missing(post7_valid_cam_negative_n)
drop _merge
count
post `flow' ("Eligible cohort before requiring post-7d valid CAM-ICU") (r(N))
count if no_valid_cam_post7 == 1
post `flow' ("Excluded or flagged: no valid CAM-ICU within 7 days after sepsis diagnosis") (r(N))
count if no_valid_cam_post7 == 0
post `flow' ("Final cohort with valid CAM-ICU within 7 days after sepsis diagnosis") (r(N))
count if SAD_7days == 1
post `flow' ("Final outcome: SAD_7days = 1") (r(N))
count if SAD_7days == 0
post `flow' ("Final outcome: SAD_7days = 0") (r(N))
save "$outdir\sepsis_SAD_7days_with_unknown_post7_exclude_pre24_positive.dta", replace
export delimited using "$outdir\sepsis_SAD_7days_with_unknown_post7_exclude_pre24_positive.csv", replace

keep if no_valid_cam_post7 == 0
save "$outdir\sepsis_SAD_7days_final_exclude_pre24_positive.dta", replace
export delimited using "$outdir\sepsis_SAD_7days_final_exclude_pre24_positive.csv", replace

use "$outdir\cohort_flow_exclude_pre24_positive.dta", clear
export delimited using "$outdir\cohort_flow_exclude_pre24_positive.csv", replace

log close
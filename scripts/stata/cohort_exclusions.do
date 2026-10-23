clear all
set more off

global datadir "./private_inputs/cohort"

global outdir "./private_outputs/cohort"

capture log close
log using "$outdir\exclude_pregnancy_by_hadm_and_short_icu.log", replace text

tempname flow
postfile `flow' str120 step double n using "$outdir\cohort_flow_after_pregnancy_by_hadm_shorticu_exclusion.dta", replace

use "$outdir\sepsis_SAD_7days_final_exclude_pre24_positive.dta", clear

count
post `flow' ("Initial final SAD cohort") (r(N))

gen double icu_los_hours = (icu_outtime_dt - icu_intime_dt)/(1000*60*60)

gen exclude_icu_los_lt24 = 0
replace exclude_icu_los_lt24 = 1 if icu_los_hours < 24

count if exclude_icu_los_lt24 == 1
post `flow' ("Excluded: ICU LOS <24h") (r(N))

save "$outdir\temp_main_cohort.dta", replace

use "$datadir\pregnant（已保留每个hadm_id唯一）.dta", clear

keep hadm_id
duplicates drop hadm_id, force

gen pregnancy_related = 1

save "$outdir\pregnancy_hadm_unique.dta", replace

use "$outdir\temp_main_cohort.dta", clear

capture drop _merge
merge m:1 hadm_id using "$outdir\pregnancy_hadm_unique.dta"

replace pregnancy_related = 0 if missing(pregnancy_related)

gen exclude_pregnancy = 0
replace exclude_pregnancy = 1 if pregnancy_related == 1

count if exclude_pregnancy == 1
post `flow' ("Excluded: pregnancy-related admission by hadm_id") (r(N))

gen exclude_any = 0
replace exclude_any = 1 if exclude_icu_los_lt24 == 1 | exclude_pregnancy == 1

count if exclude_any == 1
post `flow' ("Excluded: pregnancy-related admission or ICU LOS <24h") (r(N))

keep if exclude_any == 0

count
post `flow' ("Final analytic cohort") (r(N))

count if SAD_7days == 1
post `flow' ("SAD_7days = 1") (r(N))

count if SAD_7days == 0
post `flow' ("SAD_7days = 0") (r(N))

tab SAD_7days

capture drop _merge

save "$outdir\sepsis_SAD_7days_final_no_pregnancy_icu24h.dta", replace

export delimited using "$outdir\sepsis_SAD_7days_final_no_pregnancy_icu24h.csv", replace

postclose `flow'

use "$outdir\cohort_flow_after_pregnancy_by_hadm_shorticu_exclusion.dta", clear

export delimited using "$outdir\cohort_flow_after_pregnancy_by_hadm_shorticu_exclusion.csv", replace

log close
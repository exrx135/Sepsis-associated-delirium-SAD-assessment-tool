clear all
set more off
cd "./private_inputs/merged"
import delimited "首次ICU人口+评分+定性+定量+SA-AKI+GV-SHR-META+非SA-AKI排除后+变量排序整理后（保留编号信息）.csv", clear
ds
local refvars `r(varlist)'
local exclude first_hba1c_hosp glucose_metabolic_states gv initial_aki_stage sa_aki_diagnosis sa_aki_time shr
local keeporder
foreach v of local refvars {
    if strpos(" `exclude' "," `v' ")==0 local keeporder `keeporder' `v'
}
import delimited "SAD with all variables.csv", clear
capture confirm variable SAD_7days
if !_rc rename SAD_7days sad_7days
capture confirm variable los_before_icu_hour
if !_rc rename los_before_icu_hour los_before_icu
local keeporder `keeporder' sad_7days
ds
local allvars `r(varlist)'
local existing_keeporder
foreach v of local keeporder {
    capture confirm variable `v'
    if !_rc local existing_keeporder `existing_keeporder' `v'
}
local deleted
foreach v of local allvars {
    if strpos(" `existing_keeporder' "," `v' ")==0 local deleted `deleted' `v'
}
display "Deleted variables: `deleted'"
keep `existing_keeporder'
order `existing_keeporder'
save "SAD_cleaned_ordered_like_SA_AKI.dta", replace
export delimited using "SAD_cleaned_ordered_like_SA_AKI.csv", replace
describe
-- SAD 从头重新提取：2026-10-20 汇总性能修正版。
-- 在 Navicat 连接 mimicv31，新建一个干净查询窗口，整份运行本文件。
-- 提取和导出必须使用同一个数据库会话；不需要填写旧 PID。
-- The original patient seed is excluded; import an authorized local seed before extraction.
-- 单条SQL超时上限30分钟；整次提取可以超过30分钟。遇到错误就停止。
-- 所有研究结果仍为临时表。完成后立即在原窗口逐表导出，再关闭连接。
-- UTF-8，无BOM。源数据只读，不创建永久研究表或进度保存表。

-- This per-attempt token prevents an old successful run from being reported as a new success.
-- Commit the token independently so rollback cannot restore a previous attempt's token,
-- including when a client sends this entire file as one simple-query message.
BEGIN;
SELECT pg_catalog.set_config('sad.current_run_token',pg_catalog.gen_random_uuid()::text,false) AS extraction_attempt;
COMMIT;
BEGIN;
SET LOCAL search_path = pg_temp, pg_catalog;
SET LOCAL statement_timeout = '30min';
DO $fresh_guard$
BEGIN
 IF EXISTS (SELECT 1 FROM pg_catalog.pg_class
            WHERE relnamespace=pg_catalog.pg_my_temp_schema()
              AND (left(relname,4)='sad_' OR relname='_sad_sedation_source_ie')) THEN
  RAISE EXCEPTION 'Use a NEW query connection for this fresh extraction; existing SAD temporary objects found. Do not rerun in a completed extraction session.';
 END IF;
END $fresh_guard$;

-- BEGIN MODULE 01_config.sql
-- All objects created by this package are TEMPORARY. Use ONE connection/session.
-- For reruns, open a NEW connection. Source tables are never updated.
-- If automatic schema detection fails, put actual schema names below.
CREATE TEMP TABLE sad_config(icu_schema text,hosp_schema text,derived_schema text);
INSERT INTO sad_config VALUES(NULL,NULL,NULL);
-- Example: UPDATE sad_config SET icu_schema='mimiciv_icu',hosp_schema='mimiciv_hosp';
CREATE TEMP TABLE sad_source_status(source_name text PRIMARY KEY,source_relation text,
 available boolean NOT NULL,detail text);
DO $sad$
DECLARE icu text; hosp text; n integer; r record; schema_name text; rel regclass;
BEGIN
 SELECT icu_schema,hosp_schema INTO icu,hosp FROM sad_config;
 IF icu IS NULL THEN
  SELECT count(*),min(a.table_schema) INTO n,icu FROM information_schema.tables a
  WHERE a.table_name='icustays' AND a.table_schema NOT LIKE 'pg_%'
   AND EXISTS(SELECT 1 FROM information_schema.tables b WHERE b.table_schema=a.table_schema AND b.table_name='inputevents')
   AND EXISTS(SELECT 1 FROM information_schema.tables b WHERE b.table_schema=a.table_schema AND b.table_name='d_items');
  IF n<>1 THEN RAISE EXCEPTION 'Found % candidate ICU schemas. Set icu_schema in 01_config.sql explicitly.',n; END IF;
 END IF;
 IF hosp IS NULL THEN
  SELECT count(*),min(a.table_schema) INTO n,hosp FROM information_schema.tables a
  WHERE a.table_name='admissions' AND a.table_schema NOT LIKE 'pg_%'
   AND EXISTS(SELECT 1 FROM information_schema.tables b WHERE b.table_schema=a.table_schema AND b.table_name='labevents')
   AND EXISTS(SELECT 1 FROM information_schema.tables b WHERE b.table_schema=a.table_schema AND b.table_name='d_labitems');
  IF n<>1 THEN RAISE EXCEPTION 'Found % candidate HOSP schemas. Set hosp_schema in 01_config.sql explicitly.',n; END IF;
 END IF;
 UPDATE sad_config SET icu_schema=icu,hosp_schema=hosp;
 FOR r IN SELECT * FROM (VALUES
  ('icu','d_items',true,''),('icu','inputevents',true,''),('icu','chartevents',true,''),
  ('icu','icustays',true,''),('icu','outputevents',true,''),('icu','procedureevents',true,''),
  ('hosp','admissions',true,''),('hosp','patients',true,''),('hosp','labevents',true,''),('hosp','d_labitems',true,''),
  ('hosp','diagnoses_icd',false,'subject_id bigint,hadm_id bigint,seq_num integer,icd_code text,icd_version integer'),
  ('hosp','services',false,'subject_id bigint,hadm_id bigint,transfertime timestamp,prev_service text,curr_service text'),
  ('hosp','emar',false,'subject_id bigint,hadm_id bigint,emar_id text,emar_seq integer,charttime timestamp,storetime timestamp,medication text,event_txt text,pharmacy_id bigint,scheduletime timestamp'),
  ('hosp','emar_detail',false,'subject_id bigint,emar_id text,emar_seq integer,parent_field_ordinal double precision,administration_type text,dose_given text,dose_given_unit text,route text,infusion_rate text,infusion_rate_unit text,infusion_complete text,completion_interval text,new_iv_bag_hung text,product_amount_given text,product_unit text'),
  ('hosp','prescriptions',false,'subject_id bigint,hadm_id bigint,pharmacy_id bigint,starttime timestamp,stoptime timestamp,drug text,drug_type text,route text,dose_val_rx text,dose_unit_rx text,form_val_disp text,form_unit_disp text')
 ) AS x(module,table_name,required,empty_columns)
 LOOP
  schema_name=CASE WHEN r.module='icu' THEN icu ELSE hosp END;
  rel=to_regclass(format('%I.%I',schema_name,r.table_name));
  IF rel IS NULL THEN
   IF r.required THEN RAISE EXCEPTION 'Required source missing: %.%',schema_name,r.table_name; END IF;
   EXECUTE format('CREATE TEMP TABLE %I (%s)','sad_src_'||r.table_name,r.empty_columns);
   INSERT INTO sad_source_status VALUES(r.table_name,format('%I.%I',schema_name,r.table_name),false,'Optional source absent; empty adapter, absence is UNKNOWN, not negative exposure');
  ELSE
   EXECUTE format('CREATE TEMP VIEW %I AS SELECT * FROM %s','sad_src_'||r.table_name,rel);
   INSERT INTO sad_source_status VALUES(r.table_name,rel::text,true,'Source exists; row-level completeness must still be audited');
  END IF;
 END LOOP;
END $sad$;
SELECT * FROM sad_config;
SELECT * FROM sad_source_status ORDER BY source_name;
-- END MODULE 01_config.sql

-- BEGIN MODULE 02_cohort_seed.sql
-- PostgreSQL seed schema; the authorized patient-level seed CSV must be supplied locally.
-- No patient keys, times or seed values are included in this source package.
-- Broad 41,295-stay sepsis seed: no exclusion based on future CAM, ICU survival or future treatment.
-- Apply baseline adult/first-stay/prevalent-delirium/indication eligibility only in analysis.
-- in_manuscript identifies the original 17,851-row prediction cohort.
CREATE TEMP TABLE sad_seed (
 stay_id bigint PRIMARY KEY, subject_id bigint NOT NULL, hadm_id bigint NOT NULL,
 t0 timestamp NOT NULL, icu_intime timestamp NOT NULL, icu_outtime timestamp NOT NULL,
 admittime timestamp, dischtime timestamp, deathtime timestamp,
 admission_age double precision, in_manuscript boolean NOT NULL,
 pregnancy_recorded boolean NOT NULL, legacy_sad_7days smallint,
 legacy_first_positive_time timestamp, legacy_pre24_valid_n integer,
 legacy_post7_valid_n integer, legacy_no_valid_post7 boolean,
 legacy_baseline_eligible boolean,first_hosp_stay boolean,first_icu_stay boolean
);
-- Patient-level seed rows are deliberately excluded from this source release.
-- Before running this script, configure the database-server-local authorized CSV:
-- SET sad.seed_csv = '/absolute/local/path/cohort_seed.csv';
DO $seed_import$
DECLARE source_file text := current_setting('sad.seed_csv', true);
BEGIN
 IF source_file IS NULL OR source_file = '' THEN
  RAISE EXCEPTION 'Set sad.seed_csv to an authorized local cohort seed CSV; no seed data are distributed.';
 END IF;
 EXECUTE format('COPY sad_seed FROM %L WITH (FORMAT CSV, HEADER TRUE)', source_file);
END $seed_import$;
CREATE TEMP TABLE sad_cohort AS
SELECT s.*, LEAST(t0+INTERVAL '7 days',icu_outtime,dischtime,deathtime) AS followup_end,
       GREATEST(t0,icu_intime) AS icu_observation_start,
       EXTRACT(EPOCH FROM(t0-icu_intime))/3600.0 AS hours_icu_to_t0,
       (t0<icu_intime) AS t0_before_icu,
       (COALESCE(icu_outtime<t0,false) OR COALESCE(deathtime<t0,false) OR COALESCE(dischtime<t0,false)) AS invalid_temporal_order,
       (icu_intime>t0-INTERVAL '24 hours') AS incomplete_pre24_icu_observation
FROM sad_seed s;
CREATE UNIQUE INDEX ON sad_cohort(stay_id);
CREATE INDEX ON sad_cohort(hadm_id);
CREATE INDEX ON sad_cohort(subject_id);
ANALYZE sad_cohort;
SELECT 'cohort_loaded' AS audit, count(*) AS n, count(*) FILTER(WHERE in_manuscript) AS manuscript_n,
 count(*) FILTER(WHERE legacy_sad_7days=1 AND in_manuscript) AS manuscript_events,
 count(*) FILTER(WHERE legacy_sad_7days IS NULL) AS unknown_legacy_outcome,
 count(*) FILTER(WHERE invalid_temporal_order) AS invalid_temporal_order_n
FROM sad_cohort;
-- END MODULE 02_cohort_seed.sql

-- BEGIN MODULE 03_cohort_database_check.sql
-- Prevent extracting against a wrong MIMIC version/database.
CREATE TEMP TABLE sad_cohort_database_audit AS
SELECT c.stay_id,c.in_manuscript,c.t0,c.icu_intime AS seed_intime,c.icu_outtime AS seed_outtime,
 i.intime AS database_intime,i.outtime AS database_outtime,
 (i.stay_id IS NOT NULL) AS found_in_database,
 (i.subject_id=c.subject_id AND i.hadm_id=c.hadm_id) AS ids_match,
 (i.intime=c.icu_intime AND i.outtime=c.icu_outtime) AS icu_times_match,
 (a.hadm_id IS NOT NULL) AS admission_found_in_database,
 a.deathtime AS database_deathtime,a.dischtime AS database_dischtime,
 (a.deathtime IS NOT DISTINCT FROM c.deathtime) AS death_time_matches,
 (a.dischtime IS NOT DISTINCT FROM c.dischtime) AS discharge_time_matches
FROM sad_cohort c LEFT JOIN sad_src_icustays i USING(stay_id)
LEFT JOIN sad_src_admissions a ON a.hadm_id=c.hadm_id;
SELECT count(*) AS n,count(*) FILTER(WHERE found_in_database) AS matched,
 count(*) FILTER(WHERE NOT ids_match) AS id_mismatch,
 count(*) FILTER(WHERE NOT icu_times_match) AS time_mismatch,
 count(*) FILTER(WHERE NOT admission_found_in_database) AS missing_admission,
 count(*) FILTER(WHERE NOT death_time_matches) AS death_time_mismatch,
 count(*) FILTER(WHERE NOT discharge_time_matches) AS discharge_time_mismatch
FROM sad_cohort_database_audit;
DO $sad$
BEGIN
 IF EXISTS(SELECT 1 FROM sad_cohort_database_audit WHERE NOT found_in_database OR ids_match IS NOT TRUE OR icu_times_match IS NOT TRUE
  OR NOT admission_found_in_database OR NOT death_time_matches OR NOT discharge_time_matches) THEN
  RAISE EXCEPTION 'Cohort IDs, ICU times, death or discharge times do not match the database. Inspect sad_cohort_database_audit before continuing; do not silently change t0 or follow-up boundaries.';
 END IF;
END $sad$;
-- END MODULE 03_cohort_database_check.sql

-- BEGIN MODULE 10_chart_labs_context.sql
-- Event-level measurements for confounding control, eligibility, CAM/RASS and respiratory support.
-- Clinical charttime and documentation/result-availability storetime are both retained.
-- Source definitions: https://mimic.mit.edu/docs/iv/modules/icu/chartevents.html
-- https://mimic.mit.edu/docs/iv/modules/hosp/labevents.html
CREATE TEMP TABLE sad_chart_dictionary AS
SELECT d.* FROM sad_src_d_items d
WHERE lower(d.linksto)='chartevents' AND (
 d.itemid IN (228096,228300,228301,228302,228303,228337,228336,228334,228335,229326,229325,229324)
 OR d.label ~* 'heart rate|blood pressure|arterial.*pressure|respiratory rate|respiratory pattern|respiratory effort|oxygen|o2 saturation|spo2|inspired.*o2|fio2|peep|ventilator|plateau|driving pressure|tidal volume|minute volume|flow rate|temperature|weight|glasgow|gcs|richmond|rass|sedation|CAM-ICU|delirium|code status|comfort|pain|CPOT|Riker|intub|airway|endotracheal|activity|mobility|sleep|orientation|restraint|cough|gag|fluid respons|capillary|mottling|withdrawal|CIWA|COWS|seizure|epilep|neuro|pupil|rhythm|arrhythmi|heart block|AV block|QTc|QT interval');
CREATE UNIQUE INDEX ON sad_chart_dictionary(itemid);
CREATE TEMP TABLE sad_chart_events AS
SELECT c.stay_id,c.subject_id,c.hadm_id,c.t0,
 e.itemid,d.label,d.category,e.charttime,e.storetime,e.value,e.valuenum,e.valueuom,
 EXTRACT(EPOCH FROM(e.charttime-c.t0))/3600.0 AS hours_from_t0,
 (e.charttime<c.t0) AS measured_before_t0,
 (e.charttime<c.t0 AND e.storetime<=c.t0) AS documented_before_t0,
 (e.storetime IS NULL) AS availability_time_unknown,
 (e.charttime>c.followup_end) AS after_icu_death_or_discharge,
 to_jsonb(e)->>'warning' AS source_warning
FROM sad_cohort c JOIN sad_src_chartevents e ON e.stay_id=c.stay_id
 -- Extra hour on both sides permits nearest RASS matching at the CAM window boundaries.
 AND (e.charttime>=c.t0-INTERVAL '25 hours'
 OR (e.charttime>=c.icu_intime AND e.itemid IN (228096,228300,228301,228302,228303,228337,228336,228334,228335,229326,229325,229324)))
 AND e.charttime<=c.t0+INTERVAL '7 days 1 hour'
JOIN sad_chart_dictionary d ON d.itemid=e.itemid;
CREATE INDEX ON sad_chart_events(stay_id,charttime);
CREATE INDEX ON sad_chart_events(itemid);
ANALYZE sad_chart_events;
CREATE TEMP TABLE sad_chart_coverage AS
SELECT d.itemid,d.label,count(e.stay_id) AS records,count(DISTINCT e.stay_id) AS patients,
 count(*) FILTER(WHERE e.charttime<e.t0) AS pre_t0_records,
 count(*) FILTER(WHERE e.charttime<e.t0 AND e.storetime>e.t0) AS pre_t0_late_documented,
 count(*) FILTER(WHERE e.storetime IS NULL AND e.stay_id IS NOT NULL) AS storetime_missing
FROM sad_chart_dictionary d LEFT JOIN sad_chart_events e USING(itemid)
GROUP BY d.itemid,d.label;

CREATE TEMP TABLE sad_lab_dictionary AS
SELECT d.* FROM sad_src_d_labitems d
WHERE d.label ~* 'lactate|lactic|^pH$|pco2|po2|oxygen|bicarbonate|base excess|carbon dioxide|creatinine|urea|BUN|bilirubin|platelet|white blood|wbc|hemoglobin|hematocrit|RDW|red.*distribution|sodium|potassium|chloride|calcium|magnesium|phosphate|glucose|albumin|PTT|prothrombin|^PT$|^INR|alanine|aspartate|ALT|AST|troponin|procalcitonin|C-reactive|specimen type';
CREATE UNIQUE INDEX ON sad_lab_dictionary(itemid);
-- hadm_id-null labs are recovered ONLY within the matching admission interval.
-- Exact hadm_id rows may include pre-admission labs already attributed by MIMIC.
CREATE TEMP TABLE sad_lab_events AS
SELECT c.stay_id,c.subject_id,c.hadm_id AS cohort_hadm_id,c.t0,
 e.labevent_id,e.hadm_id AS source_hadm_id,e.specimen_id,e.itemid,d.label,d.fluid,d.category,
 e.charttime,e.storetime,e.value,e.valuenum,e.valueuom,
 EXTRACT(EPOCH FROM(e.charttime-c.t0))/3600.0 AS hours_from_t0,
 CASE WHEN e.hadm_id=c.hadm_id THEN 'hadm_id' ELSE 'subject_id_and_admission_time' END AS join_method,
 (e.charttime<c.t0) AS sampled_before_t0,
 (e.charttime<c.t0 AND e.storetime<=c.t0) AS result_available_before_t0,
 (e.storetime IS NULL) AS availability_time_unknown,
 (e.charttime>c.followup_end) AS after_icu_death_or_discharge
FROM sad_cohort c JOIN sad_src_labevents e ON e.subject_id=c.subject_id
 AND (e.hadm_id=c.hadm_id OR (e.hadm_id IS NULL AND e.charttime>=c.admittime AND e.charttime<=c.dischtime))
 AND e.charttime>=c.t0-INTERVAL '24 hours' AND e.charttime<=c.t0+INTERVAL '7 days'
JOIN sad_lab_dictionary d ON d.itemid=e.itemid;
CREATE INDEX ON sad_lab_events(stay_id,charttime);
CREATE INDEX ON sad_lab_events(specimen_id);
ANALYZE sad_lab_events;
CREATE TEMP TABLE sad_lab_coverage AS
SELECT d.itemid,d.label,d.fluid,count(e.stay_id) AS records,count(DISTINCT e.stay_id) AS patients,
 count(*) FILTER(WHERE e.charttime<e.t0 AND e.storetime>e.t0) AS pre_t0_sample_result_after_t0
FROM sad_lab_dictionary d LEFT JOIN sad_lab_events e USING(itemid)
GROUP BY d.itemid,d.label,d.fluid;

CREATE TEMP TABLE sad_urine_events AS
SELECT c.stay_id,c.t0,e.charttime,e.storetime,e.itemid,d.label,e.value,e.valueuom,
 EXTRACT(EPOCH FROM(e.charttime-c.t0))/3600.0 AS hours_from_t0,
 (e.charttime>c.followup_end) AS after_icu_death_or_discharge,
 (d.label ~* 'irrigant|irrigation') AS irrigation_item_requires_balance
FROM sad_cohort c JOIN sad_src_outputevents e ON e.stay_id=c.stay_id
 AND e.charttime>=c.t0-INTERVAL '24 hours' AND e.charttime<=c.t0+INTERVAL '7 days'
JOIN sad_src_d_items d USING(itemid)
WHERE d.label ~* 'urine|foley|void|nephrostom|ureter|condom cath|straight cath|suprapubic|irrigant';
-- Do not sum irrigation returned as urine; preserve its paired input/output separately.
CREATE INDEX ON sad_urine_events(stay_id,charttime);

CREATE TEMP TABLE sad_admission_context AS
SELECT c.*,a.admission_type,a.admission_location,a.discharge_location,
 p.gender,p.anchor_age,p.anchor_year,p.anchor_year_group,p.dod,
 a.deathtime AS hospital_recorded_deathtime,a.hospital_expire_flag
FROM sad_cohort c JOIN sad_src_admissions a ON a.hadm_id=c.hadm_id
JOIN sad_src_patients p ON p.subject_id=c.subject_id;
CREATE TEMP TABLE sad_diagnosis_context AS
SELECT c.stay_id,c.t0,d.seq_num,d.icd_code,d.icd_version,
 'Discharge-coded diagnosis: timing/presence before t0 NOT established'::text AS temporal_caution
FROM sad_cohort c JOIN sad_src_diagnoses_icd d ON d.hadm_id=c.hadm_id;
CREATE TEMP TABLE sad_service_events AS
SELECT c.stay_id,c.t0,s.transfertime,s.prev_service,s.curr_service,
 (s.transfertime<=c.t0) AS recorded_service_before_or_at_t0
FROM sad_cohort c JOIN sad_src_services s ON s.hadm_id=c.hadm_id;
SELECT 'chart_events' AS dataset,count(*) AS rows FROM sad_chart_events
UNION ALL SELECT 'lab_events',count(*) FROM sad_lab_events
UNION ALL SELECT 'urine_events',count(*) FROM sad_urine_events;
-- END MODULE 10_chart_labs_context.sql

-- BEGIN MODULE 20_ventilation.sql
-- Sources: procedureevents documentation warns that absence is NOT evidence of no procedure.
-- https://mimic.mit.edu/docs/iv/modules/icu/procedureevents.html
-- Capture direct procedure intervals + respiratory chart evidence; do not equate PEEP or FiO2 with invasive ventilation.
CREATE TEMP TABLE sad_ventilation_dictionary AS
SELECT d.* FROM sad_src_d_items d WHERE lower(d.linksto)='procedureevents'
 AND d.label ~* 'ventilat|intubat|extubat|tracheost|ECMO|extracorporeal';
CREATE TEMP TABLE sad_ventilation_events AS
SELECT c.stay_id,c.subject_id,c.hadm_id,c.t0,e.itemid,d.label,e.starttime,e.endtime,e.storetime,
 e.value,e.valueuom,e.orderid,e.linkorderid,e.statusdescription,
 CASE WHEN lower(trim(d.label))='invasive ventilation' THEN 'invasive_ventilation_interval'
 WHEN d.label ~* 'non.?invasive.*ventilat' THEN 'noninvasive_ventilation_interval'
 WHEN lower(trim(d.label))='intubation' THEN 'intubation_event'
 WHEN d.label ~* 'extubat' THEN 'extubation_event'
 WHEN d.label ~* 'tracheost' THEN 'tracheostomy_event'
 ELSE 'other_respiratory_procedure' END AS procedure_group,
 (e.starttime<=c.t0 AND e.endtime>c.t0) AS crosses_t0,
 (e.starttime>c.t0) AS recorded_start_after_t0,
 EXTRACT(EPOCH FROM(e.starttime-c.t0))/3600.0 AS start_hours_from_t0,
 (e.endtime<e.starttime) AS reversed_interval,
 (e.starttime>c.followup_end) AS after_icu_death_or_discharge
FROM sad_cohort c JOIN sad_src_procedureevents e ON e.stay_id=c.stay_id
 AND e.starttime<=c.t0+INTERVAL '7 days'
 AND COALESCE(e.endtime,e.starttime)>=c.t0-INTERVAL '24 hours'
JOIN sad_ventilation_dictionary d USING(itemid);
CREATE INDEX ON sad_ventilation_events(stay_id,starttime,endtime);
-- FRESH_PERF_BEGIN
ANALYZE sad_ventilation_events;
-- FRESH_PERF_END
CREATE TEMP TABLE sad_ventilation_summary AS
SELECT c.stay_id,
 count(e.stay_id) AS respiratory_procedure_records,
 CASE WHEN bool_or(e.procedure_group='invasive_ventilation_interval' AND e.crosses_t0 AND NOT e.reversed_interval AND lower(coalesce(e.statusdescription,''))<>'rewritten' AND c.t0<=c.followup_end)
 THEN true ELSE NULL::boolean END AS documented_invasive_ventilation_at_t0,
 min(e.starttime) FILTER(WHERE e.procedure_group='intubation_event' AND e.starttime>=c.t0 AND e.starttime<=c.followup_end AND (e.endtime IS NULL OR NOT e.reversed_interval) AND lower(coalesce(e.statusdescription,''))<>'rewritten') AS first_post_t0_intubation_record,
 min(e.starttime) FILTER(WHERE e.procedure_group='invasive_ventilation_interval' AND e.starttime>=c.t0 AND e.starttime<=c.followup_end AND NOT e.reversed_interval AND lower(coalesce(e.statusdescription,''))<>'rewritten') AS first_post_t0_invasive_interval_start,
 count(e.stay_id) FILTER(WHERE e.reversed_interval) AS reversed_interval_records,
 'No recorded invasive interval is UNKNOWN until reconciled with airway/ventilator charts; not an unventilated control'::text AS absence_interpretation
FROM sad_cohort c LEFT JOIN sad_ventilation_events e USING(stay_id) GROUP BY c.stay_id;
-- Optional official derived ventilation, if already installed. No reconstruction by guessed device codes.
CREATE TEMP TABLE sad_derived_ventilation_events(stay_id bigint,starttime timestamp,endtime timestamp,ventilation_status text,source_relation text);
DO $sad$
DECLARE s text; n integer; q text;
BEGIN
 SELECT derived_schema INTO s FROM sad_config;
 IF s IS NULL THEN
  SELECT count(*),min(table_schema) INTO n,s FROM information_schema.tables
  WHERE table_name='ventilation' AND table_schema NOT LIKE 'pg_%'
   AND table_schema NOT IN('information_schema');
  IF n<>1 THEN s=NULL; END IF;
 END IF;
 IF s IS NOT NULL AND to_regclass(format('%I.ventilation',s)) IS NOT NULL THEN
  q=format('INSERT INTO sad_derived_ventilation_events SELECT v.stay_id,v.starttime,v.endtime,v.ventilation_status,%L FROM %I.ventilation v JOIN sad_cohort c ON c.stay_id=v.stay_id WHERE v.starttime<=c.t0+INTERVAL ''7 days'' AND COALESCE(v.endtime,v.starttime)>=c.t0-INTERVAL ''24 hours''',s||'.ventilation',s);
  EXECUTE q;
  INSERT INTO sad_source_status VALUES('derived_ventilation',s||'.ventilation',true,'Version of the derived concept must be recorded by the user');
 ELSE
  INSERT INTO sad_source_status VALUES('derived_ventilation',NULL,false,'Optional concept absent or ambiguous; use raw procedure and respiratory chart extraction');
 END IF;
END $sad$;
-- END MODULE 20_ventilation.sql

-- BEGIN MODULE 25_cam_rass_outcomes.sql
-- Item mapping is preserved from the user's script1-SAD definition.txt.
-- IMPORTANT: legacy Stata initialized absent CAM components to zero.
-- This module exports STRICT three-state assessments separately; it never silently overwrites manuscript labels.
-- Raw values/item labels, conflicting forms and nearest RASS are retained for adjudication.
CREATE TEMP TABLE sad_cam_item_map(itemid integer PRIMARY KEY,form_name text,feature integer);
INSERT INTO sad_cam_item_map VALUES
 (228300,'core',1),(228301,'core',2),(228302,'core',3),(228303,'core',4),
 (228337,'backup',1),(228336,'backup',2),(228334,'backup',3),(228335,'backup',4),
 (229326,'oldsys',1),(229325,'oldsys',2),(229324,'oldsys',4);
CREATE TEMP TABLE sad_cam_dictionary_audit AS
SELECT m.*,d.label,d.linksto,(d.itemid IS NOT NULL) AS item_found,
 (d.label ~* 'CAM|delirium|mental|inattention|conscious|thinking') AS label_plausible
FROM sad_cam_item_map m LEFT JOIN sad_src_d_items d USING(itemid);
CREATE TEMP TABLE sad_cam_raw AS
SELECT e.*,m.form_name,m.feature,
 CASE WHEN trim(e.value) ~* '^yes([ (]|$)' THEN 1
      WHEN trim(e.value) ~* '^no([ (]|$)' THEN 0 ELSE NULL END AS explicit_component_result
FROM sad_chart_events e JOIN sad_cam_item_map m USING(itemid)
WHERE e.charttime<=e.t0+INTERVAL '7 days';
CREATE TEMP TABLE sad_cam_value_audit AS
SELECT itemid,label,form_name,feature,value,explicit_component_result,count(*) AS n
FROM sad_cam_raw GROUP BY itemid,label,form_name,feature,value,explicit_component_result;
CREATE TEMP TABLE sad_cam_components AS
SELECT stay_id,t0,charttime,form_name,feature,count(*) AS source_rows,
 min(storetime) AS first_component_storetime,max(storetime) AS last_component_storetime,
 count(*) FILTER(WHERE storetime IS NULL) AS missing_component_storetime_n,
 count(DISTINCT explicit_component_result) AS distinct_explicit_results,
 CASE WHEN count(DISTINCT explicit_component_result)=1 THEN max(explicit_component_result) ELSE NULL END AS component_result,
 bool_or(explicit_component_result IS NULL) AS has_uninterpreted_value
FROM sad_cam_raw GROUP BY stay_id,t0,charttime,form_name,feature;
CREATE TEMP TABLE sad_cam_forms AS
WITH p AS(
 SELECT stay_id,t0,charttime,form_name,
 max(component_result) FILTER(WHERE feature=1) AS f1,
 max(component_result) FILTER(WHERE feature=2) AS f2,
 max(component_result) FILTER(WHERE feature=3) AS f3,
 max(component_result) FILTER(WHERE feature=4) AS f4,
 bool_or(distinct_explicit_results>1) AS component_conflict,
 min(first_component_storetime) AS first_form_storetime,max(last_component_storetime) AS last_form_storetime,
 sum(missing_component_storetime_n) AS missing_form_storetime_n,
 sum(source_rows) AS source_rows
 FROM sad_cam_components GROUP BY stay_id,t0,charttime,form_name
)
SELECT p.*,
 CASE WHEN component_conflict THEN NULL
      WHEN form_name='oldsys' AND f1=1 AND f2=1 AND f4=1 THEN 1
      -- Oldsys lacks the alternative altered-consciousness component. f4=0 alone cannot prove negative.
      WHEN form_name='oldsys' AND (f1=0 OR f2=0) THEN 0
      WHEN form_name<>'oldsys' AND f1=1 AND f2=1 AND (f3=1 OR f4=1) THEN 1
      WHEN form_name<>'oldsys' AND (f1=0 OR f2=0 OR (f3=0 AND f4=0)) THEN 0
      ELSE NULL END AS cam_result_strict,
 -- Approximate legacy form logic only: original same-time cross-form dedup order is not recreated here.
 CASE WHEN coalesce(f1,0)=1 AND coalesce(f2,0)=1
  AND (coalesce(f4,0)=1 OR (form_name<>'oldsys' AND coalesce(f3,0)=1)) THEN 1 ELSE 0 END AS legacy_zero_filled_form_result
FROM p;
CREATE TEMP TABLE sad_cam_timepoints AS
SELECT stay_id,t0,charttime,count(*) AS forms_at_time,
 min(first_form_storetime) AS first_cam_storetime,max(last_form_storetime) AS last_cam_storetime,
 sum(missing_form_storetime_n) AS missing_cam_storetime_n,
 count(DISTINCT cam_result_strict)>1 AS forms_disagree,
 bool_or(component_conflict) AS any_component_conflict,
 CASE WHEN count(DISTINCT cam_result_strict)>1 OR bool_or(component_conflict) THEN NULL
 ELSE max(cam_result_strict) END AS cam_result_strict,
 bool_or(cam_result_strict IS NULL) AS any_form_incomplete
FROM sad_cam_forms GROUP BY stay_id,t0,charttime;
CREATE TEMP TABLE sad_rass_events AS
SELECT e.*,(valuenum BETWEEN -5 AND 4 AND valuenum=trunc(valuenum)) AS valid_rass_range
FROM sad_chart_events e WHERE e.itemid=228096;
CREATE INDEX ON sad_rass_events(stay_id,charttime);
-- FRESH_PERF_BEGIN
ANALYZE sad_rass_events;
-- FRESH_PERF_END
CREATE TEMP TABLE sad_rass_timepoints AS
SELECT stay_id,charttime,
 min(storetime) FILTER(WHERE valid_rass_range) AS first_rass_storetime,
 max(storetime) FILTER(WHERE valid_rass_range) AS last_rass_storetime,
 count(*) FILTER(WHERE valid_rass_range AND storetime IS NULL) AS missing_rass_storetime_n,
 count(DISTINCT valuenum) FILTER(WHERE valid_rass_range)>1 AS conflicting_rass,
 CASE WHEN count(DISTINCT valuenum) FILTER(WHERE valid_rass_range)=1
 THEN max(valuenum) FILTER(WHERE valid_rass_range) ELSE NULL END AS valuenum
FROM sad_rass_events GROUP BY stay_id,charttime
HAVING count(*) FILTER(WHERE valid_rass_range)>0;
CREATE INDEX ON sad_rass_timepoints(stay_id,charttime);
-- FRESH_PERF_BEGIN
ANALYZE sad_rass_timepoints;
-- FRESH_PERF_END
CREATE TEMP TABLE sad_cam_assessments AS
SELECT a.*,r.charttime AS nearest_rass_time,r.valuenum AS nearest_rass,
 r.first_rass_storetime,r.last_rass_storetime,r.missing_rass_storetime_n,
 (a.charttime<c.t0 AND r.charttime>c.t0) AS precam_matched_post_t0_rass,
 CASE WHEN a.charttime>c.t0 OR a.last_cam_storetime>c.t0 THEN false
      WHEN a.missing_cam_storetime_n>0 THEN NULL ELSE true END AS cam_components_available_by_t0,
 CASE WHEN r.charttime IS NULL THEN NULL
      WHEN r.charttime>c.t0 OR r.last_rass_storetime>c.t0 THEN false
      WHEN r.missing_rass_storetime_n>0 THEN NULL ELSE true END AS rass_documented_by_t0,
 -- Conservative availability of ALL source rows used in the final adjudication.
 -- A false/NULL flag does not invalidate a retrospective outcome assessment.
 CASE WHEN r.charttime IS NULL THEN NULL
      WHEN a.charttime>c.t0 OR r.charttime>c.t0
        OR a.last_cam_storetime>c.t0 OR r.last_rass_storetime>c.t0 THEN false
      WHEN a.missing_cam_storetime_n>0 OR r.missing_rass_storetime_n>0 THEN NULL
      ELSE true END AS paired_documentation_available_by_t0,
 abs(EXTRACT(EPOCH FROM(r.charttime-a.charttime)))/60.0 AS rass_gap_minutes,
 CASE WHEN a.charttime>=c.icu_intime AND a.charttime<=LEAST(c.icu_outtime,c.dischtime,c.deathtime)
 AND r.valuenum>=-3 AND a.cam_result_strict IS NOT NULL THEN true ELSE false END AS assessable_strict,
 CASE WHEN a.charttime>=c.icu_intime AND a.charttime<=LEAST(c.icu_outtime,c.dischtime,c.deathtime)
 AND r.valuenum>=-3 THEN a.cam_result_strict ELSE NULL END AS valid_cam_result,
 CASE WHEN a.charttime<c.icu_intime OR a.charttime>LEAST(c.icu_outtime,c.dischtime,c.deathtime) THEN 'outside_observed_icu_interval'
 WHEN r.charttime IS NULL THEN 'no_valid_rass_within_1h'
 WHEN r.conflicting_rass THEN 'conflicting_rass_at_nearest_time'
 WHEN r.valuenum < -3 THEN 'deep_sedation_or_coma'
 WHEN a.forms_disagree OR a.any_component_conflict THEN 'conflicting_cam'
 WHEN a.cam_result_strict IS NULL THEN 'incomplete_or_uninterpreted_cam'
 ELSE 'assessable' END AS assessment_status
FROM sad_cam_timepoints a JOIN sad_cohort c USING(stay_id)
LEFT JOIN LATERAL (
 SELECT r.charttime,r.valuenum,r.conflicting_rass,r.first_rass_storetime,r.last_rass_storetime,
        r.missing_rass_storetime_n FROM sad_rass_timepoints r
 WHERE r.stay_id=a.stay_id
 AND r.charttime>=c.icu_intime AND r.charttime<=LEAST(c.icu_outtime,c.dischtime,c.deathtime)
 AND r.charttime BETWEEN a.charttime-INTERVAL '1 hour' AND a.charttime+INTERVAL '1 hour'
 ORDER BY abs(EXTRACT(EPOCH FROM(r.charttime-a.charttime))),r.charttime,r.valuenum LIMIT 1
) r ON true;
CREATE INDEX ON sad_cam_assessments(stay_id,charttime);
-- FRESH_PERF_BEGIN
ANALYZE sad_cam_assessments;
-- FRESH_PERF_END
CREATE TEMP TABLE sad_outcome_summary AS
SELECT c.stay_id,c.t0,c.followup_end,c.legacy_sad_7days,c.legacy_first_positive_time,
 greatest(c.t0,c.icu_intime) AS observed_followup_start,
 greatest(0,EXTRACT(EPOCH FROM(c.followup_end-greatest(c.t0,c.icu_intime)))/3600.0) AS observed_followup_hours,
 (c.icu_intime<=c.t0 AND c.followup_end>=c.t0+INTERVAL '7 days') AS complete_administrative_7d_observation,
 CASE WHEN c.followup_end<=greatest(c.t0,c.icu_intime) THEN 'no_post_t0_icu_observation'
      WHEN c.followup_end=c.deathtime THEN 'death'
      WHEN c.followup_end>=c.t0+INTERVAL '7 days' THEN 'seven_day_horizon'
      WHEN c.followup_end=c.dischtime THEN 'hospital_discharge'
      WHEN c.followup_end=c.icu_outtime THEN 'icu_discharge'
      ELSE 'other_or_unknown_end' END AS followup_end_reason,
 COALESCE(c.followup_end=c.deathtime,false) AS followup_ended_at_death,
 COALESCE(c.followup_end=c.dischtime,false) AS followup_ended_at_hospital_discharge,
 COALESCE(c.followup_end=c.icu_outtime,false) AS followup_ended_at_icu_discharge,
 count(a.stay_id) FILTER(WHERE a.charttime>=c.t0-INTERVAL '24 hours' AND a.charttime<c.t0 AND a.valid_cam_result IS NOT NULL) AS strict_pre24_valid_n,
 count(a.stay_id) FILTER(WHERE a.charttime>=c.t0-INTERVAL '24 hours' AND a.charttime<c.t0 AND a.valid_cam_result=1) AS strict_pre24_positive_n,
 count(a.stay_id) FILTER(WHERE a.charttime>=c.t0-INTERVAL '24 hours' AND a.charttime<c.t0
   AND a.valid_cam_result IS NOT NULL AND a.paired_documentation_available_by_t0) AS strict_pre24_valid_available_by_t0_n,
 count(a.stay_id) FILTER(WHERE a.charttime>=c.t0-INTERVAL '24 hours' AND a.charttime<c.t0
   AND a.precam_matched_post_t0_rass) AS pre24_cam_matched_post_t0_rass_n,
 CASE WHEN bool_or(a.charttime>=c.t0-INTERVAL '24 hours' AND a.charttime<c.t0 AND a.valid_cam_result=1)
       THEN 'observed_pre24_positive'
      WHEN bool_or(a.charttime>=c.t0-INTERVAL '24 hours' AND a.charttime<c.t0 AND a.valid_cam_result=0)
       THEN 'observed_pre24_negative_only'
      ELSE 'unknown_no_valid_pre24_assessment' END AS strict_pre24_assessment_state,
 count(a.stay_id) FILTER(WHERE a.charttime<c.t0 AND a.valid_cam_result=1) AS any_prior_icu_positive_n,
 min(a.charttime) FILTER(WHERE a.charttime<c.t0 AND a.valid_cam_result=1) AS first_prior_icu_positive_time,
 count(a.stay_id) FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end AND a.valid_cam_result IS NOT NULL) AS strict_post7_valid_n,
 count(a.stay_id) FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end AND a.valid_cam_result=1) AS strict_post7_positive_n,
 min(a.charttime) FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end AND a.valid_cam_result=1) AS strict_first_positive_time,
 max(a.charttime) FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end AND a.valid_cam_result IS NOT NULL) AS last_valid_cam_time,
 max(a.charttime) FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end) AS last_any_cam_time,
 (array_agg(a.valid_cam_result ORDER BY a.charttime DESC)
   FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end AND a.valid_cam_result IS NOT NULL))[1] AS last_valid_cam_result,
 EXTRACT(EPOCH FROM(c.followup_end-max(a.charttime)
   FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end AND a.valid_cam_result IS NOT NULL)))/3600.0 AS hours_last_valid_cam_to_followup_end,
 CASE WHEN bool_or(a.valid_cam_result=1 AND a.charttime>=c.t0 AND a.charttime<=c.followup_end) THEN 'observed_positive'
      WHEN bool_or(a.valid_cam_result=0 AND a.charttime>=c.t0 AND a.charttime<=c.followup_end) THEN 'observed_negative_only'
      WHEN count(a.stay_id) FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end)>0 THEN 'only_unassessable_or_incomplete_cam'
      ELSE 'no_cam_assessment' END AS post7_assessment_state,
 CASE WHEN bool_or(a.valid_cam_result=1 AND a.charttime>=c.t0 AND a.charttime<=c.followup_end) THEN 1
 WHEN bool_or(a.valid_cam_result=0 AND a.charttime>=c.t0 AND a.charttime<=c.followup_end) THEN 0 ELSE NULL END AS strict_observed_sad_7days,
 count(a.stay_id) FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end AND a.assessment_status='deep_sedation_or_coma') AS deep_sedation_cam_n,
 count(a.stay_id) FILTER(WHERE a.charttime>=c.t0 AND a.charttime<=c.followup_end AND a.assessment_status='no_valid_rass_within_1h') AS missing_rass_cam_n,
 (c.deathtime>=c.t0 AND c.deathtime<=c.t0+INTERVAL '7 days') AS recorded_death_within_7d,
 c.deathtime,c.icu_outtime,c.dischtime,
 'Observed negative assessments do not prove continuous absence of delirium; coma/death/no assessment are distinct states'::text AS outcome_note
FROM sad_cohort c LEFT JOIN sad_cam_assessments a USING(stay_id)
GROUP BY c.stay_id,c.t0,c.icu_intime,c.followup_end,c.legacy_sad_7days,c.legacy_first_positive_time,c.deathtime,c.icu_outtime,c.dischtime;
-- FRESH_PERF_BEGIN
ANALYZE sad_outcome_summary;
-- FRESH_PERF_END
CREATE TEMP TABLE sad_outcome_daily AS
SELECT c.stay_id,d.day_index,c.t0+d.day_index*INTERVAL '1 day' AS day_start,
 c.t0+(d.day_index+1)*INTERVAL '1 day' AS day_end,
 greatest(c.icu_intime,c.t0+d.day_index*INTERVAL '1 day') AS day_observed_start,
 least(c.followup_end,c.t0+(d.day_index+1)*INTERVAL '1 day') AS day_observed_end,
 greatest(0,EXTRACT(EPOCH FROM(least(c.followup_end,c.t0+(d.day_index+1)*INTERVAL '1 day')
   -greatest(c.icu_intime,c.t0+d.day_index*INTERVAL '1 day')))/3600.0) AS observed_icu_hours,
 c.followup_end,o.followup_end_reason,
 CASE WHEN c.t0+d.day_index*INTERVAL '1 day'>=c.followup_end THEN 'after_followup_end_'||o.followup_end_reason
      WHEN c.t0+(d.day_index+1)*INTERVAL '1 day'<=c.icu_intime THEN 'before_icu_observation'
      WHEN c.icu_intime<=c.t0+d.day_index*INTERVAL '1 day' AND c.followup_end>=c.t0+(d.day_index+1)*INTERVAL '1 day'
       THEN 'full_administrative_day'
      ELSE 'partial_administrative_day' END AS daily_observation_status,
 CASE WHEN least(c.followup_end,c.t0+(d.day_index+1)*INTERVAL '1 day')<=greatest(c.icu_intime,c.t0+d.day_index*INTERVAL '1 day')
       THEN 'outside_observation'
      WHEN count(a.stay_id) FILTER(WHERE a.valid_cam_result=1)>0 THEN 'observed_positive'
      WHEN count(a.stay_id) FILTER(WHERE a.valid_cam_result=0)>0 THEN 'observed_negative_only'
      WHEN count(a.stay_id)>0 THEN 'only_unassessable_or_incomplete_cam'
      ELSE 'no_cam_assessment' END AS daily_assessment_state,
 max(a.charttime) FILTER(WHERE a.valid_cam_result IS NOT NULL) AS last_valid_cam_time,
 count(a.stay_id) AS cam_assessments,
 count(a.stay_id) FILTER(WHERE a.valid_cam_result=1) AS positive_assessments,
 count(a.stay_id) FILTER(WHERE a.valid_cam_result=0) AS negative_assessments,
 count(a.stay_id) FILTER(WHERE a.assessment_status='deep_sedation_or_coma') AS unassessable_deep_cam,
 (SELECT count(*) FROM sad_rass_events r WHERE r.stay_id=c.stay_id AND r.valid_rass_range
  AND r.charttime>=c.t0+d.day_index*INTERVAL '1 day' AND r.charttime<c.t0+(d.day_index+1)*INTERVAL '1 day'
  AND r.charttime<=c.followup_end AND r.valuenum < -3) AS deep_rass_records,
 c.deathtime,c.icu_outtime
FROM sad_cohort c JOIN sad_outcome_summary o USING(stay_id)
CROSS JOIN generate_series(0,6) AS d(day_index)
LEFT JOIN sad_cam_assessments a ON a.stay_id=c.stay_id
 AND a.charttime>=c.t0+d.day_index*INTERVAL '1 day'
 AND a.charttime<c.t0+(d.day_index+1)*INTERVAL '1 day' AND a.charttime<=c.followup_end
GROUP BY c.stay_id,c.t0,c.icu_intime,c.followup_end,d.day_index,c.deathtime,c.icu_outtime,o.followup_end_reason;
-- Administrative time is NOT continuously observed mental status. No-CAM days,
-- days after death/discharge and negative-only observed days remain separate.
-- No delirium/coma-free-day endpoint is manufactured from sparsely observed days.
SELECT assessment_status,count(*) AS n FROM sad_cam_assessments GROUP BY assessment_status;
-- END MODULE 25_cam_rass_outcomes.sql

-- BEGIN MODULE 30_sedation.sql
-- SAD sedation/analgesia extraction; PostgreSQL 12+; 2026-10-19.
-- Run in the SAME session as upstream TEMP sad_cohort.
-- Required sad_cohort columns: stay_id, subject_id, hadm_id, t0,
-- icu_intime, icu_outtime, followup_end. One row per index ICU stay.
-- followup_end = min(t0+7d, ICU discharge, hospital discharge, death).
-- This module describes recorded exposure, not treatment assignment or benefit.
-- Read notes/sedation_design.txt before causal analyses.
-- Sources checked: https://mimic.mit.edu/docs/iv/modules/icu/inputevents.html
-- https://mimic.mit.edu/docs/iv/modules/icu/d_items.html
-- https://mimic.mit.edu/docs/iv/modules/hosp/emar.html
-- https://github.com/MIT-LCP/mimic-code/tree/main/mimic-iv/concepts/medication

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM sad_cohort WHERE t0 IS NULL OR stay_id IS NULL OR followup_end IS NULL) THEN
    RAISE EXCEPTION 'sad_cohort requires non-null t0, stay_id and followup_end';
  END IF;
  IF EXISTS (SELECT stay_id FROM sad_cohort GROUP BY stay_id HAVING count(*) > 1) THEN
    RAISE EXCEPTION '30_sedation requires exactly one t0 per stay_id';
  END IF;
END $$;

DROP TABLE IF EXISTS pg_temp.sad_sedation_summary;
DROP TABLE IF EXISTS pg_temp.sad_sedation_transitions;
DROP TABLE IF EXISTS pg_temp.sad_sedation_regimen_segments;
DROP TABLE IF EXISTS pg_temp.sad_sedation_drug_windows;
DROP TABLE IF EXISTS pg_temp.sad_sedation_intervals;
DROP TABLE IF EXISTS pg_temp.sad_sedation_episodes;
DROP TABLE IF EXISTS pg_temp.sad_sedation_emar_audit;
DROP TABLE IF EXISTS pg_temp.sad_sedation_emar_coverage;
DROP TABLE IF EXISTS pg_temp.sad_sedation_source_windows;
DROP TABLE IF EXISTS pg_temp.sad_sedation_events;
DROP TABLE IF EXISTS pg_temp.sad_sedation_dictionary_audit;
DROP TABLE IF EXISTS pg_temp.sad_sedation_dictionary;
DROP TABLE IF EXISTS pg_temp.sad_sedation_catalog;
DROP TABLE IF EXISTS pg_temp.sad_sedation_windows;
DROP TABLE IF EXISTS pg_temp._sad_sedation_source_ie;

-- Dictionary-driven mappings: actual itemids are obtained from the local d_items.
-- Generic and brand names; token boundaries avoid fentanyl matching remifentanil.
CREATE TEMP TABLE sad_sedation_catalog (
  drug text PRIMARY KEY, drug_class text NOT NULL, label_regex text NOT NULL
);
INSERT INTO sad_sedation_catalog VALUES
 ('dexmedetomidine','sedative','(^|[^a-z])(dexmedetomidine|precedex)([^a-z]|$)'),
 ('propofol','sedative','(^|[^a-z])(propofol|diprivan)([^a-z]|$)'),
 ('midazolam','benzodiazepine','(^|[^a-z])(midazolam|versed)([^a-z]|$)'),
 ('lorazepam','benzodiazepine','(^|[^a-z])(lorazepam|ativan)([^a-z]|$)'),
 ('diazepam','benzodiazepine','(^|[^a-z])(diazepam|valium)([^a-z]|$)'),
 ('ketamine','sedative','(^|[^a-z])(ketamine|ketalar)([^a-z]|$)'),
 ('fentanyl','opioid','(^|[^a-z])(fentanyl|sublimaze)([^a-z]|$)'),
 ('remifentanil','opioid','(^|[^a-z])(remifentanil|ultiva)([^a-z]|$)'),
 ('sufentanil','opioid','(^|[^a-z])(sufentanil|sufenta)([^a-z]|$)'),
 ('alfentanil','opioid','(^|[^a-z])(alfentanil|alfenta)([^a-z]|$)'),
 ('morphine','opioid','(^|[^a-z])(morphine|duramorph|astramorph)([^a-z]|$)'),
 ('hydromorphone','opioid','(^|[^a-z])(hydromorphone|dilaudid)([^a-z]|$)'),
 ('meperidine','opioid','(^|[^a-z])(meperidine|demerol|pethidine)([^a-z]|$)'),
 ('methadone','opioid','(^|[^a-z])(methadone|dolophine)([^a-z]|$)'),
 ('oxycodone','opioid','(^|[^a-z])(oxycodone|oxycontin|roxicodone|percocet)([^a-z]|$)'),
 ('hydrocodone','opioid','(^|[^a-z])(hydrocodone|vicodin|norco)([^a-z]|$)'),
 ('codeine','opioid','(^|[^a-z])(codeine)([^a-z]|$)'),
 ('tramadol','opioid','(^|[^a-z])(tramadol|ultram)([^a-z]|$)'),
 ('buprenorphine','opioid','(^|[^a-z])(buprenorphine|buprenex|subutex|suboxone)([^a-z]|$)');
-- PERF_FIX_BEGIN
ANALYZE sad_sedation_catalog;
-- PERF_FIX_END

CREATE TEMP TABLE sad_sedation_dictionary AS
SELECT d.itemid, d.label, d.abbreviation, d.linksto, d.category,
       d.unitname, c.drug, c.drug_class,
       count(*) OVER (PARTITION BY d.itemid) AS drug_matches_for_item
FROM sad_src_d_items d
JOIN sad_sedation_catalog c ON lower(d.label) ~ c.label_regex
WHERE lower(d.linksto) = 'inputevents';
CREATE INDEX ON sad_sedation_dictionary(itemid);
-- PERF_FIX_BEGIN
ANALYZE sad_sedation_dictionary;
-- PERF_FIX_END

-- Includes label candidates not mapped to a canonical drug and wrong-table items.
CREATE TEMP TABLE sad_sedation_dictionary_audit AS
SELECT d.itemid, d.label, d.abbreviation, d.linksto, d.category, d.unitname,
       (SELECT string_agg(m.drug, ',' ORDER BY m.drug)
        FROM sad_sedation_dictionary m WHERE m.itemid = d.itemid) AS mapped_drugs,
       CASE WHEN lower(coalesce(d.linksto,'')) <> 'inputevents' THEN 'not_inputevents'
            WHEN NOT EXISTS (SELECT 1 FROM sad_sedation_dictionary m WHERE m.itemid=d.itemid)
              THEN 'unmapped_candidate_review'
            ELSE 'mapped_review_label_and_route' END AS mapping_audit
FROM sad_src_d_items d
WHERE lower(d.label) ~ '(sedat|opioid|narcotic|benzodiaz|dexmed|precedex|propofol|diprivan|midazol|versed|loraz|ativan|diazep|valium|ketamin|ketalar|fentan|sufenta|alfenta|morphin|morphone|dilaudid|meperidin|demerol|methadone|oxycod|hydrocod|codeine|tramadol|buprenorph)';

-- Extraction interval is [-24h,+168h). Cross-boundary infusions are retained.
-- Invalid timestamps for the cohort stay are retained for audit, not imputed.
CREATE TEMP TABLE _sad_sedation_source_ie AS
SELECT c.t0, c.icu_intime, c.icu_outtime, c.followup_end,
       c.subject_id AS cohort_subject_id, c.hadm_id AS cohort_hadm_id,
       i.subject_id, i.hadm_id, i.stay_id, i.itemid,
       i.starttime, i.endtime, i.storetime, i.amount, i.amountuom,
       i.rate, i.rateuom, i.orderid, i.linkorderid, i.statusdescription,
       i.ordercategoryname, i.secondaryordercategoryname,
       i.ordercomponenttypedescription, i.ordercategorydescription,
       i.patientweight, i.originalamount, i.originalrate
FROM sad_cohort c JOIN sad_src_inputevents i ON i.stay_id = c.stay_id
WHERE i.starttime IS NULL OR i.endtime IS NULL OR i.endtime < i.starttime
   OR (i.starttime < c.t0 + interval '7 days'
       AND (i.endtime > c.t0 - interval '24 hours'
            OR i.starttime >= c.t0 - interval '24 hours'));
CREATE INDEX ON _sad_sedation_source_ie(stay_id, itemid, starttime, endtime);
-- PERF_FIX_BEGIN
ANALYZE _sad_sedation_source_ie;
-- PERF_FIX_END

CREATE TEMP TABLE sad_sedation_events AS
WITH raw AS (
 SELECT s.*, d.label, d.abbreviation, d.category AS dictionary_category,
        d.unitname AS dictionary_unitname, d.drug, d.drug_class,
        d.drug_matches_for_item,
        row_number() OVER (PARTITION BY s.stay_id,s.subject_id,s.hadm_id,s.itemid,
           s.starttime,s.endtime,s.storetime,s.orderid,s.linkorderid,
           s.amount,s.amountuom,s.rate,s.rateuom,s.statusdescription,
           s.ordercategoryname,s.secondaryordercategoryname,s.ordercomponenttypedescription,
           s.ordercategorydescription,s.patientweight,s.originalamount,s.originalrate,d.drug
           ORDER BY s.storetime NULLS LAST) AS exact_duplicate_rank,
        count(*) OVER (PARTITION BY s.stay_id,s.subject_id,s.hadm_id,s.itemid,
           s.starttime,s.endtime,s.storetime,s.orderid,s.linkorderid,
           s.amount,s.amountuom,s.rate,s.rateuom,s.statusdescription,
           s.ordercategoryname,s.secondaryordercategoryname,s.ordercomponenttypedescription,
           s.ordercategorydescription,s.patientweight,s.originalamount,s.originalrate,d.drug)
           AS exact_duplicate_count
 FROM _sad_sedation_source_ie s
 JOIN sad_sedation_dictionary d ON d.itemid=s.itemid
), classified AS (
 SELECT r.*,
   lower(coalesce(statusdescription,''))='rewritten' AS is_rewritten,
   starttime IS NULL OR endtime IS NULL OR endtime < starttime AS invalid_time,
   subject_id IS DISTINCT FROM cohort_subject_id OR hadm_id IS DISTINCT FROM cohort_hadm_id
       AS identity_mismatch,
   lower(coalesce(rate::text,'')) IN ('nan','infinity','-infinity','inf','-inf')
     OR lower(coalesce(amount::text,'')) IN ('nan','infinity','-infinity','inf','-inf') AS nonfinite_dose_value,
   lower(coalesce(rate::text,'')) NOT IN ('nan','infinity','-infinity','inf','-inf')
     AND lower(coalesce(amount::text,'')) NOT IN ('nan','infinity','-infinity','inf','-inf')
     AND (coalesce(rate,0)>0 OR coalesce(amount,0)>0)
       AND coalesce(rate,0)>=0 AND coalesce(amount,0)>=0 AS positive_delivery_evidence,
   (rate IS NULL AND endtime>=starttime AND endtime<=starttime+interval '1 minute') AS is_point_dose,
   CASE WHEN rate IS NULL AND endtime>=starttime AND endtime<=starttime+interval '1 minute'
          THEN 'bolus_candidate'
        WHEN lower(concat_ws(' ',ordercategoryname,ordercategorydescription,
                    secondaryordercategoryname)) ~ '(bolus|single dose)'
          THEN 'interval_type_uncertain'
        WHEN rate>0 OR lower(concat_ws(' ',ordercategoryname,ordercategorydescription)) ~ 'continuous'
          THEN 'infusion'
        ELSE 'interval_type_uncertain' END AS delivery_kind,
   greatest(starttime,t0-interval '24 hours') AS extraction_start,
   least(endtime,t0+interval '7 days') AS extraction_end,
   extract(epoch FROM (storetime-starttime))/3600.0 AS documentation_delay_hours,
   starttime<t0 AND storetime>t0 AS pre_t0_event_documented_after_t0,
   starttime<icu_intime OR endtime>icu_outtime AS outside_index_icu_bounds,
   starttime>=followup_end OR endtime>followup_end AS crosses_or_after_followup_end
 FROM raw r
)
SELECT row_number() OVER (ORDER BY stay_id,drug,starttime,endtime,orderid,storetime)
          AS sedation_event_id, x.*,
       NOT is_rewritten AND NOT invalid_time AND NOT identity_mismatch
       AND positive_delivery_evidence AND exact_duplicate_rank=1
       AND drug_matches_for_item=1
       AND (CASE WHEN is_point_dose
          THEN starttime>=greatest(t0-interval '24 hours',icu_intime)
             AND starttime<least(t0+interval '7 days',icu_outtime,followup_end)
          ELSE starttime<least(t0+interval '7 days',icu_outtime,followup_end)
             AND (endtime>greatest(t0-interval '24 hours',icu_intime)
               OR (starttime=endtime AND starttime>=greatest(t0-interval '24 hours',icu_intime))) END) AS is_usable,
       CASE WHEN invalid_time THEN NULL WHEN is_point_dose THEN 0
            ELSE greatest(0,extract(epoch FROM (extraction_end-extraction_start))/60.0)
            END AS extraction_overlap_minutes
FROM classified x;
CREATE INDEX ON sad_sedation_events(stay_id,drug,starttime,endtime);
-- PERF_FIX_BEGIN
ANALYZE sad_sedation_events;
-- PERF_FIX_END

-- Administrative observation does not guarantee complete medication capture.
CREATE TEMP TABLE sad_sedation_windows AS
SELECT c.stay_id,c.t0,w.window_name,w.hours,
       c.t0+w.lo_hours*interval '1 hour' AS window_start,
       c.t0+w.hi_hours*interval '1 hour' AS window_end,
       greatest(c.t0+w.lo_hours*interval '1 hour',c.icu_intime) AS observed_start,
       least(c.t0+w.hi_hours*interval '1 hour',c.icu_outtime,c.followup_end) AS observed_end,
       c.icu_intime IS NOT NULL AND c.icu_outtime IS NOT NULL
       AND c.icu_intime<=c.t0+w.lo_hours*interval '1 hour'
       AND c.icu_outtime>=c.t0+w.hi_hours*interval '1 hour'
       AND c.followup_end IS NOT NULL AND c.followup_end>=c.t0+w.hi_hours*interval '1 hour' AS complete_icu_window,
       c.icu_intime IS NULL OR c.icu_outtime IS NULL OR c.followup_end IS NULL AS icu_bounds_missing
FROM sad_cohort c CROSS JOIN (VALUES
 ('prior24h',24,-24,0),('post6h',6,0,6),('post12h',12,0,12),
 ('post24h',24,0,24),('post168h',168,0,168)
) AS w(window_name,hours,lo_hours,hi_hours);
-- PERF_FIX_BEGIN
ANALYZE sad_sedation_windows;
-- PERF_FIX_END

CREATE TEMP TABLE sad_sedation_source_windows AS
SELECT w.*, count(s.stay_id) AS any_inputevents_rows,
       count(s.stay_id) FILTER (WHERE lower(coalesce(s.statusdescription,''))<>'rewritten')
          AS nonrewritten_inputevents_rows,
       min(s.starttime) AS first_inputevent_start, max(s.endtime) AS last_inputevent_end
FROM sad_sedation_windows w
LEFT JOIN _sad_sedation_source_ie s ON s.stay_id=w.stay_id
 AND w.observed_end>w.observed_start
 AND s.starttime IS NOT NULL AND s.endtime>=s.starttime
 AND s.subject_id=s.cohort_subject_id AND s.hadm_id=s.cohort_hadm_id
 AND (CASE WHEN s.rate IS NULL AND s.endtime<=s.starttime+interval '1 minute'
       THEN s.starttime>=w.observed_start AND s.starttime<w.observed_end
       ELSE (s.starttime<w.observed_end AND s.endtime>w.observed_start)
         OR (s.starttime=s.endtime AND s.starttime>=w.observed_start AND s.starttime<w.observed_end) END)
GROUP BY w.stay_id,w.t0,w.window_name,w.hours,w.window_start,w.window_end,
         w.observed_start,w.observed_end,w.complete_icu_window,w.icu_bounds_missing;
-- PERF_FIX_BEGIN
ANALYZE sad_sedation_source_windows;
-- PERF_FIX_END

-- Union intervals by drug; duplicate/concurrent rows do not inflate minutes.
-- One-minute/no-rate bolus candidates are point doses, never duration exposure.
CREATE TEMP TABLE sad_sedation_intervals AS
WITH valid AS (
 SELECT e.stay_id,e.drug,e.drug_class,
        greatest(e.starttime,e.t0-interval '24 hours',e.icu_intime) AS lo,
        least(e.endtime,e.t0+interval '7 days',e.icu_outtime,e.followup_end) AS hi
 FROM sad_sedation_events e WHERE e.is_usable AND NOT e.is_point_dose AND e.endtime>e.starttime
), prev AS (
 SELECT *,max(hi) OVER (PARTITION BY stay_id,drug ORDER BY lo,hi
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_max_hi
 FROM valid WHERE hi>lo
), grp AS (
 SELECT *,sum(CASE WHEN prev_max_hi IS NULL OR lo>prev_max_hi THEN 1 ELSE 0 END)
          OVER (PARTITION BY stay_id,drug ORDER BY lo,hi) AS island
 FROM prev
)
SELECT stay_id,drug,drug_class,island,min(lo) AS starttime,max(hi) AS endtime
FROM grp GROUP BY stay_id,drug,drug_class,island;
CREATE INDEX ON sad_sedation_intervals(stay_id,drug,starttime,endtime);
-- PERF_FIX_BEGIN
ANALYZE sad_sedation_intervals;
-- PERF_FIX_END

-- Separate infusion episodes for continuation/newly observed episode decisions.
-- Touching same-drug rate-change segments are one episode; gaps are not filled.
CREATE TEMP TABLE sad_sedation_episodes AS
WITH clipped AS (
 SELECT stay_id,drug,drug_class,starttime,
  least(endtime,icu_outtime,followup_end,t0+interval '7 days') AS endtime
 FROM sad_sedation_events WHERE is_usable AND delivery_kind='infusion' AND endtime>starttime
  AND starttime<least(icu_outtime,followup_end,t0+interval '7 days')
  AND endtime>greatest(icu_intime,t0-interval '24 hours')
), valid AS (
 SELECT stay_id,drug,drug_class,starttime,endtime,
  max(endtime) OVER (PARTITION BY stay_id,drug ORDER BY starttime,endtime
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_max_end
 FROM clipped WHERE endtime>starttime
), grp AS (
 SELECT *,sum(CASE WHEN prev_max_end IS NULL OR starttime>prev_max_end THEN 1 ELSE 0 END)
       OVER (PARTITION BY stay_id,drug ORDER BY starttime,endtime) AS episode_no
 FROM valid
)
SELECT stay_id,drug,drug_class,episode_no,min(starttime) AS starttime,max(endtime) AS endtime
FROM grp GROUP BY stay_id,drug,drug_class,episode_no;
CREATE INDEX ON sad_sedation_episodes(stay_id,drug,starttime,endtime);
-- PERF_FIX_BEGIN
ANALYZE sad_sedation_episodes;
-- PERF_FIX_END

CREATE TEMP TABLE sad_sedation_drug_windows AS
WITH mapped AS (SELECT drug,count(*) AS mapped_itemids FROM sad_sedation_dictionary GROUP BY drug),
unlocated AS (
 SELECT stay_id,drug,count(*) AS unlocated_target_records FROM sad_sedation_events
 WHERE invalid_time AND NOT is_rewritten AND exact_duplicate_rank=1 GROUP BY stay_id,drug
),
aggregated AS (
 SELECT w.*,c.drug,c.drug_class,coalesce(m.mapped_itemids,0) AS mapped_itemids,
   coalesce(u.unlocated_target_records,0) AS unlocated_target_records,
   count(e.sedation_event_id) FILTER (WHERE NOT e.is_usable AND NOT e.is_rewritten AND e.exact_duplicate_rank=1)
     AS unusable_target_records,
   count(e.sedation_event_id) AS raw_drug_rows,
   count(e.sedation_event_id) FILTER (WHERE e.is_usable) AS usable_drug_rows,
   count(e.sedation_event_id) FILTER (WHERE e.is_rewritten) AS rewritten_rows,
   count(e.sedation_event_id) FILTER (WHERE e.is_usable AND e.delivery_kind='bolus_candidate') AS bolus_candidate_rows,
   count(e.sedation_event_id) FILTER (WHERE e.is_usable AND e.delivery_kind='interval_type_uncertain') AS uncertain_delivery_rows,
   min(e.starttime) FILTER (WHERE e.is_usable AND e.starttime>=w.window_start) AS first_record_start_in_window,
   min(greatest(e.starttime,w.window_start)) FILTER (WHERE e.is_usable) AS first_recorded_exposure_in_window,
   max(e.endtime) FILTER (WHERE e.is_usable) AS last_record_end_overlapping_window
 FROM sad_sedation_source_windows w CROSS JOIN sad_sedation_catalog c
 LEFT JOIN mapped m ON m.drug=c.drug
 LEFT JOIN unlocated u ON u.stay_id=w.stay_id AND u.drug=c.drug
 LEFT JOIN sad_sedation_events e ON e.stay_id=w.stay_id AND e.drug=c.drug
  AND w.observed_end>w.observed_start
  AND e.starttime IS NOT NULL AND e.endtime>=e.starttime
  AND (CASE WHEN e.is_point_dose THEN e.starttime>=w.observed_start AND e.starttime<w.observed_end
       ELSE (e.starttime<w.observed_end AND e.endtime>w.observed_start)
         OR (e.starttime=e.endtime AND e.starttime>=w.observed_start AND e.starttime<w.observed_end) END)
 GROUP BY w.stay_id,w.t0,w.window_name,w.hours,w.window_start,w.window_end,
  w.observed_start,w.observed_end,w.complete_icu_window,w.icu_bounds_missing,
  w.any_inputevents_rows,w.nonrewritten_inputevents_rows,w.first_inputevent_start,w.last_inputevent_end,
  c.drug,c.drug_class,m.mapped_itemids,u.unlocated_target_records
)
SELECT a.*,
 CASE WHEN usable_drug_rows>0 THEN 1
      WHEN unusable_target_records>0 OR unlocated_target_records>0 THEN NULL
      WHEN mapped_itemids=0 OR nonrewritten_inputevents_rows=0 OR NOT complete_icu_window THEN NULL
      ELSE 0 END AS recorded_exposure,
 CASE WHEN usable_drug_rows>0 THEN 'recorded'
      WHEN unusable_target_records>0 OR unlocated_target_records>0 THEN 'unknown_unusable_target_records'
      WHEN mapped_itemids=0 THEN 'unknown_no_dictionary_mapping'
      WHEN observed_end<=observed_start OR icu_bounds_missing THEN 'unknown_no_observed_icu_window'
      WHEN nonrewritten_inputevents_rows=0 THEN 'unknown_no_inputevents_source'
      WHEN NOT complete_icu_window THEN 'unknown_incomplete_icu_window'
      ELSE 'no_record_in_observed_inputevents' END AS exposure_state,
 coalesce((SELECT sum(extract(epoch FROM (least(i.endtime,a.observed_end)-greatest(i.starttime,a.observed_start)))/60.0)
   FROM sad_sedation_intervals i WHERE i.stay_id=a.stay_id AND i.drug=a.drug
      AND a.observed_end>a.observed_start
      AND i.starttime<a.observed_end AND i.endtime>a.observed_start),0) AS recorded_interval_minutes_union
FROM aggregated a;
-- PERF_FIX_BEGIN
ANALYZE sad_sedation_drug_windows;
-- PERF_FIX_END

-- Changes in the RECORDED infusion set; empty intervals show recorded gaps.
-- Sedative/benzodiazepine sets and opioid sets are kept separately.
CREATE TEMP TABLE sad_sedation_regimen_segments AS
WITH bounds AS (
 SELECT stay_id,observed_start AS point FROM sad_sedation_windows WHERE window_name='post168h' AND observed_end>observed_start
 UNION SELECT stay_id,observed_end FROM sad_sedation_windows WHERE window_name='post168h' AND observed_end>observed_start
 UNION SELECT e.stay_id,greatest(e.starttime,w.observed_start) FROM sad_sedation_episodes e
  JOIN sad_sedation_windows w USING(stay_id) WHERE w.window_name='post168h'
  AND w.observed_end>w.observed_start
  AND e.starttime<w.observed_end AND e.endtime>w.observed_start
 UNION SELECT e.stay_id,least(e.endtime,w.observed_end) FROM sad_sedation_episodes e
  JOIN sad_sedation_windows w USING(stay_id) WHERE w.window_name='post168h'
  AND w.observed_end>w.observed_start
  AND e.starttime<w.observed_end AND e.endtime>w.observed_start
), segments AS (
 SELECT stay_id,point AS starttime,lead(point) OVER (PARTITION BY stay_id ORDER BY point) AS endtime FROM bounds
)
SELECT s.stay_id,s.starttime,s.endtime,extract(epoch FROM(s.endtime-s.starttime))/60.0 AS minutes,
 coalesce(array_agg(DISTINCT e.drug ORDER BY e.drug) FILTER (WHERE e.drug_class IN ('sedative','benzodiazepine')),ARRAY[]::text[]) AS sedative_drugs,
 coalesce(array_agg(DISTINCT e.drug ORDER BY e.drug) FILTER (WHERE e.drug_class='opioid'),ARRAY[]::text[]) AS opioid_drugs,
 count(DISTINCT e.drug) FILTER (WHERE e.drug_class IN ('sedative','benzodiazepine')) AS n_sedatives,
 count(DISTINCT e.drug) FILTER (WHERE e.drug_class='opioid') AS n_opioids
FROM segments s LEFT JOIN sad_sedation_episodes e ON e.stay_id=s.stay_id
 AND e.starttime<s.endtime AND e.endtime>s.starttime
WHERE s.endtime>s.starttime GROUP BY s.stay_id,s.starttime,s.endtime;
-- PERF_FIX_BEGIN
CREATE INDEX sad_sedation_regimen_stay_idx ON sad_sedation_regimen_segments(stay_id);
ANALYZE sad_sedation_regimen_segments;
-- PERF_FIX_END

CREATE TEMP TABLE sad_sedation_transitions AS
WITH prior AS (
 SELECT *,lag(sedative_drugs) OVER(PARTITION BY stay_id ORDER BY starttime) AS prior_sedative_drugs,
          lag(opioid_drugs) OVER(PARTITION BY stay_id ORDER BY starttime) AS prior_opioid_drugs
 FROM sad_sedation_regimen_segments
)
SELECT *,CASE WHEN prior_sedative_drugs IS NULL THEN 'initial_observed_state'
  WHEN sedative_drugs=prior_sedative_drugs THEN 'sedative_set_unchanged'
  WHEN cardinality(sedative_drugs)=0 THEN 'recorded_sedative_gap_begins'
  WHEN cardinality(prior_sedative_drugs)=0 THEN 'recorded_sedative_set_starts'
  WHEN NOT (sedative_drugs && prior_sedative_drugs) THEN 'nonoverlapping_set_change_candidate'
  ELSE 'addition_removal_or_cross_taper_candidate' END AS transition_type
FROM prior WHERE prior_sedative_drugs IS NULL OR sedative_drugs<>prior_sedative_drugs OR opioid_drugs<>prior_opioid_drugs;
-- PERF_FIX_BEGIN
CREATE INDEX sad_sedation_transitions_stay_idx ON sad_sedation_transitions(stay_id);
ANALYZE sad_sedation_transitions;
-- PERF_FIX_END

-- eMAR is a SEPARATE audit source. No union with ICU amounts/durations: doing so
-- would double count and infer durations unavailable from the eMAR header.
CREATE TEMP TABLE sad_sedation_emar_audit (
 stay_id bigint,subject_id bigint,hadm_id bigint,emar_id text,charttime timestamp,
 storetime timestamp,medication text,event_txt text,drug text,drug_class text,
 in_index_icu boolean,administration_status text,documentation_delay_hours numeric
);
CREATE TEMP TABLE sad_sedation_emar_coverage (
 stay_id bigint PRIMARY KEY,emar_table_available boolean,any_emar_rows bigint,
 matching_emar_rows bigint,administered_matching_rows bigint
);
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM sad_source_status WHERE source_name='emar' AND available) THEN
  EXECUTE $q$ INSERT INTO sad_sedation_emar_audit
  SELECT c.stay_id,e.subject_id,e.hadm_id,e.emar_id,e.charttime,e.storetime,
    e.medication,e.event_txt,d.drug,d.drug_class,
    e.charttime>=c.icu_intime AND e.charttime<least(c.icu_outtime,c.followup_end),
    CASE WHEN lower(trim(coalesce(e.event_txt,'')))='administered' THEN 'documented_administered'
         WHEN lower(coalesce(e.event_txt,'')) ~ '(not given|held|refused|missed|delayed)' THEN 'not_administered_or_delayed'
         ELSE 'status_requires_review' END,
    extract(epoch FROM(e.storetime-e.charttime))/3600.0
  FROM sad_cohort c JOIN sad_src_emar e ON e.hadm_id=c.hadm_id AND e.subject_id=c.subject_id
   AND e.charttime>=c.t0-interval '24 hours' AND e.charttime<c.t0+interval '7 days'
  JOIN sad_sedation_catalog d ON lower(e.medication) ~ d.label_regex $q$;
  -- PERF_FIX_BEGIN
  CREATE INDEX sad_sedation_emar_stay_drug_time_idx ON sad_sedation_emar_audit(stay_id,drug,charttime);
  ANALYZE sad_sedation_emar_audit;
  -- PERF_FIX_END
  EXECUTE $q$ INSERT INTO sad_sedation_emar_coverage
  SELECT c.stay_id,true,count(e.emar_id),
    (SELECT count(*) FROM sad_sedation_emar_audit a WHERE a.stay_id=c.stay_id),
    (SELECT count(*) FROM sad_sedation_emar_audit a WHERE a.stay_id=c.stay_id AND a.administration_status='documented_administered')
  FROM sad_cohort c LEFT JOIN sad_src_emar e ON e.hadm_id=c.hadm_id AND e.subject_id=c.subject_id
   AND e.charttime>=c.t0-interval '24 hours' AND e.charttime<c.t0+interval '7 days'
  GROUP BY c.stay_id $q$;
 ELSE
  INSERT INTO sad_sedation_emar_coverage SELECT stay_id,false,NULL,NULL,NULL FROM sad_cohort;
 END IF;
END $$;
-- PERF_FIX_BEGIN
ANALYZE sad_sedation_emar_coverage;
-- PERF_FIX_END

-- One row per stay x canonical drug; all windows remain available in long form.
CREATE TEMP TABLE sad_sedation_summary AS
WITH event_summary AS (
 SELECT c.stay_id,c.subject_id,c.hadm_id,c.t0,c.icu_intime,c.icu_outtime,c.followup_end,d.drug,d.drug_class,
  count(e.sedation_event_id) AS audit_event_rows,
  count(e.sedation_event_id) FILTER(WHERE e.is_rewritten) AS rewritten_rows,
  count(e.sedation_event_id) FILTER(WHERE e.invalid_time) AS invalid_time_rows,
  count(e.sedation_event_id) FILTER(WHERE e.identity_mismatch) AS identity_mismatch_rows,
  count(e.sedation_event_id) FILTER(WHERE e.exact_duplicate_rank>1) AS duplicate_rows_excluded,
  count(e.sedation_event_id) FILTER(WHERE e.drug_matches_for_item>1) AS ambiguous_mapping_rows,
  count(e.sedation_event_id) FILTER(WHERE e.pre_t0_event_documented_after_t0) AS pre_t0_late_documentation_rows,
  count(e.sedation_event_id) FILTER(WHERE e.outside_index_icu_bounds) AS outside_icu_rows,
  count(e.sedation_event_id) FILTER(WHERE e.crosses_or_after_followup_end) AS crosses_or_after_followup_rows,
  count(e.sedation_event_id) FILTER(WHERE e.nonfinite_dose_value) AS nonfinite_dose_rows,
  EXISTS(SELECT 1 FROM sad_sedation_episodes p
    WHERE p.stay_id=c.stay_id AND p.drug=d.drug AND p.starttime<c.t0 AND p.endtime>c.t0
      AND (c.icu_intime IS NULL OR c.t0>=c.icu_intime)
      AND (c.icu_outtime IS NULL OR c.t0<c.icu_outtime)
      AND (c.followup_end IS NULL OR c.t0<c.followup_end)) AS has_recorded_continuation_at_t0,
  min(e.starttime) FILTER(WHERE e.is_usable AND e.starttime>=c.t0 AND e.starttime<c.t0+interval '7 days'
      AND (c.icu_intime IS NULL OR e.starttime>=c.icu_intime)
      AND (c.icu_outtime IS NULL OR e.starttime<c.icu_outtime)
      AND (c.followup_end IS NULL OR e.starttime<c.followup_end)) AS first_post_t0_record_start,
  min(e.starttime) FILTER(WHERE e.is_usable AND e.starttime<c.t0
      AND (CASE WHEN e.is_point_dose THEN e.starttime>=c.t0-interval '24 hours'
           ELSE e.endtime>c.t0-interval '24 hours' END)
      AND (c.icu_intime IS NULL OR (CASE WHEN e.is_point_dose THEN e.starttime>=c.icu_intime ELSE e.endtime>c.icu_intime END))
      AND (c.icu_outtime IS NULL OR e.starttime<c.icu_outtime)
      AND (c.followup_end IS NULL OR e.starttime<c.followup_end)) AS first_prior24h_overlapping_record_start
 FROM sad_cohort c CROSS JOIN sad_sedation_catalog d
 LEFT JOIN sad_sedation_events e ON e.stay_id=c.stay_id AND e.drug=d.drug
 GROUP BY c.stay_id,c.subject_id,c.hadm_id,c.t0,c.icu_intime,c.icu_outtime,c.followup_end,d.drug,d.drug_class
), windows AS (
 SELECT stay_id,drug,
  max(recorded_exposure) FILTER(WHERE window_name='prior24h') AS prior24h_recorded_exposure,
  max(recorded_exposure) FILTER(WHERE window_name='post6h') AS post6h_recorded_exposure,
  max(recorded_exposure) FILTER(WHERE window_name='post12h') AS post12h_recorded_exposure,
  max(recorded_exposure) FILTER(WHERE window_name='post24h') AS post24h_recorded_exposure,
  max(recorded_exposure) FILTER(WHERE window_name='post168h') AS post168h_recorded_exposure,
  max(exposure_state) FILTER(WHERE window_name='prior24h') AS prior24h_exposure_state,
  max(exposure_state) FILTER(WHERE window_name='post6h') AS post6h_exposure_state,
  max(unusable_target_records+unlocated_target_records) FILTER(WHERE window_name='prior24h') AS prior24h_uncertain_target_records,
  max(recorded_interval_minutes_union) FILTER(WHERE window_name='post6h') AS post6h_recorded_minutes_union,
  max(recorded_interval_minutes_union) FILTER(WHERE window_name='post12h') AS post12h_recorded_minutes_union,
  max(recorded_interval_minutes_union) FILTER(WHERE window_name='post24h') AS post24h_recorded_minutes_union
 FROM sad_sedation_drug_windows GROUP BY stay_id,drug
)
SELECT a.*,w.prior24h_recorded_exposure,w.post6h_recorded_exposure,w.post12h_recorded_exposure,
 w.post24h_recorded_exposure,w.post168h_recorded_exposure,w.prior24h_exposure_state,w.post6h_exposure_state,
 w.prior24h_uncertain_target_records,
 w.post6h_recorded_minutes_union,w.post12h_recorded_minutes_union,w.post24h_recorded_minutes_union,
 (SELECT min(p.starttime) FROM sad_sedation_episodes p WHERE p.stay_id=a.stay_id AND p.drug=a.drug
   AND p.starttime>=a.t0 AND p.starttime<a.t0+interval '7 days'
   AND (a.icu_intime IS NULL OR p.starttime>=a.icu_intime)
   AND (a.icu_outtime IS NULL OR p.starttime<a.icu_outtime)
   AND (a.followup_end IS NULL OR p.starttime<a.followup_end)) AS first_post_t0_infusion_episode_start,
 CASE WHEN a.has_recorded_continuation_at_t0 THEN 'continuing_at_t0'
      WHEN w.post6h_recorded_exposure=1 AND w.prior24h_recorded_exposure=0
       AND w.prior24h_uncertain_target_records=0 THEN 'newly_recorded_in_6h_no_prior24h_record'
      WHEN w.post6h_recorded_exposure=1 AND w.prior24h_recorded_exposure=1 THEN 'post_t0_exposure_with_prior_use'
      WHEN w.post6h_recorded_exposure=1 THEN 'post_t0_exposure_prior_status_unknown'
      ELSE w.post6h_exposure_state END AS descriptive_start_pattern,
 ec.emar_table_available,ec.any_emar_rows,
 CASE WHEN ec.emar_table_available THEN
  (SELECT count(*) FROM sad_sedation_emar_audit ea WHERE ea.stay_id=a.stay_id AND ea.drug=a.drug AND ea.in_index_icu AND ea.administration_status='documented_administered')
  ELSE NULL END AS emar_administered_rows,
 EXISTS(SELECT 1 FROM sad_sedation_emar_audit ea WHERE ea.stay_id=a.stay_id AND ea.drug=a.drug
   AND ea.in_index_icu AND ea.administration_status='documented_administered'
   AND NOT EXISTS(SELECT 1 FROM sad_sedation_events se WHERE se.stay_id=a.stay_id AND se.drug=a.drug AND se.is_usable
       AND ea.charttime>=se.starttime-interval '1 hour' AND ea.charttime<=se.endtime+interval '1 hour')) AS emar_without_nearby_inputevent_audit,
 (SELECT count(*) FROM sad_sedation_regimen_segments r WHERE r.stay_id=a.stay_id
      AND a.drug=ANY(r.sedative_drugs) AND r.n_sedatives>=2) AS combination_segments,
 (SELECT count(*) FROM sad_sedation_transitions r WHERE r.stay_id=a.stay_id
      AND (a.drug=ANY(r.sedative_drugs) OR a.drug=ANY(r.prior_sedative_drugs))
      AND r.transition_type IN ('nonoverlapping_set_change_candidate','addition_removal_or_cross_taper_candidate')) AS change_candidate_count
FROM event_summary a JOIN windows w USING(stay_id,drug)
LEFT JOIN sad_sedation_emar_coverage ec USING(stay_id);

-- Review dictionary and exclusions before export. Do not overwrite zero/NULL rules.
-- SELECT * FROM sad_sedation_dictionary ORDER BY drug,itemid;
-- SELECT * FROM sad_sedation_dictionary_audit ORDER BY mapping_audit,label;
-- SELECT * FROM sad_sedation_summary ORDER BY stay_id,drug;
-- SELECT * FROM sad_sedation_events WHERE NOT is_usable;
-- END MODULE 30_sedation.sql

-- BEGIN MODULE 40_vasoactive_fluids.sql
-- PostgreSQL. Run in the same session after sad_cohort is created.
-- Extraction only: this module DOES NOT assign early/late/untreated causal arms.
-- Source contract and source URLs: ../notes/vasoactive_design.txt.
-- A count of zero means zero matching rows, not absence of treatment.

DROP TABLE IF EXISTS pg_temp.sad_vasoactive_seed;
CREATE TEMP TABLE sad_vasoactive_seed (
    itemid integer, agent text, label_pattern text, source_url text
);
INSERT INTO sad_vasoactive_seed VALUES
 (221906,'norepinephrine','norepinephrine|noradrenaline|levophed','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/concepts/medication/norepinephrine.sql'),
 (221289,'epinephrine','(^|[^a-z])(epinephrine|adrenaline)','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/concepts/medication/epinephrine.sql'),
 (221662,'dopamine','dopamine','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/concepts/medication/dopamine.sql'),
 (221653,'dobutamine','dobutamine','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/concepts/medication/dobutamine.sql'),
 (222315,'vasopressin','(^|[^a-z])vasopressin','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/concepts/medication/vasopressin.sql'),
 (221749,'phenylephrine','phenylephrine|neo.?synephrine','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/concepts/medication/phenylephrine.sql'),
 (221986,'milrinone','milrinone','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/concepts/medication/milrinone.sql');

-- Do not silently reuse an itemid with an unexpected local label or linksto.
DROP TABLE IF EXISTS pg_temp.sad_vasoactive_mapping_audit;
CREATE TEMP TABLE sad_vasoactive_mapping_audit AS
SELECT s.*, d.label AS local_label, d.linksto,
       CASE WHEN d.itemid IS NULL THEN 'seed_missing_from_local_dictionary'
            WHEN lower(d.linksto) IS DISTINCT FROM 'inputevents' THEN 'unexpected_linksto'
            WHEN lower(d.label) ~ s.label_pattern THEN 'verified_local_label'
            ELSE 'unexpected_or_missing_label' END AS mapping_status
FROM sad_vasoactive_seed s
LEFT JOIN sad_src_d_items d ON d.itemid = s.itemid;

DROP TABLE IF EXISTS pg_temp.sad_vasoactive_dictionary;
CREATE TEMP TABLE sad_vasoactive_dictionary AS
WITH discovered AS (
 SELECT d.itemid,d.label,d.linksto,d.category,d.unitname,
        CASE
         WHEN lower(d.label) ~ 'norepinephrine|noradrenaline|levophed' THEN 'norepinephrine'
         WHEN lower(d.label) ~ '(^|[^a-z])(epinephrine|adrenaline)' THEN 'epinephrine'
         WHEN lower(d.label) ~ '(^|[^a-z])dopamine' THEN 'dopamine'
         WHEN lower(d.label) ~ 'dobutamine' THEN 'dobutamine'
         WHEN lower(d.label) ~ '(^|[^a-z])vasopressin' THEN 'vasopressin'
         WHEN lower(d.label) ~ 'phenylephrine|neo.?synephrine' THEN 'phenylephrine'
         WHEN lower(d.label) ~ 'angiotensin[ -]*(ii|2)|giapreza' THEN 'angiotensin_ii'
         WHEN lower(d.label) ~ 'milrinone' THEN 'milrinone'
         WHEN lower(d.label) ~ 'isoproterenol|isoprenaline|isuprel' THEN 'isoproterenol'
         WHEN lower(d.label) ~ 'methylene[ -]*blue' THEN 'methylene_blue'
         WHEN lower(d.label) ~ 'metaraminol' THEN 'metaraminol'
         WHEN lower(d.label) ~ '(^|[^a-z])ephedrine' THEN 'ephedrine'
        END AS agent
 FROM sad_src_d_items d WHERE lower(d.linksto) = 'inputevents'
)
SELECT d.*,
 CASE WHEN d.agent IN ('dobutamine','milrinone','isoproterenol') THEN 'inotrope_or_inodilator'
      WHEN d.agent = 'methylene_blue' THEN 'other_vasoactive_rescue'
      ELSE 'vasopressor' END AS drug_class,
 CASE WHEN s.itemid IS NOT NULL AND lower(d.label) ~ s.label_pattern
      THEN 'published_itemid_and_local_label' ELSE 'local_dictionary_label_candidate' END AS mapping_method,
 COALESCE(s.source_url,'https://mimic.mit.edu/docs/iv/modules/icu/d_items.html') AS mapping_source_url
FROM discovered d LEFT JOIN sad_vasoactive_seed s ON s.itemid = d.itemid
WHERE d.agent IS NOT NULL;

-- Fluid identities are discovered from the ACTUAL installed dictionary.
-- Legacy MetaVision IDs are checks only, never sufficient without label verification.
DROP TABLE IF EXISTS pg_temp.sad_fluid_seed;
CREATE TEMP TABLE sad_fluid_seed(itemid integer,label_pattern text,source_url text);
INSERT INTO sad_fluid_seed VALUES
 (225158,'nacl[ ]*0[.]9|normal saline','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iii/concepts/fluid_balance/crystalloid_bolus.sql'),
 (225828,'^lr$|lactated ringer|ringers? lactate','https://github.com/MIT-LCP/mimic-code/discussions/1150'),
 (225827,'d5lr|dextrose.*ringer','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iii/concepts/fluid_balance/crystalloid_bolus.sql'),
 (220864,'albumin.*5([^0-9]|$)','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iii/concepts/fluid_balance/colloid_bolus.sql'),
 (220862,'albumin.*25','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iii/concepts/fluid_balance/colloid_bolus.sql'),
 (225174,'hetastarch|hespan','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iii/concepts/fluid_balance/colloid_bolus.sql'),
 (225795,'dextran.*40','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iii/concepts/fluid_balance/colloid_bolus.sql'),
 (225796,'dextran.*70','https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iii/concepts/fluid_balance/colloid_bolus.sql');
DROP TABLE IF EXISTS pg_temp.sad_fluid_mapping_audit;
CREATE TEMP TABLE sad_fluid_mapping_audit AS
SELECT s.*,d.label AS local_label,d.linksto,
 CASE WHEN d.itemid IS NULL THEN 'seed_missing_from_local_dictionary'
      WHEN lower(d.linksto) IS DISTINCT FROM 'inputevents' THEN 'unexpected_linksto'
      WHEN lower(d.label) ~ s.label_pattern THEN 'verified_local_label'
      ELSE 'unexpected_or_missing_label' END AS mapping_status
FROM sad_fluid_seed s LEFT JOIN sad_src_d_items d ON s.itemid=d.itemid;

DROP TABLE IF EXISTS pg_temp.sad_fluid_dictionary;
CREATE TEMP TABLE sad_fluid_dictionary AS
WITH x AS (
 SELECT d.itemid,d.label,d.linksto,d.category,d.unitname,
  CASE
   WHEN lower(d.label) ~ 'albumin' THEN 'albumin'
   WHEN lower(d.label) ~ 'packed.*(rbc|red)|red.*blood.*cell|prbc|fresh frozen|platelet|cryoprecip|whole blood|blood product|^ffp$|^plasma$'
        OR lower(d.category) ~ 'blood' THEN 'blood_product'
   WHEN lower(d.label) ~ 'hetastarch|hespan|dextran|voluven|gelofusin|gelatin|colloid'
        OR lower(d.category) ~ 'colloid' THEN 'colloid_non_albumin'
   WHEN lower(d.label) ~ '^(nacl|normal saline|lactated ringer|ringers|lr$|d5|d10|dextrose|plasma.?lyte|normosol)|crystalloid'
        OR lower(d.category) ~ 'crystalloid' THEN 'crystalloid'
   WHEN lower(d.label) ~ '^(sterile water|free water|solution|piggyback)$' THEN 'other_fluid_or_carrier'
  END AS fluid_class
 FROM sad_src_d_items d WHERE lower(d.linksto) = 'inputevents'
)
SELECT x.*,
 CASE WHEN lower(label) ~ 'albumin.*25' THEN 'albumin_25_percent'
      WHEN lower(label) ~ 'albumin.*5([^0-9]|$)' THEN 'albumin_5_percent'
      WHEN fluid_class = 'albumin' THEN 'albumin_other_or_unspecified'
      WHEN lower(label) ~ 'packed.*(rbc|red)|red.*blood.*cell|prbc' THEN 'red_cells'
      WHEN lower(label) ~ 'fresh frozen|^ffp$' THEN 'fresh_frozen_plasma'
      WHEN lower(label) ~ 'platelet' THEN 'platelets'
      WHEN lower(label) ~ 'cryoprecip' THEN 'cryoprecipitate'
      WHEN lower(label) ~ '(^|[^a-z])(or|pacu)([^a-z]|$)|preadmi|pre.admi' THEN 'aggregate_prior_or_perioperative_intake'
      WHEN lower(label) ~ '^(lr|lactated ringers?|ringers? lactate|plasma.?lyte|normosol)' THEN 'balanced_crystalloid_candidate'
      WHEN lower(label) ~ '^nacl[ ]*0[.]9%|^normal saline$' THEN 'isotonic_saline_candidate'
      WHEN lower(label) ~ 'dextrose|^d5|^d10|nacl[ ]*(0[.]45|3|7|23)' THEN 'nonstandard_resuscitation_fluid'
      ELSE 'other_or_unspecified' END AS fluid_subtype,
 CASE WHEN s.itemid IS NOT NULL AND lower(x.label) ~ s.label_pattern
      THEN 'published_itemid_and_local_label'
      ELSE 'runtime_label_or_category_candidate' END AS mapping_method,
 COALESCE(s.source_url,'https://mimic.mit.edu/docs/iv/modules/icu/d_items.html') AS mapping_source_url
FROM x LEFT JOIN sad_fluid_seed s ON x.itemid=s.itemid
WHERE fluid_class IS NOT NULL;

-- Keep the original fields. Null/invalid ends are retained for audit, not extended
-- to t0 or the end of follow-up. Events are linked by stay_id AND patient/admission.
DROP TABLE IF EXISTS pg_temp.sad_input_candidates;
CREATE TEMP TABLE sad_input_candidates AS
SELECT row_number() OVER (ORDER BY c.stay_id,i.starttime,i.endtime,i.itemid,i.orderid,i.storetime) AS extraction_row_id,
 c.t0,c.icu_intime,c.icu_outtime,c.followup_end,
 c.t0 - interval '24 hours' AS requested_start,
 LEAST(c.t0 + interval '7 days',c.followup_end,c.icu_outtime) AS requested_end,
 i.subject_id,i.hadm_id,i.stay_id,i.starttime,i.endtime,i.storetime,i.itemid,
 i.amount,i.amountuom,i.rate,i.rateuom,i.orderid,i.linkorderid,
 i.ordercategoryname,i.secondaryordercategoryname,i.ordercomponenttypedescription,i.ordercategorydescription,
 i.patientweight,i.totalamount,i.totalamountuom,i.statusdescription,i.originalamount,i.originalrate,
 lower(COALESCE(i.statusdescription,'')) = 'rewritten' AS is_rewritten,
 (i.statusdescription IS NULL) AS missing_status,
 ((i.rate > 0 AND i.rate::text NOT IN ('NaN','Infinity','-Infinity'))
   OR (i.amount > 0 AND i.amount::text NOT IN ('NaN','Infinity','-Infinity'))) AS positive_amount_or_rate,
 (COALESCE(i.rate::text IN ('NaN','Infinity','-Infinity'),false)
   OR COALESCE(i.amount::text IN ('NaN','Infinity','-Infinity'),false)) AS nonfinite_numeric_flag,
 (COALESCE(i.rate<0,false) OR COALESCE(i.amount<0,false)) AS negative_numeric_flag,
 CASE
  WHEN i.starttime IS NULL THEN 'missing_start'
  WHEN i.endtime < i.starttime THEN 'invalid_negative_duration'
  WHEN i.rate IS NULL AND (i.endtime = i.starttime OR i.endtime = i.starttime + interval '1 minute')
       THEN 'bolus_point_from_null_rate_and_0_or_1min_duration'
  WHEN i.rate IS NULL AND i.endtime IS NULL
       AND lower(COALESCE(i.ordercategorydescription,'')) ~ 'bolus'
       THEN 'bolus_point_from_explicit_category'
  WHEN i.endtime > i.starttime THEN 'interval'
  ELSE 'unknown_duration'
 END AS timing_type,
 (i.storetime > c.t0) AS documented_after_t0,
 (i.starttime < c.icu_intime) AS start_before_icu_admission,
 (i.endtime > c.icu_outtime) AS end_after_icu_discharge,
 (i.starttime>=c.followup_end) AS starts_after_observation_end,
 (i.endtime>c.followup_end) AS crosses_observation_end
FROM sad_cohort c
JOIN sad_src_inputevents i ON i.stay_id=c.stay_id AND i.subject_id=c.subject_id AND i.hadm_id=c.hadm_id
WHERE (i.itemid IN (SELECT itemid FROM sad_vasoactive_dictionary)
    OR i.itemid IN (SELECT itemid FROM sad_fluid_dictionary))
 -- Retain post-discharge/death rows for audit; usable evidence below requires observed overlap.
 AND (i.starttime < c.t0 + interval '7 days' OR i.starttime IS NULL)
 AND (i.endtime > c.t0 - interval '24 hours'
      OR i.starttime >= c.t0 - interval '24 hours'
      OR i.endtime IS NULL OR i.endtime < i.starttime);

-- FRESH_PERF_BEGIN
ANALYZE sad_input_candidates;
-- FRESH_PERF_END
DROP TABLE IF EXISTS pg_temp.sad_vasoactive_events;
CREATE TEMP TABLE sad_vasoactive_events AS
SELECT i.*,d.label,d.category,d.unitname AS dictionary_unitname,d.agent,d.drug_class,d.mapping_method,d.mapping_source_url,
 CASE WHEN NOT is_rewritten AND NOT nonfinite_numeric_flag AND NOT negative_numeric_flag
           AND positive_amount_or_rate IS TRUE
           AND ((timing_type='interval' AND GREATEST(starttime,requested_start,icu_intime)<LEAST(endtime,requested_end,icu_outtime))
             OR (timing_type LIKE 'bolus_point%' AND starttime>=GREATEST(requested_start,icu_intime)
                 AND starttime<requested_end))
      THEN true ELSE false END AS usable_positive_documentation,
 CASE WHEN is_rewritten THEN 'rewritten_audit_only'
      WHEN nonfinite_numeric_flag THEN 'nonfinite_dose_needs_review'
      WHEN negative_numeric_flag THEN 'negative_dose_needs_review'
      WHEN timing_type IN ('missing_start','invalid_negative_duration','unknown_duration') THEN 'timing_needs_review'
      WHEN positive_amount_or_rate IS NOT TRUE THEN 'no_positive_dose_evidence'
      WHEN starttime>=requested_end OR COALESCE(endtime,starttime)<GREATEST(requested_start,icu_intime) THEN 'outside_observation_window_audit_only'
      ELSE 'documented_positive_exposure' END AS evidence_status,
 CASE WHEN timing_type='interval' THEN GREATEST(starttime,requested_start,icu_intime)
      WHEN timing_type LIKE 'bolus_point%' THEN starttime END AS overlap_start,
 CASE WHEN timing_type='interval' THEN LEAST(endtime,requested_end,icu_outtime)
      WHEN timing_type LIKE 'bolus_point%' THEN starttime END AS overlap_end,
 EXTRACT(epoch FROM (starttime-t0))/3600.0 AS start_hours_from_t0
FROM sad_input_candidates i JOIN sad_vasoactive_dictionary d USING(itemid);
CREATE INDEX ON sad_vasoactive_events(stay_id,starttime,endtime);
ANALYZE sad_vasoactive_events;

DROP TABLE IF EXISTS pg_temp.sad_fluid_events;
CREATE TEMP TABLE sad_fluid_events AS
SELECT i.*,d.label,d.category,d.unitname AS dictionary_unitname,d.fluid_class,d.fluid_subtype,d.mapping_method,d.mapping_source_url,
 CASE WHEN amount::text IN ('NaN','Infinity','-Infinity') OR (amount=0 AND rate>0) THEN NULL
      WHEN lower(trim(amountuom)) IN ('ml','milliliter','milliliters') AND amount >= 0 THEN amount
      WHEN lower(trim(amountuom)) IN ('l','liter','liters') AND amount >= 0 THEN amount*1000.0
      ELSE NULL END AS recorded_amount_ml,
 CASE WHEN amount=0 AND rate>0 THEN 'zero_amount_positive_rate_conflict'
      WHEN lower(trim(amountuom)) IN ('ml','milliliter','milliliters','l','liter','liters') AND amount >= 0
           AND amount::text NOT IN ('NaN','Infinity','-Infinity')
      THEN 'known_volume_unit' ELSE 'unknown_volume_or_negative_amount' END AS volume_status,
 lower(COALESCE(ordercategoryname,'') || ' ' || COALESCE(secondaryordercategoryname,'') || ' ' || COALESCE(ordercomponenttypedescription,''))
      ~ 'medication|additive|mixed solution' AS possible_medication_carrier,
 lower(COALESCE(d.label,'') || ' ' || COALESCE(ordercategoryname,''))
      ~ '(^|[^a-z])(or|pacu)([^a-z]|$)|preadmi|pre.admi' AS possible_aggregate_prior_intake,
 lower(COALESCE(ordercategorydescription,'') || ' ' || COALESCE(ordercategoryname,'')) ~ 'bolus' AS explicit_bolus_label,
 CASE WHEN NOT is_rewritten AND NOT nonfinite_numeric_flag AND NOT negative_numeric_flag
           AND positive_amount_or_rate IS TRUE
           AND ((timing_type='interval' AND GREATEST(starttime,requested_start,icu_intime)<LEAST(endtime,requested_end,icu_outtime))
             OR (timing_type LIKE 'bolus_point%' AND starttime>=GREATEST(requested_start,icu_intime)
                 AND starttime<requested_end))
      THEN true ELSE false END AS usable_positive_documentation
FROM sad_input_candidates i JOIN sad_fluid_dictionary d USING(itemid);
CREATE INDEX ON sad_fluid_events(stay_id,starttime,endtime);
ANALYZE sad_fluid_events;

-- Exact/raw Rewritten records remain available independently of all summaries.
DROP TABLE IF EXISTS pg_temp.sad_input_rewritten_audit;
CREATE TEMP TABLE sad_input_rewritten_audit AS
SELECT i.*,d.agent,f.fluid_class
FROM sad_input_candidates i
LEFT JOIN sad_vasoactive_dictionary d USING(itemid)
LEFT JOIN sad_fluid_dictionary f USING(itemid)
WHERE i.is_rewritten;

-- All expected core agents remain visible even when the local dictionary has no match.
DROP TABLE IF EXISTS pg_temp.sad_vasoactive_groups;
CREATE TEMP TABLE sad_vasoactive_groups AS
SELECT DISTINCT agent AS agent_group FROM sad_vasoactive_seed
UNION SELECT DISTINCT agent FROM sad_vasoactive_dictionary
UNION SELECT 'angiotensin_ii'
UNION SELECT 'any_vasopressor'
UNION SELECT 'any_vasoactive';

DROP TABLE IF EXISTS pg_temp.sad_vasoactive_expanded;
CREATE TEMP TABLE sad_vasoactive_expanded AS
SELECT e.*,g.agent_group
FROM sad_vasoactive_events e
JOIN sad_vasoactive_groups g ON g.agent_group=e.agent OR g.agent_group='any_vasoactive'
 OR (g.agent_group='any_vasopressor' AND e.drug_class='vasopressor');
CREATE INDEX ON sad_vasoactive_expanded(stay_id,agent_group,starttime,endtime);
ANALYZE sad_vasoactive_expanded;

-- Merge overlapping/touching intervals before reporting duration; do not double
-- count simultaneous pressors or rate-change rows. Boluses have no inferred duration.
DROP TABLE IF EXISTS pg_temp.sad_vasoactive_merged_intervals;
CREATE TEMP TABLE sad_vasoactive_merged_intervals AS
WITH interval_rows AS (
 SELECT DISTINCT stay_id,agent_group,overlap_start,overlap_end
 FROM sad_vasoactive_expanded
 WHERE usable_positive_documentation AND timing_type='interval' AND overlap_end>overlap_start
), ordered AS (
 SELECT stay_id,agent_group,overlap_start,overlap_end,
  MAX(overlap_end) OVER (PARTITION BY stay_id,agent_group ORDER BY overlap_start,overlap_end
     ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS previous_max_end
 FROM interval_rows
), numbered AS (
 SELECT *,SUM(CASE WHEN previous_max_end IS NULL OR overlap_start>previous_max_end THEN 1 ELSE 0 END)
  OVER (PARTITION BY stay_id,agent_group ORDER BY overlap_start,overlap_end ROWS UNBOUNDED PRECEDING) AS interval_group
 FROM ordered
)
SELECT stay_id,agent_group,MIN(overlap_start) AS interval_start,MAX(overlap_end) AS interval_end
FROM numbered GROUP BY stay_id,agent_group,interval_group;
CREATE INDEX ON sad_vasoactive_merged_intervals(stay_id,agent_group,interval_start,interval_end);
ANALYZE sad_vasoactive_merged_intervals;

DROP TABLE IF EXISTS pg_temp.sad_vasoactive_summary;
CREATE TEMP TABLE sad_vasoactive_summary AS
WITH base AS (
 SELECT c.stay_id,c.subject_id,c.hadm_id,c.t0,c.icu_intime,c.icu_outtime,c.followup_end,g.agent_group,
  COUNT(e.extraction_row_id) AS n_matching_rows_including_audit,
  COUNT(e.extraction_row_id) FILTER (WHERE e.is_rewritten) AS n_rewritten_rows,
  COUNT(e.extraction_row_id) FILTER (WHERE NOT e.is_rewritten AND NOT e.usable_positive_documentation) AS n_uncertain_or_nonpositive_rows,
  COUNT(e.extraction_row_id) FILTER (WHERE NOT e.is_rewritten AND NOT e.usable_positive_documentation
     AND (e.starttime<c.t0 OR e.starttime IS NULL)) AS n_uncertain_or_nonpositive_pre_t0_rows,
  COUNT(e.extraction_row_id) FILTER (WHERE e.usable_positive_documentation AND e.starttime<c.t0
     AND ((e.timing_type='interval' AND e.endtime>c.t0-interval '24 hours')
       OR (e.timing_type LIKE 'bolus_point%' AND e.starttime>=c.t0-interval '24 hours'))) AS n_documented_pre24h_rows,
  BOOL_OR(true) FILTER (WHERE e.usable_positive_documentation AND e.timing_type='interval'
     AND e.starttime<=c.t0 AND e.endtime>c.t0) AS documented_active_at_t0,
  BOOL_OR(true) FILTER (WHERE e.usable_positive_documentation AND e.timing_type='interval'
     AND e.starttime<c.t0 AND e.endtime>c.t0) AS documented_already_active_before_t0,
  MIN(e.starttime) FILTER (WHERE e.usable_positive_documentation AND e.starttime>=c.t0) AS first_documented_post_t0_start,
  MIN(e.starttime) FILTER (WHERE e.usable_positive_documentation AND e.starttime>=c.t0 AND e.timing_type='interval') AS first_documented_post_t0_infusion_start,
  COUNT(e.extraction_row_id) FILTER (WHERE e.usable_positive_documentation AND e.timing_type LIKE 'bolus_point%' AND e.starttime>=c.t0) AS n_post_t0_bolus_rows
 FROM sad_cohort c CROSS JOIN sad_vasoactive_groups g
 LEFT JOIN sad_vasoactive_expanded e ON e.stay_id=c.stay_id AND e.agent_group=g.agent_group
 GROUP BY c.stay_id,c.subject_id,c.hadm_id,c.t0,c.icu_intime,c.icu_outtime,c.followup_end,g.agent_group
)
SELECT b.*,
 EXTRACT(epoch FROM (first_documented_post_t0_start-t0))/3600.0 AS hours_to_first_documented_post_t0_start,
 CASE WHEN documented_already_active_before_t0 IS TRUE THEN 'documented_ongoing_from_before_t0'
      WHEN first_documented_post_t0_start IS NOT NULL AND n_documented_pre24h_rows>0 THEN 'post_t0_start_with_documented_prior_use'
      WHEN first_documented_post_t0_start IS NOT NULL AND n_uncertain_or_nonpositive_pre_t0_rows>0 THEN 'post_t0_start_prior_status_needs_review'
      WHEN first_documented_post_t0_start IS NOT NULL THEN 'candidate_new_start_no_pre24h_use_documented'
      WHEN n_documented_pre24h_rows>0 THEN 'pre_t0_use_only_documented'
      WHEN n_uncertain_or_nonpositive_rows>0 THEN 'indeterminate_records_present'
      ELSE 'no_positive_exposure_documented_not_confirmed_untreated' END AS descriptive_exposure_pattern,
 (icu_intime<=t0-interval '24 hours') AS full_pre24h_within_icu,
 (icu_intime<=t0 AND icu_outtime>=t0+interval '24 hours' AND followup_end>=t0+interval '24 hours') AS full_post24h_calendar_available,
 'NULL exposure flags mean no qualifying positive documentation; they are not confirmed absence'::text AS missingness_note
FROM base b;

-- Long window table: 0-1/3/6/12/24 h plus pre24 h. Windows are reporting
-- intervals only. No choice of a definitive early-treatment threshold is made.
DROP TABLE IF EXISTS pg_temp.sad_vasoactive_window_summary;
CREATE TEMP TABLE sad_vasoactive_window_summary AS
WITH windows AS (
 SELECT c.stay_id,c.t0,c.icu_intime,c.icu_outtime,c.followup_end,g.agent_group,w.window_name,
  c.t0 + w.start_h*interval '1 hour' AS window_start,
  c.t0 + w.end_h*interval '1 hour' AS window_end
 FROM sad_cohort c CROSS JOIN sad_vasoactive_groups g
 CROSS JOIN (VALUES ('pre24h',-24,0),('post_0_1h',0,1),('post_0_3h',0,3),
  ('post_0_6h',0,6),('post_0_12h',0,12),('post_0_24h',0,24)) w(window_name,start_h,end_h)
)
SELECT w.*,
 GREATEST(w.window_start,w.icu_intime) AS available_window_start,
 LEAST(w.window_end,w.icu_outtime,w.followup_end) AS available_window_end,
 (w.icu_intime<=w.window_start AND w.icu_outtime>=w.window_end AND w.followup_end>=w.window_end) AS full_calendar_window_available,
 dur.documented_infusion_minutes,
 ev.n_positive_rows,ev.n_positive_starts,ev.n_positive_bolus_rows,
 uncertain.n_uncertain_candidate_rows,
 CASE WHEN ev.n_positive_rows>0 THEN true ELSE NULL END AS documented_exposure,
 CASE WHEN ev.n_positive_rows>0 THEN 'documented_positive_exposure'
      WHEN uncertain.n_uncertain_candidate_rows>0 THEN 'unknown_unusable_target_records'
      WHEN w.icu_intime>w.window_start OR w.icu_outtime<w.window_end OR w.followup_end<w.window_end THEN 'unknown_partial_calendar_coverage'
      ELSE 'no_positive_record_not_confirmed_absence' END AS observation_status
FROM windows w
LEFT JOIN LATERAL (
 SELECT SUM(EXTRACT(epoch FROM (LEAST(m.interval_end,w.window_end)-GREATEST(m.interval_start,w.window_start)))/60.0) AS documented_infusion_minutes
 FROM sad_vasoactive_merged_intervals m
 WHERE m.stay_id=w.stay_id AND m.agent_group=w.agent_group
  AND m.interval_start<w.window_end AND m.interval_end>w.window_start
) dur ON true
LEFT JOIN LATERAL (
 SELECT COUNT(*) AS n_positive_rows,
  COUNT(*) FILTER (WHERE e.starttime>=w.window_start AND e.starttime<w.window_end) AS n_positive_starts,
  COUNT(*) FILTER (WHERE e.timing_type LIKE 'bolus_point%') AS n_positive_bolus_rows
 FROM sad_vasoactive_expanded e
 WHERE e.stay_id=w.stay_id AND e.agent_group=w.agent_group AND e.usable_positive_documentation
  AND ((e.timing_type='interval' AND e.overlap_start<w.window_end AND e.overlap_end>w.window_start)
    OR (e.timing_type LIKE 'bolus_point%' AND e.starttime>=w.window_start AND e.starttime<w.window_end))
) ev ON true
LEFT JOIN LATERAL (
 SELECT COUNT(*) AS n_uncertain_candidate_rows
 FROM sad_vasoactive_expanded e
 WHERE e.stay_id=w.stay_id AND e.agent_group=w.agent_group
  AND NOT e.is_rewritten AND NOT e.usable_positive_documentation
  AND (e.starttime IS NULL OR (e.starttime<w.window_end
       AND (e.endtime IS NULL OR e.endtime>w.window_start OR e.endtime<e.starttime)))
) uncertain ON true;

-- Fluid time allocation is explicitly an ESTIMATE. A documented bolus point is
-- assigned at its recorded start without proportional division. Bag totals are
-- NOT used as administered amounts; unknown amount/unit remains NULL.
DROP TABLE IF EXISTS pg_temp.sad_fluid_window_allocations;
CREATE TEMP TABLE sad_fluid_window_allocations AS
SELECT e.extraction_row_id,e.stay_id,e.t0,e.itemid,e.label,e.fluid_class,e.fluid_subtype,
 e.possible_medication_carrier,e.possible_aggregate_prior_intake,e.explicit_bolus_label,
 e.amount,e.amountuom,e.recorded_amount_ml,e.volume_status,e.starttime,e.endtime,
 w.window_name,b.window_start,b.window_end,
 CASE WHEN e.possible_aggregate_prior_intake THEN 'prior_or_perioperative_aggregate_not_time_allocatable'
      WHEN e.recorded_amount_ml IS NULL THEN 'unknown_volume'
      WHEN e.timing_type LIKE 'bolus_point%' THEN 'recorded_bolus_point_amount'
      WHEN e.timing_type='interval' THEN 'uniform_rate_fraction_estimate'
      ELSE 'unknown_timing' END AS allocation_method,
 CASE WHEN e.possible_aggregate_prior_intake THEN NULL
      WHEN e.timing_type LIKE 'bolus_point%' THEN e.recorded_amount_ml
      WHEN e.timing_type='interval' THEN e.recorded_amount_ml
          * EXTRACT(epoch FROM (LEAST(e.endtime,b.window_end)-GREATEST(e.starttime,b.window_start)))
          / NULLIF(EXTRACT(epoch FROM (e.endtime-e.starttime)),0)
      ELSE NULL END AS allocated_volume_ml,
 (e.icu_intime<=e.t0+w.start_h*interval '1 hour'
  AND e.icu_outtime>=e.t0+w.end_h*interval '1 hour'
  AND e.followup_end>=e.t0+w.end_h*interval '1 hour') AS full_calendar_window_available
FROM sad_fluid_events e
CROSS JOIN (VALUES ('pre24h',-24,0),('post_0_1h',0,1),('post_0_3h',0,3),
 ('post_0_6h',0,6),('post_0_12h',0,12),('post_0_24h',0,24),('post_0_7d',0,168)) w(window_name,start_h,end_h)
CROSS JOIN LATERAL (SELECT GREATEST(e.t0+w.start_h*interval '1 hour',e.icu_intime) AS window_start,
 LEAST(e.t0+w.end_h*interval '1 hour',e.icu_outtime,e.followup_end) AS window_end) b
WHERE e.usable_positive_documentation AND b.window_end>b.window_start
 AND ((e.timing_type='interval' AND e.starttime<b.window_end AND e.endtime>b.window_start)
      OR (e.timing_type LIKE 'bolus_point%' AND e.starttime>=b.window_start AND e.starttime<b.window_end));

-- FRESH_PERF_BEGIN
ANALYZE sad_fluid_window_allocations;
-- FRESH_PERF_END
DROP TABLE IF EXISTS pg_temp.sad_fluid_window_summary;
CREATE TEMP TABLE sad_fluid_window_summary AS
SELECT stay_id,window_name,fluid_class,fluid_subtype,possible_medication_carrier,possible_aggregate_prior_intake,
 COUNT(*) AS n_documented_positive_rows,
 COUNT(*) FILTER (WHERE allocated_volume_ml IS NULL) AS n_rows_with_unallocated_or_unknown_volume,
 SUM(allocated_volume_ml) FILTER (WHERE allocation_method='recorded_bolus_point_amount') AS documented_point_bolus_volume_ml,
 SUM(allocated_volume_ml) FILTER (WHERE allocation_method='uniform_rate_fraction_estimate') AS uniform_allocated_volume_ml,
 SUM(allocated_volume_ml) AS known_component_volume_ml,
 CASE WHEN COUNT(*) FILTER (WHERE allocated_volume_ml IS NULL)=0 THEN SUM(allocated_volume_ml) ELSE NULL END AS all_documented_rows_quantifiable_volume_ml,
 BOOL_AND(full_calendar_window_available) AS full_calendar_window_available
FROM sad_fluid_window_allocations
GROUP BY stay_id,window_name,fluid_class,fluid_subtype,possible_medication_carrier,possible_aggregate_prior_intake;
-- END MODULE 40_vasoactive_fluids.sql

-- BEGIN MODULE 50_hospital_medications.sql
-- Complement ICU infusions with hospital eMAR (recorded administrations) and prescriptions (orders only).
-- https://mimic.mit.edu/docs/iv/modules/hosp/emar.html
-- https://mimic.mit.edu/docs/iv/modules/hosp/emar_detail.html
-- https://mimic.mit.edu/docs/iv/modules/hosp/prescriptions.html
-- No eMAR event_txt or prescription is silently interpreted as administered.
CREATE TEMP TABLE sad_medication_patterns(drug_group text,pattern text);
INSERT INTO sad_medication_patterns VALUES
 ('sedative','dexmedetomidine|precedex|propofol|diprivan|midazolam|versed|lorazepam|ativan|diazepam|valium|ketamine|etomidate'),
 ('opioid','fentanyl|morphine|hydromorphone|dilaudid|remifentanil|sufentanil|oxycodone|methadone|meperidine|tramadol'),
 ('vasoactive','norepinephrine|noradrenaline|levophed|epinephrine|adrenalin|phenylephrine|neosynephrine|vasopressin|dopamine|dobutamine|milrinone|angiotensin'),
 ('corticosteroid','hydrocortisone|methylprednisolone|dexamethasone|prednisone|prednisolone|fludrocortisone'),
 ('neuromuscular_blocker','cisatracurium|atracurium|rocuronium|vecuronium|pancuronium|succinylcholine'),
 ('antiepileptic','levetiracetam|keppra|phenytoin|fosphenytoin|valproate|valproic|carbamazepine|oxcarbazepine|phenobarbital|lacosamide|topiramate|lamotrigine|gabapentin|pregabalin'),
 ('delirium_sleep_psychotropic','haloperidol|quetiapine|olanzapine|risperidone|ziprasidone|melatonin|ramelteon|zolpidem|trazodone'),
 ('antimicrobial_candidate','penicillin|ampicillin|amoxicillin|piperacillin|tazobactam|cef[a-z]|vancomycin|meropenem|imipenem|ertapenem|aztreonam|ciprofloxacin|levofloxacin|moxifloxacin|metronidazole|clindamycin|linezolid|daptomycin|azithromycin|clarithromycin|erythromycin|doxycycline|minocycline|gentamicin|tobramycin|amikacin|trimethoprim|sulfamethoxazole|fluconazole|micafungin|caspofungin|amphotericin|acyclovir|oseltamivir');
CREATE TEMP TABLE sad_hospital_emar AS
SELECT c.stay_id,c.t0,e.subject_id,e.hadm_id,e.emar_id,e.charttime,e.storetime,e.medication,e.event_txt,
 string_agg(DISTINCT p.drug_group,';') AS candidate_groups,
 (e.charttime<c.t0) AS clinical_time_pre_t0,
 (e.charttime<c.t0 AND e.storetime<=c.t0) AS documented_pre_t0,
 (e.charttime>c.followup_end) AS after_icu_death_or_discharge,
 'Raw eMAR status retained. Inspect event_txt and detail before classifying administration; do not add ICU and eMAR doses'::text AS interpretation
FROM sad_cohort c JOIN sad_src_emar e ON e.hadm_id=c.hadm_id AND e.subject_id=c.subject_id
 AND e.charttime>=c.t0-INTERVAL '24 hours' AND e.charttime<=c.t0+INTERVAL '7 days'
JOIN sad_medication_patterns p ON e.medication ~* p.pattern
GROUP BY c.stay_id,c.t0,c.followup_end,e.subject_id,e.hadm_id,e.emar_id,e.charttime,e.storetime,e.medication,e.event_txt;
CREATE INDEX ON sad_hospital_emar(emar_id,subject_id);
-- FRESH_PERF_BEGIN
ANALYZE sad_hospital_emar;
-- FRESH_PERF_END
CREATE TEMP TABLE sad_hospital_emar_details AS
SELECT e.stay_id,e.t0,e.emar_id,e.charttime,e.medication,e.event_txt,
 to_jsonb(d)->>'emar_seq' AS emar_seq,
 to_jsonb(d)->>'parent_field_ordinal' AS parent_field_ordinal,
 to_jsonb(d)->>'administration_type' AS administration_type,
 to_jsonb(d)->>'dose_given' AS dose_given_raw,
 to_jsonb(d)->>'dose_given_unit' AS dose_given_unit_raw,
 to_jsonb(d)->>'route' AS route_raw,
 to_jsonb(d)->>'infusion_rate' AS infusion_rate_raw,
 to_jsonb(d)->>'infusion_rate_unit' AS infusion_rate_unit_raw,
 to_jsonb(d)->>'infusion_complete' AS infusion_complete_raw,
 to_jsonb(d)->>'new_iv_bag_hung' AS new_iv_bag_hung_raw,
 to_jsonb(d)->>'product_amount_given' AS product_amount_given_raw,
 to_jsonb(d)->>'product_unit' AS product_unit_raw
FROM sad_hospital_emar e JOIN sad_src_emar_detail d ON d.emar_id=e.emar_id AND d.subject_id=e.subject_id;
CREATE TEMP TABLE sad_prescription_orders AS
SELECT c.stay_id,c.t0,p.subject_id,p.hadm_id,p.pharmacy_id,p.starttime,p.stoptime,
 p.drug,p.drug_type,p.route,p.dose_val_rx,p.dose_unit_rx,
 (p.starttime<=c.t0 AND coalesce(p.stoptime,p.starttime)>c.t0) AS order_spans_t0,
 'Prescription/order only: not evidence of actual administration or its exact timing'::text AS interpretation
FROM sad_cohort c JOIN sad_src_prescriptions p ON p.hadm_id=c.hadm_id AND p.subject_id=c.subject_id
 AND p.starttime<=c.t0+INTERVAL '7 days' AND coalesce(p.stoptime,p.starttime)>=c.t0-INTERVAL '24 hours'
WHERE EXISTS(SELECT 1 FROM sad_medication_patterns x WHERE p.drug ~* x.pattern);
CREATE TEMP TABLE sad_hospital_medication_audit AS
SELECT medication,event_txt,candidate_groups,count(*) AS records,count(DISTINCT stay_id) AS patients
FROM sad_hospital_emar GROUP BY medication,event_txt,candidate_groups;

-- ICU administrations of concomitant drugs also matter when hospital eMAR is absent.
-- These rows overlap the dedicated sedation/pressor files: never add their doses together.
CREATE TEMP TABLE sad_concomitant_drug_dictionary AS
SELECT d.itemid,d.label,d.category,d.unitname,string_agg(DISTINCT p.drug_group,';') AS candidate_groups
FROM sad_src_d_items d JOIN sad_medication_patterns p ON d.label ~* p.pattern
WHERE lower(d.linksto)='inputevents'
GROUP BY d.itemid,d.label,d.category,d.unitname;
CREATE TEMP TABLE sad_concomitant_input_events AS
SELECT c.stay_id,c.subject_id,c.hadm_id,c.t0,d.itemid,d.label,d.candidate_groups,
 i.starttime,i.endtime,i.storetime,i.amount,i.amountuom,i.rate,i.rateuom,
 i.patientweight,i.orderid,i.linkorderid,i.statusdescription,
 i.ordercategoryname,i.secondaryordercategoryname,i.ordercategorydescription,
 (lower(coalesce(i.statusdescription,''))='rewritten') AS is_rewritten,
 (i.starttime<c.t0 AND i.storetime<=c.t0) AS documented_pre_t0,
 (i.starttime>=c.followup_end) AS after_observation_end,
 (i.endtime>c.followup_end) AS crosses_observation_end,
 (i.starttime IS NULL OR i.endtime IS NULL OR i.endtime<i.starttime) AS uncertain_interval,
 (coalesce(i.rate::text IN('NaN','Infinity','-Infinity'),false) OR coalesce(i.amount::text IN('NaN','Infinity','-Infinity'),false)
  OR coalesce(i.rate<0,false) OR coalesce(i.amount<0,false)) AS invalid_dose_value
FROM sad_cohort c JOIN sad_src_inputevents i ON i.stay_id=c.stay_id
 AND i.subject_id=c.subject_id AND i.hadm_id=c.hadm_id
 AND (i.starttime<c.t0+INTERVAL '7 days' OR i.starttime IS NULL)
 AND (i.endtime>c.t0-INTERVAL '24 hours' OR i.starttime>=c.t0-INTERVAL '24 hours' OR i.endtime IS NULL OR i.endtime<i.starttime)
JOIN sad_concomitant_drug_dictionary d USING(itemid);
CREATE INDEX ON sad_concomitant_input_events(stay_id,starttime,endtime);
-- END MODULE 50_hospital_medications.sql

-- BEGIN MODULE 60_physiology_time_series.sql
-- Sparse hourly summaries plus raw data: NO last-observation-carried-forward and NO missing=normal.
-- These are descriptive engineering outputs, not a target-trial analysis or eligibility rule.
-- Keep raw item/unit identity in the long-form output; do not merge arterial/nonarterial/specimen sources blindly.
CREATE TEMP TABLE sad_hourly_chart AS
SELECT stay_id,floor(hours_from_t0)::integer AS hour_from_t0,itemid,label,valueuom,
 count(*) AS records,count(valuenum) AS numeric_records,
 min(valuenum) AS value_min,max(valuenum) AS value_max,avg(valuenum) AS value_mean,
 min(charttime) AS first_measurement_time,max(charttime) AS last_measurement_time,
 min(storetime) AS first_documented_time,max(storetime) AS last_documented_time,
 count(*) FILTER(WHERE valuenum IS NULL) AS nonnumeric_records
FROM sad_chart_events
WHERE hours_from_t0>=-24 AND hours_from_t0<168 AND NOT after_icu_death_or_discharge
 AND (valuenum IS NULL OR valuenum::text NOT IN ('NaN','Infinity','-Infinity'))
GROUP BY stay_id,floor(hours_from_t0)::integer,itemid,label,valueuom;
CREATE TEMP TABLE sad_hourly_lab AS
SELECT stay_id,floor(hours_from_t0)::integer AS sample_hour_from_t0,itemid,label,fluid,valueuom,
 count(*) AS records,min(valuenum) AS value_min,max(valuenum) AS value_max,avg(valuenum) AS value_mean,
 min(charttime) AS first_sample_time,max(charttime) AS last_sample_time,
 min(storetime) AS first_result_available_time,max(storetime) AS last_result_available_time
FROM sad_lab_events WHERE hours_from_t0>=-24 AND hours_from_t0<168
 AND NOT after_icu_death_or_discharge AND (valuenum IS NULL OR valuenum::text NOT IN ('NaN','Infinity','-Infinity'))
GROUP BY stay_id,floor(hours_from_t0)::integer,itemid,label,fluid,valueuom;
CREATE TEMP TABLE sad_baseline_last_chart AS
SELECT DISTINCT ON(stay_id,itemid) stay_id,itemid,label,charttime,storetime,value,valuenum,valueuom,
 'Last charttime before t0 with storetime<=t0; unknown storetime is excluded from available-at-t0 view'::text AS rule
FROM sad_chart_events WHERE charttime<t0 AND charttime>=t0-INTERVAL '24 hours'
 AND storetime<=t0 ORDER BY stay_id,itemid,charttime DESC,storetime DESC,value;
CREATE TEMP TABLE sad_baseline_last_lab AS
SELECT DISTINCT ON(stay_id,itemid) stay_id,itemid,label,fluid,charttime,storetime,value,valuenum,valueuom,specimen_id,
 'Last available result by storetime<=t0; sample charttime also precedes t0'::text AS rule
FROM sad_lab_events WHERE charttime<t0 AND charttime>=t0-INTERVAL '24 hours'
 AND storetime<=t0 ORDER BY stay_id,itemid,storetime DESC,charttime DESC,labevent_id DESC;
-- Candidate low-MAP records are for eligibility audit, not an automatic vasopressor indication.
-- Exact labels exclude MAP goal/threshold settings; mapping is exported for review.
CREATE TEMP TABLE sad_map_dictionary AS
SELECT itemid,label FROM sad_chart_dictionary
WHERE lower(label) IN ('arterial blood pressure mean','non invasive blood pressure mean','arterial blood pressure mean (manual)',
 'arterial blood pressure mean (abp)','mean arterial pressure')
 OR (label ~* '(arterial|blood) pressure.*mean' AND label !~* 'goal|alarm|limit|target');
CREATE TEMP TABLE sad_map_events AS
SELECT e.*,CASE WHEN e.valuenum BETWEEN 1 AND 250 THEN e.valuenum ELSE NULL END AS map_value_for_audit,
 CASE WHEN e.valuenum BETWEEN 1 AND 250 THEN e.valuenum<65 ELSE NULL END AS map_below_65_audit_only
FROM sad_chart_events e JOIN sad_map_dictionary d USING(itemid);
CREATE TEMP TABLE sad_extraction_quality AS
SELECT 'cohort_rows'::text AS check_name,count(*)::bigint AS n FROM sad_cohort
UNION ALL SELECT 'original_manuscript_rows',count(*) FROM sad_cohort WHERE in_manuscript
UNION ALL SELECT 'source_absent_optional',count(*) FROM sad_source_status WHERE NOT available
UNION ALL SELECT 'no_chart_in_selected_window',count(*) FROM sad_cohort c WHERE NOT EXISTS(SELECT 1 FROM sad_chart_events e WHERE e.stay_id=c.stay_id)
UNION ALL SELECT 'no_valid_strict_post_cam',count(*) FROM sad_outcome_summary WHERE strict_post7_valid_n=0
UNION ALL SELECT 'legacy_vs_strict_known_label_disagreement',count(*) FROM sad_outcome_summary WHERE legacy_sad_7days IS NOT NULL AND strict_observed_sad_7days IS NOT NULL AND legacy_sad_7days<>strict_observed_sad_7days
UNION ALL SELECT 'legacy_known_but_strict_unknown',count(*) FROM sad_outcome_summary WHERE legacy_sad_7days IS NOT NULL AND strict_observed_sad_7days IS NULL
UNION ALL SELECT 't0_before_icu',count(*) FROM sad_cohort WHERE t0_before_icu
UNION ALL SELECT 'invalid_cohort_time_order',count(*) FROM sad_cohort WHERE invalid_temporal_order;
SELECT * FROM sad_extraction_quality;
-- END MODULE 60_physiology_time_series.sql

-- BEGIN MODULE 70_delivery_audit.sql
-- Final package manifest; no source data is modified.
CREATE TEMP TABLE sad_run_metadata AS
SELECT current_timestamp AS extraction_time,current_database() AS database_name,version() AS postgres_version,
 current_user AS database_role,c.icu_schema,c.hosp_schema,c.derived_schema,
 'SAD_SQL_20261020_FRESH_PERF_V1'::text AS package_version,
 (SELECT count(*) FROM sad_cohort) AS extracted_cohort_rows
FROM sad_config c;
CREATE TEMP TABLE sad_export_manifest(table_name text PRIMARY KEY,row_granularity text,purpose text,row_count bigint);
INSERT INTO sad_export_manifest(table_name,row_granularity,purpose) VALUES
('sad_config','1 row','Resolved source schemas'),
('sad_source_status','source table','Availability; absent optional source is unknown'),
('sad_cohort','stay_id','Broad seed, manuscript membership, times and observation boundaries'),
('sad_cohort_database_audit','stay_id','Seed versus installed database consistency'),
('sad_chart_dictionary','itemid','Selected chart labels and units'),
('sad_chart_events','raw chart event','Vitals, respiratory, neuro, sedation, CAM/RASS and documented care context'),
('sad_chart_coverage','itemid','Event and patient coverage'),
('sad_lab_dictionary','itemid','Selected lab definitions and specimen fluid'),
('sad_lab_events','stay_id x labevent_id','Raw labs; specimen time differs from result availability'),
('sad_lab_coverage','itemid','Lab coverage and late result availability'),
('sad_urine_events','raw output event','Urine and irrigant identity; do not sum indiscriminately'),
('sad_admission_context','stay_id','Admission demographics and anchor-year context'),
('sad_diagnosis_context','stay_id x diagnosis row','Discharge codes, not automatically known at baseline'),
('sad_service_events','stay_id x service event','Service transitions'),
('sad_ventilation_dictionary','itemid','Respiratory procedure mappings'),
('sad_ventilation_events','raw procedure event','Intervals, point events and quality flags'),
('sad_ventilation_summary','stay_id','Documented invasive ventilation; absence is unknown'),
('sad_derived_ventilation_events','stay_id x interval','Optional installed ventilation concept'),
('sad_cam_dictionary_audit','itemid','Original-study CAM mapping against installed labels'),
('sad_cam_value_audit','itemid x raw value','Explicit yes/no/unknown mapping audit'),
('sad_cam_forms','stay_id x charttime x form','Strict feature logic and legacy approximation'),
('sad_cam_assessments','stay_id x charttime','Strict CAM, nearest RASS, conflicts and availability'),
('sad_rass_events','raw RASS event','Raw scores, storetime and valid range'),
('sad_rass_timepoints','stay_id x charttime','Same-time RASS conflicts'),
('sad_outcome_summary','stay_id','Observed SAD, unknown assessment, death and follow-up completeness'),
('sad_outcome_daily','stay_id x day_index','Daily observation and assessment states; not fabricated coma-free days'),
('sad_sedation_catalog','drug','Canonical drug list'),
('sad_sedation_dictionary','itemid x drug match','Runtime mapped sedative/opioid labels'),
('sad_sedation_dictionary_audit','candidate itemid','Missing or ambiguous mappings'),
('sad_sedation_events','sedation_event_id','Raw exposure with duplicate/dose/time/usability flags'),
('sad_sedation_source_windows','stay_id x window','Inputevents source coverage'),
('sad_sedation_drug_windows','stay_id x drug x window','Exposure states, overlap duration and completeness'),
('sad_sedation_episodes','stay_id x drug x episode','Union of contiguous or overlapping infusion segments'),
('sad_sedation_regimen_segments','stay_id x interval','Concurrent sedative/opioid sets'),
('sad_sedation_transitions','stay_id x interval','Candidate set change, addition or gap'),
('sad_sedation_summary','stay_id x drug','Long format, NOT one row per patient'),
('sad_sedation_emar_audit','stay_id x emar event x drug match','Separate administration-status audit; no dose union'),
('sad_sedation_emar_coverage','stay_id','eMAR availability and coverage'),
('sad_vasoactive_mapping_audit','seed itemid','Known IDs validated against actual labels'),
('sad_vasoactive_dictionary','itemid','Vasopressor versus inotrope and other categories'),
('sad_fluid_mapping_audit','seed itemid','Fluid seed label validation'),
('sad_fluid_dictionary','itemid','Fluid classes and subtypes'),
('sad_vasoactive_events','extraction_row_id','Raw doses, units and start/stop; no forced NE-equivalence'),
('sad_fluid_events','extraction_row_id','Raw fluid amount, rate, carrier and aggregate flags'),
('sad_input_rewritten_audit','extraction_row_id','Rewritten entries excluded from positive exposure'),
('sad_vasoactive_merged_intervals','stay_id x agent_group x interval','Union duration without overlapping double-count'),
('sad_vasoactive_summary','stay_id x agent_group','Long format; grouped and individual drugs overlap'),
('sad_vasoactive_window_summary','stay_id x agent_group x window','Cumulative descriptive time windows'),
('sad_fluid_window_allocations','extraction_row_id x window','Explicit uniform-rate approximation or point assignment'),
('sad_fluid_window_summary','stay_id x window x fluid type x flags','Incomplete amounts remain unknown; cumulative windows overlap'),
('sad_hospital_emar','stay_id x emar event','Sedation, vasoactive and concomitant medication statuses'),
('sad_hospital_emar_details','stay_id x emar detail row','Raw dose, route, infusion and product fields'),
('sad_prescription_orders','stay_id x prescription row','Orders only, not actual administration'),
('sad_hospital_medication_audit','medication x status x group','Raw medication/status mappings'),
('sad_concomitant_drug_dictionary','itemid','Steroid, paralytic, neuropsychiatric, antimicrobial and other candidates'),
('sad_concomitant_input_events','stay_id x input event','ICU concomitant actual-record evidence; overlaps dedicated drug files'),
('sad_hourly_chart','stay_id x hour x itemid x unit','Sparse chart aggregates, no carry-forward'),
('sad_hourly_lab','stay_id x sample hour x itemid x unit','Sparse specimen-time aggregates; availability retained'),
('sad_baseline_last_chart','stay_id x itemid','Last documented available chart at original t0'),
('sad_baseline_last_lab','stay_id x itemid','Last available lab result at original t0'),
('sad_map_dictionary','itemid','MAP measurement candidates, excludes goals'),
('sad_map_events','raw MAP event','MAP<65 audit marker is not an automatic indication'),
('sad_extraction_quality','check_name','Coverage and strict/legacy label differences'),
('sad_run_metadata','1 row','Database version and local execution metadata');
DO $sad$
DECLARE r record; n bigint;
BEGIN
 FOR r IN SELECT table_name FROM sad_export_manifest LOOP
  IF to_regclass(format('pg_temp.%I',r.table_name)) IS NULL THEN
   RAISE EXCEPTION 'Expected output missing: %',r.table_name;
  END IF;
  EXECUTE format('SELECT count(*) FROM pg_temp.%I',r.table_name) INTO n;
  UPDATE sad_export_manifest SET row_count=n WHERE table_name=r.table_name;
 END LOOP;
END $sad$;
CREATE TEMP TABLE sad_export_columns AS
SELECT m.table_name,a.attnum AS column_number,a.attname AS column_name,
 format_type(a.atttypid,a.atttypmod) AS postgres_type
FROM sad_export_manifest m
JOIN pg_attribute a ON a.attrelid=to_regclass(format('pg_temp.%I',m.table_name))
WHERE a.attnum>0 AND NOT a.attisdropped;
SELECT * FROM sad_export_manifest ORDER BY table_name;
-- END MODULE 70_delivery_audit.sql

-- Verify every expected data table was counted before declaring completion.
DO $completion_guard$
BEGIN
 IF (SELECT count(*) FROM pg_temp.sad_export_manifest)<>64
    OR EXISTS(SELECT 1 FROM pg_temp.sad_export_manifest WHERE row_count IS NULL)
    OR (SELECT count(*) FROM pg_temp.sad_run_metadata WHERE package_version='SAD_SQL_20261020_FRESH_PERF_V1')<>1 THEN
  RAISE EXCEPTION 'Final manifest/version verification failed; do not export this run as complete.';
 END IF;
END $completion_guard$;
CREATE TEMP TABLE sad_fresh_completion AS
SELECT current_setting('sad.current_run_token') AS run_token,
       'SAD_SQL_20261020_FRESH_PERF_V1'::text AS package_version,
       pg_backend_pid() AS backend_pid,clock_timestamp() AS finished_at;
COMMIT;
-- This row is emitted only after a successful commit of this specific attempt.
SELECT 'SUCCESS_ALL_MODULES_COMPLETED_EXPORT_BEFORE_CLOSING_CONNECTION'::text AS completion,
       backend_pid,finished_at,package_version
FROM pg_temp.sad_fresh_completion
WHERE run_token=current_setting('sad.current_run_token') AND backend_pid=pg_backend_pid();

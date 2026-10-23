-- First configure a writable database-server-local output folder:
-- SET sad.output_dir = '/absolute/local/path/eicu_exports';
-- BEGIN 00_setup.sql
-- eICU 2.0 FULL extraction, ICU24h clinical-sepsis landmark.
-- Run the WHOLE file in a NEW Navicat query connected to the eICU database.
-- Source tables are read-only. Temporary tables and server-side CSV output only.
-- No sampling cap. Predictor NULLs remain NULL. Outcomes are never imputed.
-- All files are valid as a completed set only when the matching SUCCESS.csv exists.
-- Resource settings apply only to this transaction; final GUI output is one row.
BEGIN;
DO $attempt$ BEGIN
 PERFORM set_config('sad_eicu_full.attempt',
  'full_'||to_char(clock_timestamp(),'YYYYMMDD_HH24MISS_US')||'_'||pg_backend_pid(),false);
 PERFORM set_config('sad_eicu_full.success','',false);
END $attempt$;
COMMIT;
BEGIN;
SET LOCAL statement_timeout = '30min';
SET LOCAL lock_timeout = '5s';
SET LOCAL work_mem = '16MB';
SET LOCAL max_parallel_workers_per_gather = 0;
SET LOCAL search_path = pg_temp, pg_catalog;
DO $guard$
BEGIN
 IF to_regclass('pg_temp.ef_config') IS NOT NULL THEN
  RAISE EXCEPTION 'This connection already ran an eICU extraction. Open a NEW query window; do not overwrite the existing run.';
 END IF;
END $guard$;
CREATE TEMP TABLE ef_config(
 source_schema text, per_hospital integer, maximum_stays integer,
 output_dir text, sample_seed text, started_at timestamptz, run_id text
);
-- Optional: replace NULL with the exact schema name if auto-detection is ambiguous.
INSERT INTO ef_config VALUES(
 NULL,NULL,NULL,current_setting('sad.output_dir'),
 'FULL_NO_SAMPLING',clock_timestamp(),
 current_setting('sad_eicu_full.attempt')
);
CREATE TEMP TABLE ef_status(stage text,object_name text,status text,detail text);
CREATE TEMP TABLE ef_report(section text,item text,details jsonb);
CREATE TEMP TABLE ef_specs(table_name text,seq integer,col_name text,col_type text);
INSERT INTO ef_specs VALUES
('patient',1,'patientunitstayid','integer'),
('patient',2,'patienthealthsystemstayid','integer'),
('patient',3,'hospitalid','integer'),
('patient',4,'uniquepid','text'),
('patient',5,'age','text'),
('patient',6,'hospitaladmitoffset','integer'),
('patient',7,'unitdischargeoffset','integer'),
('patient',8,'unitvisitnumber','integer'),
('patient',9,'hospitaldischargeyear','integer'),
('patient',10,'gender','text'),
('nursecharting',1,'patientunitstayid','integer'),
('nursecharting',2,'nursingchartoffset','integer'),
('nursecharting',3,'nursingchartentryoffset','integer'),
('nursecharting',4,'nursingchartcelltypecat','text'),
('nursecharting',5,'nursingchartcelltypevallabel','text'),
('nursecharting',6,'nursingchartcelltypevalname','text'),
('nursecharting',7,'nursingchartvalue','text'),
('nurseassessment',1,'patientunitstayid','integer'),
('nurseassessment',2,'nurseassessoffset','integer'),
('nurseassessment',3,'nurseassessentryoffset','integer'),
('nurseassessment',4,'cellattributepath','text'),
('nurseassessment',5,'celllabel','text'),
('nurseassessment',6,'cellattribute','text'),
('nurseassessment',7,'cellattributevalue','text'),
('diagnosis',1,'patientunitstayid','integer'),
('diagnosis',2,'diagnosisoffset','integer'),
('diagnosis',3,'diagnosisstring','text'),
('diagnosis',4,'icd9code','text'),
('medication',1,'patientunitstayid','integer'),
('medication',2,'drugstartoffset','integer'),
('medication',3,'drugstopoffset','integer'),
('medication',4,'drugorderoffset','integer'),
('medication',5,'drugname','text'),
('medication',6,'routeadmin','text'),
('medication',7,'drugordercancelled','text'),
('microlab',1,'patientunitstayid','integer'),
('microlab',2,'culturetakenoffset','integer'),
('microlab',3,'culturesite','text'),
('microlab',4,'organism','text'),
('lab',1,'patientunitstayid','integer'),
('lab',2,'labresultoffset','integer'),
('lab',3,'labresultrevisedoffset','integer'),
('lab',4,'labname','text'),
('lab',5,'labresult','numeric'),
('lab',6,'labtypename','text'),
('lab',7,'labtypeid','integer'),
('lab',8,'labmeasurenamesystem','text'),
('lab',9,'labmeasurenameinterface','text'),
('intakeoutput',1,'patientunitstayid','integer'),
('intakeoutput',2,'intakeoutputoffset','integer'),
('intakeoutput',3,'intakeoutputentryoffset','integer'),
('intakeoutput',4,'cellpath','text'),
('intakeoutput',5,'celllabel','text'),
('intakeoutput',6,'cellvaluenumeric','numeric'),
('pasthistory',1,'patientunitstayid','integer'),
('pasthistory',2,'pasthistoryoffset','integer'),
('pasthistory',3,'pasthistoryenteredoffset','integer'),
('pasthistory',4,'pasthistorypath','text'),
('pasthistory',5,'pasthistoryvalue','text'),
('pasthistory',6,'pasthistoryvaluetext','text'),
('respiratorycare',1,'patientunitstayid','integer'),
('respiratorycare',2,'respcarestatusoffset','integer'),
('respiratorycare',3,'airwaytype','text'),
('respiratorycare',4,'ventstartoffset','integer'),
('respiratorycare',5,'ventendoffset','integer'),
('respiratorycharting',1,'patientunitstayid','integer'),
('respiratorycharting',2,'respchartoffset','integer'),
('respiratorycharting',3,'respchartentryoffset','integer'),
('respiratorycharting',4,'respcharttypecat','text'),
('respiratorycharting',5,'respchartvaluelabel','text'),
('respiratorycharting',6,'respchartvalue','text'),
('vitalperiodic',1,'patientunitstayid','integer'),
('vitalperiodic',2,'observationoffset','integer'),
('vitalperiodic',3,'systemicmean','real'),
('vitalaperiodic',1,'patientunitstayid','integer'),
('vitalaperiodic',2,'observationoffset','integer'),
('vitalaperiodic',3,'noninvasivemean','real'),
('apachepredvar',1,'patientunitstayid','integer'),
('apachepredvar',2,'apachepredvarid','integer'),
('apachepredvar',3,'sicuday','numeric'),
('apachepredvar',4,'ventday1','numeric'),
('apachepredvar',5,'oobventday1','numeric'),
('apachepredvar',6,'oobintubday1','numeric'),
('apacheapsvar',1,'patientunitstayid','integer'),
('apacheapsvar',2,'apacheapsvarid','integer'),
('apacheapsvar',3,'intubated','numeric'),
('apacheapsvar',4,'vent','numeric'),
('apacheapsvar',5,'urine','numeric'),
('treatment',1,'patientunitstayid','integer'),
('treatment',2,'treatmentid','integer'),
('treatment',3,'treatmentoffset','integer'),
('treatment',4,'treatmentstring','text'),
('careplangeneral',1,'patientunitstayid','integer'),
('careplangeneral',2,'cplgeneralid','integer'),
('careplangeneral',3,'cplitemoffset','integer'),
('careplangeneral',4,'cplgroup','text'),
('careplangeneral',5,'cplitemvalue','text');
CREATE TEMP TABLE ef_source_tables(table_name text PRIMARY KEY,qualified_name text,
 present boolean,has_stay_index boolean,missing_columns text[]);
DO $schema$
DECLARE schemas text[]; selected text; t record; f record; rid oid; cmap jsonb;
 expressions text; missing text[]; qualified text;
BEGIN
 SELECT source_schema INTO selected FROM ef_config;
 IF selected IS NULL THEN
  SELECT array_agg(n.nspname ORDER BY n.nspname) INTO schemas
  FROM pg_namespace n
  WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema'
   AND EXISTS(SELECT 1 FROM pg_class c WHERE c.relnamespace=n.oid AND lower(c.relname)='patient' AND c.relkind IN ('r','p','v','m'))
   AND EXISTS(SELECT 1 FROM pg_class c WHERE c.relnamespace=n.oid AND lower(c.relname)='nursecharting' AND c.relkind IN ('r','p','v','m'));
  IF coalesce(cardinality(schemas),0)<>1 THEN
   RAISE EXCEPTION 'Cannot uniquely identify eICU schema: %. Set source_schema in ef_config. Confirm this is the eICU database.',schemas;
  END IF;
  selected:=schemas[1];
 END IF;
 UPDATE ef_config SET source_schema=selected;
 FOR t IN SELECT DISTINCT table_name FROM ef_specs ORDER BY table_name LOOP
  SELECT c.oid,format('%I.%I',n.nspname,c.relname) INTO rid,qualified
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname=selected AND lower(c.relname)=t.table_name AND c.relkind IN ('r','p','v','m');
  IF rid IS NOT NULL THEN
   IF NOT has_table_privilege(rid,'SELECT') THEN RAISE EXCEPTION 'No SELECT access: %',qualified; END IF;
   IF EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=rid AND attnum>0 AND NOT attisdropped
      GROUP BY replace(lower(attname),'_','') HAVING count(*)>1) THEN
    RAISE EXCEPTION 'Ambiguous normalized columns in %',qualified;
   END IF;
   SELECT jsonb_object_agg(replace(lower(attname),'_',''),attname) INTO cmap
   FROM pg_attribute WHERE attrelid=rid AND attnum>0 AND NOT attisdropped;
  ELSE cmap:='{}'::jsonb;
  END IF;
  expressions:=''; missing:='{}';
  FOR f IN SELECT * FROM ef_specs WHERE table_name=t.table_name ORDER BY seq LOOP
   IF expressions<>'' THEN expressions:=expressions||','; END IF;
   IF cmap ? f.col_name THEN
    expressions:=expressions||format('%I AS %I',cmap->>f.col_name,f.col_name);
   ELSE
    expressions:=expressions||format('NULL::%s AS %I',f.col_type,f.col_name);
    missing:=array_append(missing,f.col_name);
   END IF;
  END LOOP;
  EXECUTE format('CREATE TEMP VIEW %I AS SELECT %s%s','ef_src_'||t.table_name,expressions,
   CASE WHEN rid IS NULL THEN ' WHERE false' ELSE ' FROM '||qualified END);
  INSERT INTO ef_source_tables
  SELECT t.table_name,qualified,rid IS NOT NULL,
   EXISTS(SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid
     AND a.attnum=i.indkey[0] WHERE i.indrelid=rid AND i.indisvalid
     AND replace(lower(a.attname),'_','')='patientunitstayid'),missing;
  INSERT INTO ef_status VALUES('source',t.table_name,
   CASE WHEN rid IS NULL THEN 'ABSENT' WHEN cardinality(missing)>0 THEN 'PARTIAL_COLUMNS' ELSE 'READY' END,
   coalesce(qualified,'No table in selected schema')||'; missing='||array_to_string(missing,','));
 END LOOP;
 IF EXISTS(SELECT 1 FROM ef_source_tables WHERE table_name='patient'
   AND (NOT present OR missing_columns && ARRAY['patientunitstayid','patienthealthsystemstayid','hospitalid','age','hospitaladmitoffset','unitdischargeoffset'])) THEN
  RAISE EXCEPTION 'patient is missing required eICU fields. See source schema; do not use a MIMIC patient table.';
 END IF;
 IF EXISTS(SELECT 1 FROM ef_source_tables WHERE table_name='diagnosis'
   AND (NOT present OR missing_columns && ARRAY['patientunitstayid','diagnosisoffset','diagnosisstring'])) THEN
  RAISE EXCEPTION 'diagnosis table/required columns missing; cannot identify the adapted clinical-sepsis cohort.';
 END IF;
 -- Fail before scans if server-side export is unavailable.
 EXECUTE format('COPY (SELECT %L AS run_id, %L AS status) TO %L WITH (FORMAT CSV, HEADER TRUE, ENCODING ''UTF8'')',
  (SELECT run_id FROM ef_config),'WRITE_PROBE_NOT_COMPLETION',
  (SELECT output_dir||'/'||run_id||'_write_probe.csv' FROM ef_config));
END $schema$;

-- END 00_setup.sql

-- BEGIN 10_population.sql

-- Entire eligible adult population; no hospital sampling and no row-count limit.
CREATE TEMP TABLE ef_patient AS
SELECT p.*,
 CASE WHEN trim(age) ~ '^[0-9]{1,3}$' THEN trim(age)::numeric
      WHEN trim(age) ~ '^>[ ]*89$' THEN 90::numeric END AS age_numeric,
 coalesce(trim(age) ~ '^>[ ]*89$',false) AS age_topcoded,
 dense_rank() OVER(PARTITION BY patienthealthsystemstayid
    ORDER BY hospitaladmitoffset DESC NULLS LAST) AS icu_time_rank,
 count(*) OVER(PARTITION BY patienthealthsystemstayid,hospitaladmitoffset) AS same_time_icu_stays
FROM ef_src_patient p;
CREATE UNIQUE INDEX ON ef_patient(patientunitstayid);
ANALYZE ef_patient;
CREATE TEMP TABLE ef_eligible_all AS
SELECT * FROM ef_patient WHERE age_numeric>=18 AND unitdischargeoffset>1440
 AND icu_time_rank=1 AND same_time_icu_stays=1 AND hospitaladmitoffset IS NOT NULL
 AND patienthealthsystemstayid IS NOT NULL;
CREATE UNIQUE INDEX ON ef_eligible_all(patientunitstayid);
ANALYZE ef_eligible_all;
CREATE TEMP TABLE ef_sample AS SELECT * FROM ef_eligible_all;
CREATE UNIQUE INDEX ON ef_sample(patientunitstayid);
ANALYZE ef_sample;
INSERT INTO ef_status VALUES('population','scope','FULL_POPULATION_NO_SAMPLING',
 'All adults with unambiguous first observed ICU stay per hospitalization, ICU stay >24h. No feature-completeness exclusion.');
INSERT INTO ef_report
SELECT 'population','hospital_'||p.hospitalid,jsonb_build_object(
 'hospital_id',p.hospitalid,'all_icu_stays',count(*),
 'eligible_adult_first_icu_over24h',count(e.patientunitstayid))
FROM ef_patient p LEFT JOIN ef_eligible_all e USING(patientunitstayid)
GROUP BY p.hospitalid;
DO $progress$ BEGIN
 RAISE NOTICE 'EICU_FULL_STAGE_10: % adult baseline candidates', (SELECT count(*) FROM ef_eligible_all);
END $progress$;

-- END 10_population.sql

-- BEGIN 15_clinical_sepsis.sql
-- Adapted cohort: documented clinical sepsis during ICU hours 0-24, landmark at hour24.
-- This is NOT reconstructed Sepsis-3 onset. Diagnosis offsets are documentation times.
-- Applied to the full adult candidate population before outcome extraction.
CREATE TEMP TABLE ef_diagnosis_flags AS
WITH raw AS (
 SELECT d.patientunitstayid,d.diagnosisoffset,d.diagnosisstring,d.icd9code,
  lower(coalesce(d.diagnosisstring,'')) AS txt,
  upper(coalesce(d.icd9code,'')) AS code
 FROM ef_src_diagnosis d JOIN ef_sample s USING(patientunitstayid)
), normalized AS (
 SELECT *,regexp_replace(txt,'\msepsis[[:space:]]+without[[:space:]]+(septic[[:space:]]+)?shock\M','sepsis','g') AS negation_txt
 FROM raw
), tagged AS (
 SELECT *,
  (txt ~ '\m(sepsis|septicemia|septicaemia)\M|\mseptic[[:space:]]+shock\M'
   OR code ~ '(^|[^[:alnum:]])(995[.]91|995[.]92|785[.]52)([^[:alnum:].]|$)') AS sepsis_candidate,
  (txt ~ '\m(pregnant|pregnancy|obstetric|obstetrical)\M|\mlabo(u)?r[[:space:]&/+-]+(and[[:space:]]+)?delivery\M'
   OR code ~ '(^|[^[:alnum:]])(6[3-7][0-9]([.][0-9]+)?|V2[23]([.][0-9]+)?)([^[:alnum:].]|$)') AS pregnancy_candidate,
  (negation_txt ~ '\m(no|not|without|denies|denied|negative[[:space:]]+for|possible|probable|suspected|suspect|suspecting|unlikely|rule[d]?[[:space:]-]+out|r[[:space:]]*/[[:space:]]*o)[[:space:][:punct:]]+(severe[[:space:]]+)?(sepsis|septicemia|septicaemia|septic[[:space:]]+shock)\M|\m(sepsis|septicemia|septicaemia|septic[[:space:]]+shock)[[:space:][:punct:]]+(ruled[[:space:]]+out|excluded|not[[:space:]]+(present|confirmed)|suspected|possible|probable)\M|[?]') AS sepsis_negated_or_uncertain,
  (txt ~ '\m(no|not|without|denies|denied|negative[[:space:]]+for|possible|probable|suspected|suspect|unlikely|rule[d]?[[:space:]-]+out)[[:space:][:punct:]]+(pregnancy|pregnant|obstetric|obstetrical)\M|\m(pregnancy|pregnant)[[:space:][:punct:]]+(ruled[[:space:]]+out|excluded|not[[:space:]]+(present|confirmed)|suspected|possible|probable)\M|[?]') AS pregnancy_negated_or_uncertain,
  (txt ~ '\m(history[[:space:]]+of|prior|previous|remote|resolved)\M') AS historical_or_resolved
 FROM normalized
)
SELECT *,sepsis_negated_or_uncertain OR pregnancy_negated_or_uncertain AS negated_or_uncertain,
 coalesce(diagnosisoffset BETWEEN 0 AND 1440,false) AS in_first24h,
 coalesce(diagnosisoffset BETWEEN 0 AND 1440,false) AND sepsis_candidate
  AND NOT sepsis_negated_or_uncertain AND NOT historical_or_resolved AS eligible_sepsis,
 coalesce(diagnosisoffset<=1440,false) AND pregnancy_candidate
  AND NOT pregnancy_negated_or_uncertain AND NOT historical_or_resolved AS pregnancy_exclusion
FROM tagged;
CREATE INDEX ON ef_diagnosis_flags(patientunitstayid);
ANALYZE ef_diagnosis_flags;

CREATE TEMP TABLE ef_timing_patient AS
SELECT s.patientunitstayid,
 count(d.patientunitstayid) AS diagnosis_rows,
 count(*) FILTER(WHERE d.in_first24h) AS first24h_diagnosis_rows,
 count(*) FILTER(WHERE d.in_first24h AND d.sepsis_candidate) AS first24h_sepsis_candidate_rows,
 count(*) FILTER(WHERE d.in_first24h AND d.sepsis_candidate AND d.sepsis_negated_or_uncertain) AS uncertain_sepsis_rows,
 count(*) FILTER(WHERE d.in_first24h AND d.sepsis_candidate AND d.historical_or_resolved) AS historical_sepsis_rows,
 coalesce(bool_or(d.eligible_sepsis),false) AS documented_clinical_sepsis,
 min(d.diagnosisoffset) FILTER(WHERE d.eligible_sepsis) AS first_documented_sepsis_offset,
 coalesce(bool_or(d.pregnancy_exclusion),false) AS pregnancy_exclusion,
 count(*) FILTER(WHERE d.pregnancy_candidate AND d.diagnosisoffset<=1440) AS pregnancy_candidate_rows,
 CASE WHEN bool_or(d.eligible_sepsis) THEN 'DOCUMENTED_CLINICAL_SEPSIS'
  WHEN count(*) FILTER(WHERE d.in_first24h)=0 THEN 'UNKNOWN_NO_FIRST24H_DIAGNOSIS'
  WHEN bool_or(d.in_first24h AND d.sepsis_candidate) THEN 'NOT_SELECTED_UNCERTAIN_OR_HISTORICAL_SEPSIS'
  ELSE 'NOT_SELECTED_NO_DOCUMENTED_SEPSIS' END::text AS clinical_sepsis_status
FROM ef_sample s LEFT JOIN ef_diagnosis_flags d USING(patientunitstayid)
GROUP BY s.patientunitstayid;
ALTER TABLE ef_timing_patient ADD PRIMARY KEY(patientunitstayid);

CREATE TEMP TABLE ef_index(
 patientunitstayid bigint PRIMARY KEY,t0_offset numeric,definition_id text
);
INSERT INTO ef_index
SELECT s.patientunitstayid,1440::numeric,'EICU_CLINICAL_SEPSIS_24H_LANDMARK_V1'
FROM ef_sample s JOIN ef_timing_patient t USING(patientunitstayid)
WHERE t.documented_clinical_sepsis AND NOT t.pregnancy_exclusion
 AND s.unitdischargeoffset>1440;
ANALYZE ef_index;

CREATE TEMP TABLE ef_timing_dictionary AS
SELECT diagnosisstring,icd9code,sepsis_candidate,pregnancy_candidate,
 negated_or_uncertain,historical_or_resolved,
 count(*) AS diagnosis_rows,count(DISTINCT patientunitstayid) AS sampled_stays,
 count(*) FILTER(WHERE in_first24h) AS first24h_rows,
 count(*) FILTER(WHERE eligible_sepsis) AS eligible_sepsis_rows,
 count(*) FILTER(WHERE pregnancy_exclusion) AS pregnancy_exclusion_rows
FROM ef_diagnosis_flags
GROUP BY diagnosisstring,icd9code,sepsis_candidate,pregnancy_candidate,
 negated_or_uncertain,historical_or_resolved;
INSERT INTO ef_report
SELECT 'diagnosis_dictionary',row_number() OVER(ORDER BY diagnosisstring,icd9code)::text,to_jsonb(d)
FROM ef_timing_dictionary d;
INSERT INTO ef_report
SELECT 'timing_readiness',clinical_sepsis_status,jsonb_build_object(
 'status',clinical_sepsis_status,'sampled_stays',count(*),
 'pregnancy_excluded',count(*) FILTER(WHERE pregnancy_exclusion),
 'index_stays',count(i.patientunitstayid))
FROM ef_timing_patient t LEFT JOIN ef_index i USING(patientunitstayid)
GROUP BY clinical_sepsis_status;
INSERT INTO ef_report
SELECT 'timing_readiness','adapted_landmark_definition',jsonb_build_object(
 't0_offset_minutes',1440,'definition_id','EICU_CLINICAL_SEPSIS_24H_LANDMARK_V1',
 'sampled_stays',(SELECT count(*) FROM ef_sample),'selected_stays',(SELECT count(*) FROM ef_index),
 'pregnancy_excluded_stays',count(*) FILTER(WHERE pregnancy_exclusion),
 'strict_original_sepsis3_onset_status','NOT_RECONSTRUCTED',
 'strict_original_sepsis3_onset_stays',NULL,
 'note','Diagnosis documentation in ICU[0,1440]min; t0 is fixed1440min, not diagnosisoffset. No later diagnosis selects the cohort. Missing diagnosis is unknown; no pregnancy record does not prove non-pregnancy. Regex negation/history flags are conservative candidates for dictionary review.')
FROM ef_timing_patient;
INSERT INTO ef_status VALUES
('timing','ef_index','ADAPTED_READY','Clinical sepsis recorded by ICU24h; fixed24h landmark; documented pregnancy candidates excluded. First24h diagnosis absent = UNKNOWN.'),
('timing','original_sepsis3_onset','NOT_RECONSTRUCTED','Original diagnosis_time generation SQL is unavailable; no strict Sepsis-3 onset is asserted or substituted with a first SOFA>=2 or diagnosisoffset.');

-- END 15_clinical_sepsis.sql

-- BEGIN 18_limit_assessment_scope.sql

-- Scope large assessment scans to all baseline-eligible clinical-sepsis stays.
-- Every rejected adult remains represented in ef_timing_patient/summary counts.
ALTER TABLE ef_sample RENAME TO ef_initial_sample;
CREATE TEMP TABLE ef_sample AS
SELECT s.* FROM ef_initial_sample s JOIN ef_index i USING(patientunitstayid);
CREATE UNIQUE INDEX ON ef_sample(patientunitstayid);
ANALYZE ef_sample;
DO $progress$ BEGIN
 RAISE NOTICE 'EICU_FULL_STAGE_18: % clinical-sepsis stays; starting CAM/RASS extraction',
  (SELECT count(*) FROM ef_index);
END $progress$;

-- END 18_limit_assessment_scope.sql

-- BEGIN 20_cam_rass.sql
-- eICU-CRD 2.0: full eligible clinical-sepsis cohort, fixed ICU24h landmark.
-- Requires ef_sample, ef_src_nursecharting, ef_src_nurseassessment, ef_status, ef_report.
-- No t0 is inferred here. Offsets are ICU-relative minutes.
-- Mapping v2: the original standard scale/score paths plus one exact observed
-- actual RASS path. CAM classification is unchanged; other aliases stay audit-only.
-- Official v2.0 schema: https://eicu.mit.edu/eicutables/nursecharting/
-- Official tutorial: https://eicu.mit.edu/tutorials/nursecharting/
-- The schema defines the three path fields and actual/entry minute offsets;
-- it does not publish a universal direct-RASS alias list. The exact added path
-- is supported by this run's observed dictionary, not by a claim of official
-- universal synonym equivalence: 20261020_161448_804911_38700_feasibility_summary.csv,
-- cam_label_dictionary item 6: Other Vital Signs and Infusions / RASS / Value,
-- 4561 rows, 119 stays, 6 hospitals; its 10 values are integer scores -5 through 4.
-- Goals, free text and other unverified aliases are not actual assessable RASS.
-- Do not replace unknown tools/results with CAM, ICDSC, diagnoses, or medications.
-- Source URLs and the observed dictionary provenance are recorded above.
-- Adapted 24h landmark: requested candidate range [-1440,11580] minutes.
-- 11520 is 24h + 7 days; the extra 60min permits the prespecified RASS pairing.

-- Each large source is referenced once and restricted to ef_sample (the full
-- clinical-sepsis ef_index population at this stage). Later work reads TEMP only.
ANALYZE ef_sample;
ANALYZE ef_index;

CREATE TEMP TABLE ef_assessment_candidates AS
WITH raw AS (
 SELECT 'nursecharting'::text AS source_table,s.patientunitstayid,s.hospitalid,
        n.nursingchartoffset::numeric AS chartoffset,
        n.nursingchartentryoffset::numeric AS entryoffset,
        n.nursingchartcelltypecat::text AS label_category,
        n.nursingchartcelltypevallabel::text AS label_name,
        n.nursingchartcelltypevalname::text AS label_attribute,
        n.nursingchartvalue::text AS raw_value,
        (n.nursingchartoffset>=0 AND n.nursingchartoffset<=s.unitdischargeoffset) AS within_icu
 FROM ef_sample s JOIN ef_src_nursecharting n USING(patientunitstayid)
 WHERE n.nursingchartoffset BETWEEN -1440 AND 11580
   AND concat_ws(' ',n.nursingchartcelltypecat,n.nursingchartcelltypevallabel,
                   n.nursingchartcelltypevalname,n.nursingchartvalue)
       ~* '(deliri|cam[-_ ]?icu|icdsc|confusion assessment|rass|richmond|sedation)'
 UNION ALL
 SELECT 'nurseassessment',s.patientunitstayid,s.hospitalid,
        n.nurseassessoffset::numeric,n.nurseassessentryoffset::numeric,
        n.cellattributepath::text,n.celllabel::text,n.cellattribute::text,n.cellattributevalue::text,
        (n.nurseassessoffset>=0 AND n.nurseassessoffset<=s.unitdischargeoffset)
 FROM ef_sample s JOIN ef_src_nurseassessment n USING(patientunitstayid)
 WHERE n.nurseassessoffset BETWEEN -1440 AND 11580
   AND concat_ws(' ',n.cellattributepath,n.celllabel,n.cellattribute,n.cellattributevalue)
       ~* '(deliri|cam[-_ ]?icu|icdsc|confusion assessment|rass|richmond|sedation)'
), normalized AS (
 SELECT *,
        lower(regexp_replace(btrim(coalesce(label_category,'')),'[[:space:]]+',' ','g')) AS category_norm,
        lower(regexp_replace(btrim(coalesce(label_name,'')),'[[:space:]]+',' ','g')) AS label_norm,
        lower(regexp_replace(btrim(coalesce(label_attribute,'')),'[[:space:]]+',' ','g')) AS attribute_norm,
        lower(regexp_replace(btrim(coalesce(raw_value,'')),'[[:space:]]+',' ','g')) AS value_norm
 FROM raw
)
SELECT *,
 CASE
  WHEN source_table='nursecharting' AND category_norm='scores'
   AND label_norm='delirium scale/score' AND attribute_norm='delirium scale' THEN 'cam_instrument'
  WHEN source_table='nursecharting' AND category_norm='scores'
   AND label_norm='delirium scale/score' AND attribute_norm='delirium score' THEN 'cam_result'
  WHEN source_table='nursecharting' AND category_norm='scores'
   AND label_norm='sedation scale/score/goal' AND attribute_norm='sedation scale' THEN 'sedation_instrument'
  WHEN source_table='nursecharting' AND category_norm='scores'
   AND label_norm='sedation scale/score/goal' AND attribute_norm='sedation score' THEN 'sedation_result'
  WHEN source_table='nursecharting' AND category_norm='scores'
   AND label_norm='sedation scale/score/goal' AND attribute_norm='sedation goal' THEN 'sedation_goal_excluded'
  WHEN source_table='nursecharting' AND category_norm='other vital signs and infusions'
   AND label_norm='rass' AND attribute_norm='value' THEN 'direct_rass_actual'
  WHEN concat_ws(' ',label_category,label_name,label_attribute) ~* 'icdsc' THEN 'icdsc_label_audit_only'
  WHEN concat_ws(' ',label_category,label_name,label_attribute) ~* 'cam[-_ ]?icu|confusion assessment'
       THEN 'cam_specific_label_audit_only'
  WHEN concat_ws(' ',label_category,label_name,label_attribute) ~* 'rass|richmond'
       THEN 'rass_specific_label_audit_only'
  ELSE 'other_candidate_audit_only'
 END::text AS mapping_role,
 CASE regexp_replace(value_norm,'[^a-z0-9]','','g')
  WHEN 'camicu' THEN 'cam_icu'
  WHEN 'icdsc' THEN 'icdsc'
  WHEN 'rass' THEN 'rass'
  WHEN 'richmondagitationsedationscale' THEN 'rass'
  WHEN 'richmondagitationsedationscalerass' THEN 'rass'
  ELSE coalesce(nullif(value_norm,''),'<empty>')
 END::text AS instrument_value,
 -- Use only the explicitly documented Yes/No CAM values in this feasibility pass.
 CASE WHEN value_norm='yes' THEN 1 WHEN value_norm='no' THEN 0 END::smallint AS yes_no_result,
 CASE WHEN translate(value_norm,chr(8722),'-') ~ '^[+-]?[0-9]{1,2}([.]0+)?$'
      THEN translate(value_norm,chr(8722),'-')::numeric END AS numeric_integer_candidate
FROM normalized;
CREATE INDEX ON ef_assessment_candidates(patientunitstayid,chartoffset);
ANALYZE ef_assessment_candidates;

-- Label-level dictionary retains every observed label, including unmapped paths.
CREATE TEMP TABLE ef_cam_label_audit AS
SELECT source_table,mapping_role,label_category,label_name,label_attribute,
       count(*) AS n_records,count(DISTINCT patientunitstayid) AS n_stays,
       count(DISTINCT hospitalid) AS n_hospitals,count(DISTINCT raw_value) AS n_distinct_raw_values,
       count(*) FILTER(WHERE raw_value IS NULL) AS n_null_values,
       count(*) FILTER(WHERE within_icu IS TRUE) AS n_within_icu,
       count(*) FILTER(WHERE entryoffset IS DISTINCT FROM chartoffset) AS n_entry_time_differs,
       min(chartoffset) AS first_offset_min,max(chartoffset) AS last_offset_min
FROM ef_assessment_candidates
GROUP BY source_table,mapping_role,label_category,label_name,label_attribute;

-- All raw value frequencies stay in TEMP; the export-sized audit retains at most
-- 20 common raw values per label, with totals making truncation explicit.
CREATE TEMP TABLE ef_cam_value_frequencies AS
SELECT source_table,mapping_role,label_category,label_name,label_attribute,raw_value,
       count(*) AS n_records,count(DISTINCT patientunitstayid) AS n_stays,
       count(DISTINCT hospitalid) AS n_hospitals
FROM ef_assessment_candidates
GROUP BY source_table,mapping_role,label_category,label_name,label_attribute,raw_value;
CREATE TEMP TABLE ef_cam_value_audit AS
WITH ranked AS (
 SELECT *,row_number() OVER(
   PARTITION BY source_table,mapping_role,label_category,label_name,label_attribute
   ORDER BY n_records DESC,raw_value NULLS FIRST) AS value_rank,
   count(*) OVER(PARTITION BY source_table,mapping_role,label_category,label_name,label_attribute)
      AS total_value_variants,
   sum(n_records) OVER(PARTITION BY source_table,mapping_role,label_category,label_name,label_attribute)
      AS total_label_records
 FROM ef_cam_value_frequencies
)
SELECT *,(total_value_variants>20) AS additional_values_in_temp_frequency_table
FROM ranked WHERE value_rank<=20;

-- One row per ICU stay + actual chart offset: no raw instrument/result join.
-- Repeated identical values are harmless; differing entries at the same offset
-- remain conflicting rather than selecting MAX or the latest entry.
CREATE TEMP TABLE ef_cam_timepoints AS
WITH grouped AS (
 SELECT patientunitstayid,hospitalid,chartoffset,bool_and(within_icu) AS within_icu,
        count(*) AS n_source_rows,
        count(*) FILTER(WHERE mapping_role='cam_instrument') AS n_instrument_rows,
        count(*) FILTER(WHERE mapping_role='cam_result') AS n_result_rows,
        count(DISTINCT instrument_value) FILTER(WHERE mapping_role='cam_instrument') AS n_instrument_values,
        array_agg(DISTINCT instrument_value ORDER BY instrument_value)
          FILTER(WHERE mapping_role='cam_instrument') AS instrument_values,
        count(DISTINCT value_norm) FILTER(WHERE mapping_role='cam_result') AS n_result_values,
        array_agg(DISTINCT value_norm ORDER BY value_norm)
          FILTER(WHERE mapping_role='cam_result') AS result_values,
        min(yes_no_result) FILTER(WHERE mapping_role='cam_result') AS parsed_yes_no,
        count(*) FILTER(WHERE mapping_role='cam_result' AND yes_no_result IS NULL) AS n_unknown_result_rows,
        min(entryoffset) AS first_entryoffset,max(entryoffset) AS last_entryoffset,
        count(DISTINCT entryoffset) AS n_distinct_entry_offsets
 FROM ef_assessment_candidates WHERE mapping_role IN('cam_instrument','cam_result')
 GROUP BY patientunitstayid,hospitalid,chartoffset
), classified AS (
 SELECT *,
  CASE WHEN within_icu IS NOT TRUE THEN 'outside_icu_or_unknown_time'
       WHEN n_instrument_rows=0 THEN 'missing_instrument'
       WHEN n_instrument_values<>1 THEN 'conflicting_instruments'
       WHEN instrument_values<>ARRAY['cam_icu']::text[] THEN 'non_cam_or_unknown_instrument'
       WHEN n_result_rows=0 THEN 'missing_result'
       WHEN n_result_values<>1 THEN 'conflicting_results'
       WHEN n_unknown_result_rows>0 THEN 'unrecognized_or_unassessable_result'
       WHEN parsed_yes_no=1 THEN 'valid_cam_positive'
       WHEN parsed_yes_no=0 THEN 'valid_cam_negative'
       ELSE 'unrecognized_or_unassessable_result'
  END::text AS cam_status
 FROM grouped
)
SELECT *,CASE WHEN cam_status IN('valid_cam_positive','valid_cam_negative')
              THEN parsed_yes_no END::smallint AS cam_result
FROM classified;
CREATE UNIQUE INDEX ON ef_cam_timepoints(patientunitstayid,chartoffset);
ANALYZE ef_cam_timepoints;

-- Sedation Score is NOT automatically RASS. Require a unique RASS instrument.
-- Sedation Goal is never included. Integer-valued decimals such as -3.0 are
-- accepted; prose, NaN, non-integers and values outside [-5,4] remain unknown.


-- Normalize the single exact direct-RASS label into an instrument row and a
-- score row at the same actual chartoffset. This does not duplicate CAM rows.
-- A direct invalid/missing score still establishes that a RASS observation
-- exists, so it cannot be mistaken for no RASS in the relaxed sensitivity.
-- Standard and direct rows at the same time undergo the same conflict rules:
-- contradictory tools/scores or any invalid score make the timepoint unknown.
-- The synthetic normalized rows are internal only; dictionary counts above
-- continue to describe actual source rows, without double-counting.
CREATE TEMP TABLE ef_rass_source_rows_v2 AS
SELECT patientunitstayid,hospitalid,chartoffset,within_icu,mapping_role,
       instrument_value,numeric_integer_candidate,value_norm,entryoffset
FROM ef_assessment_candidates
WHERE mapping_role IN('sedation_instrument','sedation_result')
UNION ALL
SELECT a.patientunitstayid,a.hospitalid,a.chartoffset,a.within_icu,r.mapping_role,
       'rass'::text,a.numeric_integer_candidate,a.value_norm,a.entryoffset
FROM ef_assessment_candidates a
CROSS JOIN (VALUES('sedation_instrument'::text),('sedation_result'::text)) r(mapping_role)
WHERE a.mapping_role='direct_rass_actual';
ANALYZE ef_rass_source_rows_v2;

CREATE TEMP TABLE ef_rass_timepoints AS
WITH grouped AS (
 SELECT patientunitstayid,hospitalid,chartoffset,bool_and(within_icu) AS within_icu,
        count(*) AS n_source_rows,
        count(*) FILTER(WHERE mapping_role='sedation_instrument') AS n_instrument_rows,
        count(*) FILTER(WHERE mapping_role='sedation_result') AS n_score_rows,
        count(DISTINCT instrument_value) FILTER(WHERE mapping_role='sedation_instrument') AS n_instrument_values,
        array_agg(DISTINCT instrument_value ORDER BY instrument_value)
          FILTER(WHERE mapping_role='sedation_instrument') AS instrument_values,
        bool_or(instrument_value='rass') FILTER(WHERE mapping_role='sedation_instrument') AS has_rass_tool,
        count(DISTINCT numeric_integer_candidate)
          FILTER(WHERE mapping_role='sedation_result' AND numeric_integer_candidate BETWEEN -5 AND 4)
          AS n_valid_score_values,
        min(numeric_integer_candidate)
          FILTER(WHERE mapping_role='sedation_result' AND numeric_integer_candidate BETWEEN -5 AND 4)
          AS parsed_rass,
        count(*) FILTER(WHERE mapping_role='sedation_result'
          AND (numeric_integer_candidate IS NULL OR numeric_integer_candidate NOT BETWEEN -5 AND 4))
          AS n_invalid_score_rows,
        array_agg(DISTINCT value_norm ORDER BY value_norm)
          FILTER(WHERE mapping_role='sedation_result') AS score_values,
        min(entryoffset) AS first_entryoffset,max(entryoffset) AS last_entryoffset
 FROM ef_rass_source_rows_v2 WHERE mapping_role IN('sedation_instrument','sedation_result')
 GROUP BY patientunitstayid,hospitalid,chartoffset
), classified AS (
 SELECT *,
  CASE WHEN within_icu IS NOT TRUE THEN 'outside_icu_or_unknown_time'
       WHEN n_instrument_rows=0 THEN 'missing_instrument'
       WHEN n_instrument_values<>1 THEN 'conflicting_instruments'
       WHEN instrument_values<>ARRAY['rass']::text[] THEN 'non_rass_or_unknown_instrument'
       WHEN n_score_rows=0 THEN 'missing_score'
       WHEN n_valid_score_values>1 THEN 'conflicting_scores'
       WHEN n_invalid_score_rows>0 OR n_valid_score_values=0 THEN 'invalid_or_unknown_score'
       ELSE 'valid_rass'
  END::text AS rass_status
 FROM grouped
)
SELECT *,CASE WHEN rass_status='valid_rass' THEN parsed_rass END::smallint AS rass_value
FROM classified;
CREATE UNIQUE INDEX ON ef_rass_timepoints(patientunitstayid,chartoffset);
ANALYZE ef_rass_timepoints;

-- Indexed, bounded +/-60-minute lookup against the sampled RASS timepoints.
-- At an equal nearest distance, different scores or any ambiguous timepoint
-- yield UNKNOWN. We do not choose the more convenient/lighter score.
-- Every explicitly RASS-tagged timepoint participates, even when its score is
-- missing, nonnumeric, out of range or conflicting. A nearer invalid record
-- must not be skipped in favor of a more distant clean value, or relabelled
-- "missing RASS" and admitted by the missing-RASS sensitivity analysis.


-- Active v2 pairing; standard CAM parsing and +/-60-minute rules are unchanged.
CREATE TEMP TABLE ef_cam_rass AS
WITH linked AS (
 SELECT c.*,r.nearest_distance_min,r.nearest_first_offset,r.nearest_last_offset,
        r.n_nearest_timepoints,r.n_nearest_valid_values,r.nearest_has_ambiguity,
        r.nearest_parsed_value,r.nearest_first_entryoffset,r.nearest_last_entryoffset
 FROM ef_cam_timepoints c
 LEFT JOIN LATERAL (
  SELECT min(x.distance_min) AS nearest_distance_min,
         min(x.chartoffset) AS nearest_first_offset,max(x.chartoffset) AS nearest_last_offset,
         count(*) AS n_nearest_timepoints,
         count(DISTINCT x.rass_value) AS n_nearest_valid_values,
         bool_or(x.rass_value IS NULL) AS nearest_has_ambiguity,
         min(x.rass_value) AS nearest_parsed_value,
         min(x.first_entryoffset) AS nearest_first_entryoffset,
         max(x.last_entryoffset) AS nearest_last_entryoffset
  FROM (
   SELECT r.*,abs(r.chartoffset-c.chartoffset) AS distance_min,
          dense_rank() OVER(ORDER BY abs(r.chartoffset-c.chartoffset)) AS proximity_rank
   FROM ef_rass_timepoints r
   WHERE r.patientunitstayid=c.patientunitstayid
     AND r.chartoffset BETWEEN c.chartoffset-60 AND c.chartoffset+60
     AND r.within_icu IS TRUE AND r.has_rass_tool IS TRUE
  ) x WHERE x.proximity_rank=1
 ) r ON true
), classified AS (
 SELECT *,
  CASE WHEN cam_result IS NULL THEN 'unknown_cam_'||cam_status
       WHEN n_nearest_timepoints=0 THEN 'unknown_missing_valid_rass_within_60min'
       WHEN nearest_has_ambiguity IS TRUE OR n_nearest_valid_values<>1 THEN 'unknown_ambiguous_nearest_rass'
       WHEN nearest_parsed_value < -3 THEN 'unassessable_rass_below_minus3'
       WHEN cam_result=1 THEN 'strict_cam_positive'
       ELSE 'strict_cam_negative'
  END::text AS assessment_status
 FROM linked
)
SELECT *,
 CASE WHEN n_nearest_valid_values=1 AND nearest_has_ambiguity IS FALSE
      THEN nearest_parsed_value END::smallint AS nearest_rass_value,
 CASE WHEN assessment_status IN('strict_cam_positive','strict_cam_negative')
      THEN cam_result END::smallint AS strict_cam_result,
 CASE WHEN assessment_status IN('strict_cam_positive','strict_cam_negative') THEN true
      WHEN assessment_status='unassessable_rass_below_minus3' THEN false
      ELSE NULL END::boolean AS strictly_assessable
FROM classified;
CREATE UNIQUE INDEX ON ef_cam_rass(patientunitstayid,chartoffset);
ANALYZE ef_cam_rass;

INSERT INTO ef_status(stage,object_name,status,detail)
SELECT '20_cam_rass','strict_cam_rass',
       CASE WHEN count(*) FILTER(WHERE strict_cam_result IS NOT NULL)>0
            THEN 'STRICT_ASSESSMENTS_FOUND' ELSE 'NO_STRICT_ASSESSMENTS_IN_COHORT' END,
       'ICU-relative timepoints='||count(*)||
       '; strict assessments='||(count(*) FILTER(WHERE strict_cam_result IS NOT NULL))||
       '; strict positive='||(count(*) FILTER(WHERE strict_cam_result=1))||
       '. Full clinical-sepsis candidate population; strict Sepsis-3 onset is not inferred.'
FROM ef_cam_rass;
INSERT INTO ef_status(stage,object_name,status,detail) VALUES
('20_cam_rass','mapping','RESTRICTED_VERIFIED_PATTERN',
 'CAM remains restricted to nursecharting Scores / Delirium Scale/Score, unique CAM-ICU plus Yes/No. RASS v2 additionally admits the exact Other Vital Signs and Infusions / RASS / Value path. ICDSC, nonspecific delirium symptoms and other aliases remain audit-only.'),
('20_cam_rass','rass_rule','STRICT_MISSINGNESS',
 'A unique RASS instrument with actual Sedation Score or the exact direct actual RASS path, integer [-5,4], is required. Nearest +/-60min; any same-time or nearest-distance conflict stays unknown. Goals and outside-ICU records are excluded.'),
('20_cam_rass','value_dictionary','TOP_20_PER_LABEL_FOR_EXPORT',
 'ef_cam_label_audit contains all candidate labels. ef_cam_value_audit keeps 20 common raw values per label and reports truncation. Full sampled frequencies remain in TEMP ef_cam_value_frequencies.');


-- Aggregate mapping provenance; v1 duplicate pairing is omitted in full extraction.
-- The v2 classification is unchanged. Raw clinical observations stay in TEMP
-- and are joined to the explicitly constructed outcomes in module30.
INSERT INTO ef_report(section,item,details)
SELECT 'cam_mapping_v2','definition',jsonb_build_object(
 'mapping_version','EICU_CAM_UNCHANGED_RASS_EXACT_DIRECT_V2',
 'legacy_rule_reference','standard Scores / Sedation Scale/Score/Goal only',
 'added_path','nursecharting / Other Vital Signs and Infusions / RASS / Value',
 'cam_rule_changed',false,
 'source_dictionary_run','20261020_161448_804911_38700',
 'schema_source','https://eicu.mit.edu/eicutables/nursecharting/',
 'note','Actual direct RASS only; goals/invalid scores not assessable. Raw dictionaries retained. Full extraction uses the tested v2 mapping without redundant v1 computations.');
INSERT INTO ef_report(section,item,details)
SELECT 'cam_mapping_v2','direct_rass_source',jsonb_build_object(
 'source_rows',count(*),'stays',count(DISTINCT patientunitstayid),
 'hospitals',count(DISTINCT hospitalid),
 'within_icu_rows',count(*) FILTER(WHERE within_icu IS TRUE),
 'valid_integer_rows',count(*) FILTER(WHERE within_icu IS TRUE AND numeric_integer_candidate BETWEEN -5 AND 4),
 'invalid_or_missing_value_rows',count(*) FILTER(WHERE within_icu IS TRUE
   AND (numeric_integer_candidate IS NULL OR numeric_integer_candidate NOT BETWEEN -5 AND 4)),
 'outside_icu_rows',count(*) FILTER(WHERE within_icu IS NOT TRUE))
FROM ef_assessment_candidates WHERE mapping_role='direct_rass_actual';

-- END 20_cam_rass.sql

-- BEGIN 30_outcomes.sql
-- Full extraction outcome construction; unchanged prespecified v2 definitions.
-- Run before restricting ef_sample to the union of evaluable outcome variants.
-- No feature-completeness filter and no outcome imputation are permitted here.
-- pre/post booleans describe observed evidence, not absence of disease;
-- ef_followup_audit exposes nullable outcomes and explicit unknown statuses.
CREATE TEMP TABLE ef_outcome AS
SELECT i.patientunitstayid,i.t0_offset,i.definition_id,s.hospitalid,
 coalesce(bool_or(c.strict_cam_result=1) FILTER(WHERE c.chartoffset>=i.t0_offset-1440 AND c.chartoffset<i.t0_offset),false) AS pre_positive,
 coalesce(bool_or(c.strict_cam_result=0) FILTER(WHERE c.chartoffset>=i.t0_offset-1440 AND c.chartoffset<i.t0_offset),false) AS pre_negative,
 coalesce(bool_or(c.strict_cam_result=1) FILTER(WHERE c.chartoffset>=i.t0_offset AND c.chartoffset<=i.t0_offset+10080),false) AS post_positive,
 coalesce(bool_or(c.strict_cam_result=0) FILTER(WHERE c.chartoffset>=i.t0_offset AND c.chartoffset<=i.t0_offset+10080),false) AS post_negative,
 count(*) FILTER(WHERE c.strict_cam_result IS NOT NULL AND c.chartoffset>=i.t0_offset AND c.chartoffset<=i.t0_offset+10080) AS post_valid_assessments,
 count(DISTINCT floor((c.chartoffset-i.t0_offset)/1440.0))
  FILTER(WHERE c.strict_cam_result IS NOT NULL AND c.chartoffset>=i.t0_offset AND c.chartoffset<=i.t0_offset+10080) AS assessed_followup_days,
 -- Sensitivity prespecified before seeing results: accept recorded CAM when
 -- no RASS-tagged timepoint is available; do NOT accept low/invalid/ambiguous RASS.
 coalesce(bool_or(c.cam_result=1 AND (c.strict_cam_result IS NOT NULL OR c.assessment_status='unknown_missing_valid_rass_within_60min'))
  FILTER(WHERE c.chartoffset>=i.t0_offset-1440 AND c.chartoffset<i.t0_offset),false) AS relaxed_pre_positive,
 coalesce(bool_or(c.cam_result=1 AND (c.strict_cam_result IS NOT NULL OR c.assessment_status='unknown_missing_valid_rass_within_60min'))
  FILTER(WHERE c.chartoffset>=i.t0_offset AND c.chartoffset<=i.t0_offset+10080),false) AS relaxed_post_positive,
 coalesce(bool_or(c.cam_result=0 AND (c.strict_cam_result IS NOT NULL OR c.assessment_status='unknown_missing_valid_rass_within_60min'))
  FILTER(WHERE c.chartoffset>=i.t0_offset AND c.chartoffset<=i.t0_offset+10080),false) AS relaxed_post_negative,
 least(s.unitdischargeoffset-i.t0_offset,10080) AS available_followup_minutes
FROM ef_index i JOIN ef_sample s USING(patientunitstayid)
LEFT JOIN ef_cam_rass c ON c.patientunitstayid=i.patientunitstayid
 AND c.chartoffset>=i.t0_offset-1440 AND c.chartoffset<=least(i.t0_offset+10080,s.unitdischargeoffset)
GROUP BY i.patientunitstayid,i.t0_offset,i.definition_id,s.hospitalid,s.unitdischargeoffset;
CREATE UNIQUE INDEX ON ef_outcome(patientunitstayid);
ANALYZE ef_outcome;
CREATE TEMP TABLE ef_analysis_cohort AS
SELECT patientunitstayid,hospitalid,'strict_rass'::text AS variant,
 CASE WHEN post_positive THEN 1 ELSE 0 END AS outcome
FROM ef_outcome WHERE NOT pre_positive AND (post_positive OR post_negative)
UNION ALL
SELECT patientunitstayid,hospitalid,'strict_rass_baseline_negative',
 CASE WHEN post_positive THEN 1 ELSE 0 END
FROM ef_outcome WHERE NOT pre_positive AND pre_negative AND (post_positive OR post_negative)
UNION ALL
SELECT patientunitstayid,hospitalid,'sensitivity_allow_missing_rass',
 CASE WHEN relaxed_post_positive THEN 1 ELSE 0 END
FROM ef_outcome WHERE NOT relaxed_pre_positive AND (relaxed_post_positive OR relaxed_post_negative);
CREATE UNIQUE INDEX ON ef_analysis_cohort(variant,patientunitstayid);
CREATE INDEX ON ef_analysis_cohort(patientunitstayid);
ANALYZE ef_analysis_cohort;

-- One row for EVERY clinical-sepsis landmark candidate, including no-assessment
-- cases and baseline positives. Restricting feature extraction later must not
-- remove these audit denominators. Strict/relaxed count only valid CAM results;
-- the relaxed rule admits absent RASS only, never low/invalid/conflicting RASS.
-- Follow-up CAM is in [t0,min(ICU discharge,t0+7d)], baseline in [t0-24h,t0).
-- Offset fields below are ICU-relative minutes. Gap fields are durations in minutes.
CREATE TEMP TABLE ef_followup_audit AS
WITH linked AS (
 SELECT o.patientunitstayid,o.t0_offset,
        o.t0_offset+o.available_followup_minutes AS followup_end_offset,
        o.available_followup_minutes,c.chartoffset,c.strict_cam_result,
        CASE WHEN c.strict_cam_result IS NOT NULL
               OR c.assessment_status='unknown_missing_valid_rass_within_60min'
             THEN c.cam_result END::smallint AS relaxed_cam_result
 FROM ef_outcome o
 LEFT JOIN ef_cam_rass c ON c.patientunitstayid=o.patientunitstayid
  AND c.chartoffset>=o.t0_offset-1440
  AND c.chartoffset<=o.t0_offset+o.available_followup_minutes
), counted AS (
 SELECT patientunitstayid,t0_offset,followup_end_offset,available_followup_minutes,
  min(chartoffset) FILTER(WHERE chartoffset>=t0_offset AND strict_cam_result=1) AS strict_first_positive_offset,
  min(chartoffset) FILTER(WHERE chartoffset>=t0_offset AND strict_cam_result IS NOT NULL) AS strict_first_valid_offset,
  max(chartoffset) FILTER(WHERE chartoffset>=t0_offset AND strict_cam_result IS NOT NULL) AS strict_last_valid_offset,
  max(chartoffset) FILTER(WHERE chartoffset>=t0_offset AND strict_cam_result=0) AS strict_last_negative_offset,
  count(*) FILTER(WHERE chartoffset>=t0_offset AND strict_cam_result IS NOT NULL) AS strict_valid_assessments,
  count(*) FILTER(WHERE chartoffset>=t0_offset AND strict_cam_result=1) AS strict_positive_assessments,
  count(*) FILTER(WHERE chartoffset>=t0_offset AND strict_cam_result=0) AS strict_negative_assessments,
  count(*) FILTER(WHERE chartoffset<t0_offset AND strict_cam_result IS NOT NULL) AS strict_baseline_valid_assessments,
  count(*) FILTER(WHERE chartoffset<t0_offset AND strict_cam_result=1) AS strict_baseline_positive_assessments,
  count(*) FILTER(WHERE chartoffset<t0_offset AND strict_cam_result=0) AS strict_baseline_negative_assessments,
  min(chartoffset) FILTER(WHERE chartoffset<t0_offset AND strict_cam_result=1) AS strict_baseline_first_positive_offset,
  max(chartoffset) FILTER(WHERE chartoffset<t0_offset AND strict_cam_result IS NOT NULL) AS strict_baseline_last_valid_offset,
  min(chartoffset) FILTER(WHERE chartoffset>=t0_offset AND relaxed_cam_result=1) AS relaxed_first_positive_offset,
  min(chartoffset) FILTER(WHERE chartoffset>=t0_offset AND relaxed_cam_result IS NOT NULL) AS relaxed_first_valid_offset,
  max(chartoffset) FILTER(WHERE chartoffset>=t0_offset AND relaxed_cam_result IS NOT NULL) AS relaxed_last_valid_offset,
  max(chartoffset) FILTER(WHERE chartoffset>=t0_offset AND relaxed_cam_result=0) AS relaxed_last_negative_offset,
  count(*) FILTER(WHERE chartoffset>=t0_offset AND relaxed_cam_result IS NOT NULL) AS relaxed_valid_assessments,
  count(*) FILTER(WHERE chartoffset>=t0_offset AND relaxed_cam_result=1) AS relaxed_positive_assessments,
  count(*) FILTER(WHERE chartoffset>=t0_offset AND relaxed_cam_result=0) AS relaxed_negative_assessments,
  count(*) FILTER(WHERE chartoffset<t0_offset AND relaxed_cam_result IS NOT NULL) AS relaxed_baseline_valid_assessments,
  count(*) FILTER(WHERE chartoffset<t0_offset AND relaxed_cam_result=1) AS relaxed_baseline_positive_assessments,
  count(*) FILTER(WHERE chartoffset<t0_offset AND relaxed_cam_result=0) AS relaxed_baseline_negative_assessments,
  min(chartoffset) FILTER(WHERE chartoffset<t0_offset AND relaxed_cam_result=1) AS relaxed_baseline_first_positive_offset,
  max(chartoffset) FILTER(WHERE chartoffset<t0_offset AND relaxed_cam_result IS NOT NULL) AS relaxed_baseline_last_valid_offset
 FROM linked
 GROUP BY patientunitstayid,t0_offset,followup_end_offset,available_followup_minutes
)
SELECT *,
 followup_end_offset-strict_last_valid_offset AS strict_last_assessment_to_end_minutes,
 CASE WHEN strict_baseline_positive_assessments>0 THEN 'observed_positive'
      WHEN strict_baseline_negative_assessments>0 THEN 'observed_negative_without_positive'
      ELSE 'unknown_no_valid_assessment' END::text AS strict_baseline_status,
 CASE WHEN strict_positive_assessments>0 THEN 'observed_positive'
      WHEN strict_negative_assessments>0 THEN 'observed_negative_without_positive'
      ELSE 'unknown_no_valid_assessment' END::text AS strict_followup_status,
 CASE WHEN strict_positive_assessments>0 THEN 1
      WHEN strict_negative_assessments>0 THEN 0 END::smallint AS strict_outcome,
 followup_end_offset-relaxed_last_valid_offset AS relaxed_last_assessment_to_end_minutes,
 CASE WHEN relaxed_baseline_positive_assessments>0 THEN 'observed_positive'
      WHEN relaxed_baseline_negative_assessments>0 THEN 'observed_negative_without_positive'
      ELSE 'unknown_no_valid_assessment' END::text AS relaxed_baseline_status,
 CASE WHEN relaxed_positive_assessments>0 THEN 'observed_positive'
      WHEN relaxed_negative_assessments>0 THEN 'observed_negative_without_positive'
      ELSE 'unknown_no_valid_assessment' END::text AS relaxed_followup_status,
 CASE WHEN relaxed_positive_assessments>0 THEN 1
      WHEN relaxed_negative_assessments>0 THEN 0 END::smallint AS relaxed_outcome
FROM counted;
CREATE UNIQUE INDEX ON ef_followup_audit(patientunitstayid);
ANALYZE ef_followup_audit;

INSERT INTO ef_status(stage,object_name,status,detail) VALUES
('outcomes','definition','ADAPTED_CLINICAL_SEPSIS_24H',
 'Clinical sepsis documented by ICU24h, fixed t0=1440min, observed subsequent CAM through ICU discharge or7days. Three prespecified variants; no assessment stays unknown, no feature-completeness restriction.'),
('outcomes','followup_audit','PATIENT_LEVEL_TIMED_OBSERVATION_AUDIT',
 'Every clinical-sepsis candidate retained: strict/relaxed baseline and follow-up counts, first positive and last valid assessment, end offset and gap. Recorded negative does not establish continuous seven-day surveillance.');

-- END 30_outcomes.sql

-- BEGIN 35_limit_feature_scope.sql

-- Fetch detailed predictors only after endpoint eligibility is established.
-- The full clinical-sepsis screening/outcome tables remain available for export.
ALTER TABLE ef_sample RENAME TO ef_clinical_sample;
CREATE TEMP TABLE ef_sample AS
SELECT s.* FROM ef_clinical_sample s
WHERE EXISTS(SELECT 1 FROM ef_analysis_cohort c WHERE c.patientunitstayid=s.patientunitstayid);
CREATE UNIQUE INDEX ON ef_sample(patientunitstayid);
ANALYZE ef_sample;
DO $progress$ BEGIN
 RAISE NOTICE 'EICU_FULL_STAGE_35: % distinct evaluable stays; starting predictors',
  (SELECT count(*) FROM ef_sample);
END $progress$;

-- END 35_limit_feature_scope.sql

-- BEGIN 40_features.sql
-- Raw un-imputed feature candidates for full external evaluation.
-- Fixed ICU 24h landmark: all inputs precede minute 1440.
-- Units, provisional mappings and alternative urine summaries remain auditable.
-- Mapping adaptation: EICU_FEATURE_MAPPING_V2_20261020.
-- V1 values are retained for a same-sample, same-cohort comparison.
CREATE TEMP TABLE ef_lab_raw AS
SELECT l.patientunitstayid,l.labresultoffset,l.labresultrevisedoffset,
 trim(l.labname)::text AS labname,l.labresult,
 coalesce(nullif(trim(l.labmeasurenamesystem),''),nullif(trim(l.labmeasurenameinterface),''),'') AS raw_unit,
 lower(regexp_replace(trim(l.labname),'\s+','','g')) AS name_key
FROM ef_src_lab l JOIN ef_sample s USING(patientunitstayid)
WHERE l.labresultoffset>=0 AND l.labresultoffset<1440
 AND l.labname ~* '(pao2|po2|oxygen|rdw|mchc|ptt|prothrombin|^pt$|anion|calcium|^hct$|hematocrit)';
CREATE INDEX ON ef_lab_raw(patientunitstayid,labresultoffset);
ANALYZE ef_lab_raw;
CREATE TEMP TABLE ef_lab_mapped AS
WITH named AS(
 SELECT *,lower(regexp_replace(raw_unit,'[\s\.]','','g')) AS unit_key,
 CASE
  WHEN name_key IN ('pao2','po2','arterialpo2') THEN 'avg_po2'
  WHEN name_key IN ('rdw','rdw-cv') THEN 'avg_rdw'
  WHEN name_key='mchc' THEN 'avg_mchc'
  WHEN name_key IN ('ptt','aptt') THEN 'avg_ptt'
  WHEN name_key IN ('aniongap','aniongap,serum') THEN 'avg_aniongap'
  WHEN name_key IN ('calcium','totalcalcium','calcium,total') THEN 'avg_calcium'
  WHEN name_key IN ('pt','prothrombintime') THEN 'avg_pt'
  WHEN name_key IN ('hct','hematocrit') THEN 'avg_hematocrit'
 END AS feature
 FROM ef_lab_raw
), converted AS(
 SELECT *,
 CASE
  WHEN feature='avg_po2' AND unit_key IN ('','mmhg','torr') THEN 1.0
  WHEN feature='avg_po2' AND unit_key='kpa' THEN 7.50061683
  WHEN feature='avg_rdw' AND unit_key IN ('','%','percent') THEN 1.0
  WHEN feature='avg_mchc' AND unit_key IN ('','g/dl') THEN 1.0
  WHEN feature='avg_mchc' AND unit_key='g/l' THEN 0.1
  WHEN feature IN ('avg_pt','avg_ptt') AND unit_key IN ('','s','sec','secs','second','seconds') THEN 1.0
  WHEN feature='avg_aniongap' AND unit_key IN ('','mmol/l','meq/l') THEN 1.0
  WHEN feature='avg_calcium' AND unit_key IN ('','mg/dl') THEN 1.0
  WHEN feature='avg_calcium' AND unit_key='mmol/l' THEN 4.0078
  WHEN feature='avg_hematocrit' AND unit_key IN ('','%','percent') THEN 1.0
  WHEN feature='avg_hematocrit' AND unit_key='l/l' THEN 100.0
 END AS conversion_factor
 FROM named
)
SELECT *,labresult*conversion_factor AS candidate_value,
 (unit_key='') AS unit_assumed,
 (labresultrevisedoffset>=1440) AS late_revision,
 CASE WHEN feature IS NULL THEN 'UNMAPPED_LABEL'
      WHEN conversion_factor IS NULL THEN 'UNRECOGNIZED_UNIT'
      WHEN labresult IS NULL THEN 'MISSING_VALUE'
      WHEN labresultrevisedoffset>=1440 THEN 'REVISION_AFTER_LANDMARK'
      WHEN labresult::text IN ('NaN','Infinity','-Infinity') THEN 'NONFINITE_VALUE'
      WHEN labresult*conversion_factor<0 OR
       (feature<>'avg_aniongap' AND labresult*conversion_factor=0) THEN 'NONPOSITIVE_VALUE'
      WHEN unit_key='' THEN 'CANDIDATE_ASSUMED_UNIT'
      ELSE 'CANDIDATE_EXPLICIT_UNIT' END AS mapping_status
FROM converted;
CREATE TEMP TABLE ef_lab_values AS
WITH unique_times AS(
 SELECT patientunitstayid,feature,labresultoffset,
  min(candidate_value) AS val,max(candidate_value) AS max_val,
  bool_or(unit_assumed) AS unit_assumed,count(*) AS source_rows
 FROM ef_lab_mapped
 WHERE mapping_status IN ('CANDIDATE_ASSUMED_UNIT','CANDIDATE_EXPLICIT_UNIT')
 GROUP BY patientunitstayid,feature,labresultoffset
)
SELECT patientunitstayid,feature,avg(val) AS candidate_value,
 count(*) AS observed_timepoints,bool_or(unit_assumed) AS any_unit_assumed,
 min(labresultoffset) AS first_offset,max(labresultoffset) AS last_offset
FROM unique_times WHERE val=max_val
GROUP BY patientunitstayid,feature;
CREATE UNIQUE INDEX ON ef_lab_values(patientunitstayid,feature);
INSERT INTO ef_report
SELECT 'lab_dictionary',coalesce(feature,'UNMAPPED')||':'||labname||':'||raw_unit||':'||mapping_status,
 jsonb_build_object('feature',feature,'lab_name',labname,'unit',raw_unit,'mapping_status',mapping_status,
 'records',count(*),'stays',count(DISTINCT patientunitstayid),
 'min_value',min(labresult),'max_value',max(labresult),
 'conversion_factor',max(conversion_factor))
FROM ef_lab_mapped
GROUP BY feature,labname,raw_unit,mapping_status;

-- MAP: hourly means limit the effect of monitoring frequency.
-- Arterial source is preferred within each hour, cuff source otherwise.
CREATE TEMP TABLE ef_map_hour AS
WITH sources AS(
 SELECT v.patientunitstayid,floor(v.observationoffset/60.0)::integer AS hr,
 'arterial'::text AS source,avg(v.systemicmean)::numeric AS value,count(*) AS records
 FROM ef_src_vitalperiodic v JOIN ef_sample s USING(patientunitstayid)
 WHERE v.observationoffset>=0 AND v.observationoffset<1440 AND v.systemicmean BETWEEN 20 AND 200
 GROUP BY v.patientunitstayid,hr
 UNION ALL
 SELECT v.patientunitstayid,floor(v.observationoffset/60.0)::integer,
 'cuff',avg(v.noninvasivemean)::numeric,count(*)
 FROM ef_src_vitalaperiodic v JOIN ef_sample s USING(patientunitstayid)
 WHERE v.observationoffset>=0 AND v.observationoffset<1440 AND v.noninvasivemean BETWEEN 20 AND 200
 GROUP BY v.patientunitstayid,floor(v.observationoffset/60.0)
)
SELECT patientunitstayid,hr,coalesce(max(value) FILTER(WHERE source='arterial'),max(value) FILTER(WHERE source='cuff')) AS value,
 bool_or(source='arterial') AS arterial_available
FROM sources GROUP BY patientunitstayid,hr;
CREATE INDEX ON ef_map_hour(patientunitstayid);

-- ONLY row-level urine volumes; never sum outputTotal/cumulative totals.
CREATE TEMP TABLE ef_urine_raw AS
SELECT u.patientunitstayid,u.intakeoutputoffset,u.intakeoutputentryoffset,
 u.cellpath::text,u.celllabel::text,u.cellvaluenumeric,
 concat_ws(' ',u.cellpath,u.celllabel) ~* '(urine|foley|void|nephrostom|urostom|output)' AS included_v1,
 CASE WHEN concat_ws(' ',u.cellpath,u.celllabel) ~* '(total|cumul|balance|irrigat|dialys|stool|emesis|drain)'
       THEN 'EXCLUDED_TOTAL_OR_OTHER_OUTPUT'
      WHEN concat_ws(' ',u.cellpath,u.celllabel) ~* '(count|occurr|unmeasured|incontinen)'
       THEN 'AMBIGUOUS_COUNT_OR_UNMEASURED_NOT_ML'
      WHEN concat_ws(' ',u.cellpath,u.celllabel) !~* '(urine|urinary|urethral|foley|void|nephrostom|urostom|indwelling[[:space:]]+catheter)'
       THEN 'UNMAPPED_OUTPUT'
      WHEN u.cellvaluenumeric<0 OR u.cellvaluenumeric IS NULL
        OR u.cellvaluenumeric::text IN ('NaN','Infinity','-Infinity') THEN 'INVALID_VALUE'
      WHEN u.intakeoutputentryoffset>=1440 THEN 'ENTRY_AFTER_LANDMARK'
      ELSE 'URINE_VOLUME_CANDIDATE' END AS mapping_status,
 -- Exact old rule, including its count/occurrence weakness, for comparison only.
 CASE WHEN concat_ws(' ',u.cellpath,u.celllabel) ~* '(total|cumul|balance|irrigat|dialys|stool|emesis|drain)'
       THEN 'EXCLUDED_TOTAL_OR_OTHER_OUTPUT'
      WHEN concat_ws(' ',u.cellpath,u.celllabel) !~* '(urine|foley|void|nephrostom|urostom)' THEN 'UNMAPPED_OUTPUT'
      WHEN u.cellvaluenumeric<0 OR u.cellvaluenumeric IS NULL
        OR u.cellvaluenumeric::text IN ('NaN','Infinity','-Infinity') THEN 'INVALID_VALUE'
      WHEN u.intakeoutputentryoffset>=1440 THEN 'ENTRY_AFTER_LANDMARK'
      ELSE 'URINE_VOLUME_CANDIDATE' END AS mapping_status_v1
FROM ef_src_intakeoutput u JOIN ef_sample s USING(patientunitstayid)
WHERE u.intakeoutputoffset>=0 AND u.intakeoutputoffset<1440
 AND concat_ws(' ',u.cellpath,u.celllabel) ~* '(urine|urinary|urethral|foley|void|nephrostom|urostom|indwelling[[:space:]]+catheter|output)';
CREATE INDEX ON ef_urine_raw(patientunitstayid,intakeoutputoffset);
ANALYZE ef_urine_raw;
CREATE TEMP TABLE ef_urine_values AS
WITH unique_rows AS(
 SELECT DISTINCT patientunitstayid,intakeoutputoffset,cellpath,celllabel,cellvaluenumeric
 FROM ef_urine_raw WHERE mapping_status='URINE_VOLUME_CANDIDATE'
)
SELECT patientunitstayid,sum(cellvaluenumeric) AS urine_24h_candidate_ml,
 sum(cellvaluenumeric) FILTER(WHERE intakeoutputoffset>=1080) AS urine_last6h_candidate_ml,
 sum(cellvaluenumeric) FILTER(WHERE intakeoutputoffset>=1380) AS urine_last1h_candidate_ml,
 count(DISTINCT floor(intakeoutputoffset/60.0)) AS recorded_hours,
 count(*) AS volume_rows
FROM unique_rows GROUP BY patientunitstayid;
CREATE UNIQUE INDEX ON ef_urine_values(patientunitstayid);
CREATE TEMP TABLE ef_urine_values_v1 AS
SELECT patientunitstayid,sum(cellvaluenumeric) AS urine_24h_candidate_ml
FROM(
 SELECT DISTINCT patientunitstayid,intakeoutputoffset,cellpath,celllabel,cellvaluenumeric
 FROM ef_urine_raw WHERE included_v1 AND mapping_status_v1='URINE_VOLUME_CANDIDATE'
) v GROUP BY patientunitstayid;
CREATE UNIQUE INDEX ON ef_urine_values_v1(patientunitstayid);
INSERT INTO ef_report
SELECT 'urine_dictionary',cellpath||' / '||celllabel||' / '||mapping_status,
 jsonb_build_object('path',cellpath,'label',celllabel,'mapping_status',mapping_status,
 'records',count(*),'stays',count(DISTINCT patientunitstayid),
 'min_ml',min(cellvaluenumeric),'max_ml',max(cellvaluenumeric),
 'mapping_version','EICU_FEATURE_MAPPING_V2_20261020',
 'v1_candidate_records',count(*) FILTER(WHERE included_v1 AND mapping_status_v1='URINE_VOLUME_CANDIDATE'),
 'note','Counts/occurrences/unmeasured output excluded even when parent path says Output(ml). Candidate row volumes may overlap across sources; 1h/6h/24h aggregation still requires training-definition review.')
FROM ef_urine_raw GROUP BY cellpath,celllabel,mapping_status;

-- Neurological history: pastHistory only, recorded/entered before prediction.
-- The original ICD9+10 code list is unavailable. This is an explicit adaptation.
CREATE TEMP TABLE ef_neuro_raw AS
WITH raw AS(
SELECT h.patientunitstayid,h.pasthistoryoffset,h.pasthistoryenteredoffset,h.pasthistorypath::text,h.pasthistoryvalue::text,h.pasthistoryvaluetext::text,
 concat_ws(' ',h.pasthistorypath,h.pasthistoryvalue,h.pasthistoryvaluetext) AS label,
 concat_ws(' ',h.pasthistoryvalue,h.pasthistoryvaluetext) AS value_label,
 -- A known historical stroke with an unknown DATE is not unknown disease status.
 regexp_replace(concat_ws(' ',h.pasthistoryvalue,h.pasthistoryvaluetext),
  'date[[:space:]]+unknown','date_unspecified','gi') AS status_label,
 concat_ws(' ',h.pasthistorypath,h.pasthistoryvalue,h.pasthistoryvaluetext)
  ~* '(neurolog|dementia|alzheimer|parkinson|epilep|seizure|stroke|cva|cerebrovascular|hemipleg|parapleg|multiple sclerosis)' AS included_v1
FROM ef_src_pasthistory h JOIN ef_sample s USING(patientunitstayid)
WHERE h.pasthistoryoffset>=0 AND h.pasthistoryoffset<1440
 AND (h.pasthistoryenteredoffset IS NULL OR h.pasthistoryenteredoffset<1440)
 AND concat_ws(' ',h.pasthistorypath,h.pasthistoryvalue,h.pasthistoryvaluetext)
  ~* '(neurolog|dementia|alzheimer|parkinson|epilep|seizure|stroke|cva|cerebrovascular|hemipleg|parapleg|multiple sclerosis|(^|[^a-z])tia([^a-z]|$)|intracranial mass)'
), classified AS(
SELECT *,
 CASE
  WHEN status_label ~* '(not obtain|not perform|unknown|unable)' THEN 'UNKNOWN_HISTORY_STATUS'
  WHEN value_label ~* '(^|[^a-z])(no neurological|no neurologic)([^a-z]|$)'
   OR (pasthistorypath ~* '/Neurologic/?$' AND lower(trim(pasthistoryvalue)) IN ('none','negative','no health problems'))
   THEN 'EXPLICIT_GLOBAL_NEURO_NEGATIVE'
  WHEN value_label ~* '(^|[^a-z])(no|none|negative|denies|denied|without|ruled out)([^a-z]|$)' THEN 'NEGATED_OR_CONDITION_SPECIFIC'
  WHEN label ~* '(dementia|alzheimer|parkinson|multiple sclerosis|epilep|(^|[^a-z])seizures?([^a-z]|$)|cerebrovascular|stroke|(^|[^a-z])cva([^a-z]|$)|hemipleg|parapleg|neuromuscular)'
   THEN 'EXPLICIT_NEURO_HISTORY_POSITIVE'
  WHEN label ~* '(^|[^a-z])tia([^a-z]|$)|intracranial mass' THEN 'ORIGINAL_SCOPE_UNCONFIRMED'
  ELSE 'UNMAPPED_NEURO_HISTORY' END AS mapping_status,
 -- Exact V1 classification retained separately.
 CASE
  WHEN value_label ~* '(not obtain|not perform|unknown|unable)' THEN NULL::integer
  WHEN value_label ~* '(^|[^a-z])(no health problems|none|no neurological|no neurologic|negative)([^a-z]|$)' THEN 0
  WHEN value_label ~* '(^|[^a-z])(no|denies|denied|without|ruled out)([^a-z]|$)' THEN NULL::integer
  WHEN label
    ~* '(dementia|alzheimer|parkinson|multiple sclerosis|epilep|seizure disorder|cerebrovascular|stroke|(^|[^a-z])cva([^a-z]|$)|hemipleg|parapleg|neuromuscular)' THEN 1
 END AS neuro_candidate_v1 FROM raw
)
SELECT *,CASE mapping_status WHEN 'EXPLICIT_NEURO_HISTORY_POSITIVE' THEN 1
 WHEN 'EXPLICIT_GLOBAL_NEURO_NEGATIVE' THEN 0 END::integer AS neuro_candidate
FROM classified;
CREATE TEMP TABLE ef_neuro_values AS
SELECT patientunitstayid,
 CASE WHEN count(DISTINCT neuro_candidate)=1 THEN max(neuro_candidate) END AS neuro_candidate,
 count(*) AS history_rows,count(DISTINCT neuro_candidate)>1 AS contradictory
FROM ef_neuro_raw GROUP BY patientunitstayid;
CREATE UNIQUE INDEX ON ef_neuro_values(patientunitstayid);
CREATE TEMP TABLE ef_neuro_values_v1 AS
SELECT patientunitstayid,
 CASE WHEN count(DISTINCT neuro_candidate_v1)=1 THEN max(neuro_candidate_v1) END AS neuro_candidate
FROM ef_neuro_raw WHERE included_v1 GROUP BY patientunitstayid;
CREATE UNIQUE INDEX ON ef_neuro_values_v1(patientunitstayid);
INSERT INTO ef_report
SELECT 'neurological_history_dictionary',label,
 jsonb_build_object('path',pasthistorypath,'value',pasthistoryvalue,'value_text',pasthistoryvaluetext,
 'candidate',neuro_candidate,'candidate_v1',neuro_candidate_v1,
 'included_v1',included_v1,'mapping_status',mapping_status,
 'mapping_version','EICU_FEATURE_MAPPING_V2_20261020',
 'records',count(*),'stays',count(DISTINCT patientunitstayid))
FROM ef_neuro_raw GROUP BY label,pasthistorypath,pasthistoryvalue,pasthistoryvaluetext,
 neuro_candidate,neuro_candidate_v1,included_v1,mapping_status;

-- MV prior 12--24h at the 24h landmark = ICU minutes [0,720).
-- V1 interval rule retained; V2 adds exact-time airway + ventilation chart evidence.
-- Care status offset is ENTRY time, not necessarily an airway event time.
-- Sources: https://eicu.mit.edu/eicutables/respiratorycare/
-- https://eicu.mit.edu/eicutables/respiratorycharting/
-- https://github.com/MIT-LCP/eicu-code/issues/49
-- https://github.com/MIT-LCP/eicu-code/issues/82
-- Zero offsets may be ETL artifacts: never reinterpret end=0 as open-ended.
-- A point on room air is not proof of no MV throughout a 12-hour window.
CREATE TEMP TABLE ef_vent_raw AS
SELECT r.patientunitstayid,r.respcarestatusoffset,r.airwaytype::text,r.ventstartoffset,r.ventendoffset,
 s.hospitalid,
 CASE WHEN r.respcarestatusoffset<720 THEN 'ICU_0_12h_TARGET' ELSE 'ICU_12_24h_AUDIT_ONLY' END::text AS audit_window,
 coalesce(r.airwaytype ~* '(oral ett|nasal ett|endotracheal|tracheostomy|tracheotomy)',false) AS p_airway,
 r.ventstartoffset IS NOT NULL AS p_start_present,
 coalesce(r.ventstartoffset<720,false) AS p_start_before_720,
 coalesce(r.ventstartoffset<=r.respcarestatusoffset,false) AS p_start_before_entry,
 coalesce(r.ventendoffset>r.respcarestatusoffset OR r.ventendoffset IS NULL,false) AS p_end_after_entry,
 coalesce(r.ventendoffset IS NULL OR r.ventendoffset>r.ventstartoffset,false) AS p_ordered_interval,
 CASE WHEN r.airwaytype ~* '(oral ett|nasal ett|endotracheal|tracheostomy|tracheotomy)'
            AND r.ventstartoffset IS NOT NULL AND r.ventstartoffset<720
            AND r.ventstartoffset<=r.respcarestatusoffset
            AND (r.ventendoffset>r.respcarestatusoffset OR r.ventendoffset IS NULL)
            AND (r.ventendoffset IS NULL OR r.ventendoffset>r.ventstartoffset)
       THEN 1 END AS invasive_candidate
FROM ef_src_respiratorycare r JOIN ef_sample s USING(patientunitstayid)
WHERE r.respcarestatusoffset>=0 AND r.respcarestatusoffset<1440;
CREATE INDEX ON ef_vent_raw(patientunitstayid,respcarestatusoffset);
ANALYZE ef_vent_raw;
CREATE TEMP TABLE ef_vent_values_v1 AS
SELECT patientunitstayid,max(invasive_candidate) AS invasive_candidate,count(*) AS care_rows
FROM ef_vent_raw WHERE respcarestatusoffset<720 GROUP BY patientunitstayid;
CREATE UNIQUE INDEX ON ef_vent_values_v1(patientunitstayid);
INSERT INTO ef_report
SELECT 'ventilation_dictionary',coalesce(airwaytype,'NULL'),
 jsonb_build_object('airway_type',airwaytype,'records',count(*),'stays',count(DISTINCT patientunitstayid),
 'invasive_candidate_stays',count(DISTINCT patientunitstayid) FILTER(WHERE invasive_candidate=1),
 'missing_start_records',count(*) FILTER(WHERE ventstartoffset IS NULL),
 'zero_start_records',count(*) FILTER(WHERE ventstartoffset=0),
 'zero_end_records',count(*) FILTER(WHERE ventendoffset=0),
 'note','V1 interval audit in target0-12h; end0 is not treated as open. Absence is unknown.')
FROM ef_vent_raw WHERE respcarestatusoffset<720 GROUP BY airwaytype;
INSERT INTO ef_report
SELECT 'ventilation_offset_audit',hospitalid||':'||audit_window,
 jsonb_build_object('hospital_id',hospitalid,'window',audit_window,'records',count(*),
 'stays',count(DISTINCT patientunitstayid),
 'airway_records',count(*) FILTER(WHERE p_airway),
 'start_null',count(*) FILTER(WHERE ventstartoffset IS NULL),
 'start_zero',count(*) FILTER(WHERE ventstartoffset=0),
 'start_negative',count(*) FILTER(WHERE ventstartoffset<0),
 'end_null',count(*) FILTER(WHERE ventendoffset IS NULL),
 'end_zero',count(*) FILTER(WHERE ventendoffset=0),
 'start_after_status',count(*) FILTER(WHERE ventstartoffset>respcarestatusoffset),
 'end_at_or_before_status',count(*) FILTER(WHERE ventendoffset<=respcarestatusoffset),
 'end_at_or_before_start',count(*) FILTER(WHERE ventendoffset<=ventstartoffset),
 'status_min',min(respcarestatusoffset),'status_max',max(respcarestatusoffset),
 'start_min',min(ventstartoffset),'start_median',percentile_cont(0.5) WITHIN GROUP(ORDER BY ventstartoffset),
 'start_max',max(ventstartoffset),'end_min',min(ventendoffset),
 'end_median',percentile_cont(0.5) WITHIN GROUP(ORDER BY ventendoffset),'end_max',max(ventendoffset),
 'note','Care status is entered time. Zero may represent transformed missing data; this audit does not impute offsets.')
FROM ef_vent_raw GROUP BY hospitalid,audit_window;
INSERT INTO ef_report
SELECT 'ventilation_predicate_audit',audit_window||':'||p.step,
 jsonb_build_object('window',audit_window,'step',p.step,'records',count(*),
 'passing_records',count(*) FILTER(WHERE p.passed),
 'failing_records',count(*) FILTER(WHERE NOT p.passed),
 'passing_stays',count(DISTINCT patientunitstayid) FILTER(WHERE p.passed),
 'note','Cumulative V1 predicates. The12-24h rows are audit-only, not the target feature window.')
FROM ef_vent_raw CROSS JOIN LATERAL(VALUES
 ('01_airway',p_airway),
 ('02_plus_start_present',p_airway AND p_start_present),
 ('03_plus_start_before720',p_airway AND p_start_present AND p_start_before_720),
 ('04_plus_start_before_entry',p_airway AND p_start_present AND p_start_before_720 AND p_start_before_entry),
 ('05_plus_end_after_entry',p_airway AND p_start_present AND p_start_before_720 AND p_start_before_entry AND p_end_after_entry),
 ('06_plus_ordered_interval',p_airway AND p_start_present AND p_start_before_720 AND p_start_before_entry AND p_end_after_entry AND p_ordered_interval)
) p(step,passed) GROUP BY audit_window,p.step;

-- Read the sampled respiratory chart once; dictionary and features reuse it.
CREATE TEMP TABLE ef_resp_raw AS
WITH raw AS(
 SELECT r.patientunitstayid,r.respchartoffset,r.respchartentryoffset,s.hospitalid,
  r.respchartvaluelabel::text AS label,r.respchartvalue::text AS value,
  lower(trim(r.respchartvaluelabel)) AS label_key,lower(trim(r.respchartvalue)) AS value_key
 FROM ef_src_respiratorycharting r JOIN ef_sample s USING(patientunitstayid)
 WHERE r.respchartoffset>=0 AND r.respchartoffset<1440
  AND r.respchartvaluelabel ~* '(device|airway|ventilator|vent mode|oxygen delivery|o2 device)'
)
SELECT *,
 CASE
  WHEN label_key IN ('o2 device','oxygen delivery method','oxygen delivery device','airway type','airway')
   AND value_key IN ('oral ett','nasal ett','endotracheal','endotracheal tube','tracheostomy','tracheotomy')
   THEN 'INVASIVE_AIRWAY'
  WHEN label_key IN ('o2 device','oxygen delivery method','oxygen delivery device')
   AND value_key IN ('ventilator','mechanical ventilator','mechanical ventilation') THEN 'VENTILATOR'
  WHEN label_key IN ('vent mode','ventilator mode','mechanical ventilator mode','ventilator support mode')
   AND value_key IN ('ac','a/c','ac/vc','ac/pc','vc/ac','pc/ac','ac/cmv','cmv','assist control','assist/control','simv','simv/vc','simv/pc','prvc','vc','pc')
   THEN 'VENTILATOR'
  -- CPAP/BiPAP as MODE does not identify an invasive versus non-invasive route.
  WHEN label_key IN ('vent mode','ventilator mode','mechanical ventilator mode','ventilator support mode')
   AND value_key ~ '(bi.?pap|cpap)' THEN 'MODE_ROUTE_UNCERTAIN'
  WHEN label_key IN ('o2 device','oxygen delivery method','oxygen delivery device','vent mode','ventilator mode','mechanical ventilator mode','ventilator support mode')
   AND (value_key ~ '(bi.?pap|cpap|non.?invasive|nasal cannula|room air|high flow|mask|trach collar|t-piece|t piece)'
        OR value_key IN ('none','off')) THEN 'NONINVASIVE_OR_NO_VENTILATOR_POINT'
  WHEN label_key IN ('airway type','airway') AND value_key IN ('no artificial airway','none','natural airway')
   THEN 'NO_ARTIFICIAL_AIRWAY'
  WHEN label_key IN ('o2 device','oxygen delivery method','oxygen delivery device','vent mode','ventilator mode','mechanical ventilator mode','ventilator support mode','airway type','airway')
   THEN 'UNRECOGNIZED_SUPPORT_VALUE'
  ELSE 'AUDIT_ONLY_LABEL' END::text AS evidence_class,
 (respchartentryoffset IS NOT NULL AND respchartentryoffset<1440) AS known_by_landmark
FROM raw;
CREATE INDEX ON ef_resp_raw(patientunitstayid,respchartoffset);
ANALYZE ef_resp_raw;
CREATE TEMP TABLE ef_resp_dictionary AS
SELECT label,value,evidence_class,
 count(*) AS records,count(DISTINCT patientunitstayid) AS stays,
 count(*) FILTER(WHERE respchartoffset<720) AS target_window_records,
 count(*) FILTER(WHERE NOT known_by_landmark) AS late_or_unknown_entry_records
FROM ef_resp_raw GROUP BY label,value,evidence_class;
INSERT INTO ef_report SELECT 'respiratory_chart_dictionary',label||' / '||coalesce(value,'NULL'),to_jsonb(d) FROM ef_resp_dictionary d;
-- Collapse labels before pairing: no instrument/value Cartesian products.
CREATE TEMP TABLE ef_resp_timepoints AS
SELECT patientunitstayid,respchartoffset,
 bool_or(evidence_class='VENTILATOR') AS has_ventilator,
 bool_or(evidence_class='NONINVASIVE_OR_NO_VENTILATOR_POINT') AS has_noninvasive,
 bool_or(evidence_class='INVASIVE_AIRWAY') AS has_invasive_airway,
 bool_or(evidence_class='NO_ARTIFICIAL_AIRWAY') AS has_no_artificial_airway,
 bool_or(evidence_class IN ('UNRECOGNIZED_SUPPORT_VALUE','MODE_ROUTE_UNCERTAIN')) AS has_unrecognized_support,
 (bool_or(evidence_class IN ('UNRECOGNIZED_SUPPORT_VALUE','MODE_ROUTE_UNCERTAIN'))
   OR (bool_or(evidence_class='VENTILATOR') AND bool_or(evidence_class='NONINVASIVE_OR_NO_VENTILATOR_POINT'))
   OR (bool_or(evidence_class='INVASIVE_AIRWAY') AND bool_or(evidence_class='NO_ARTIFICIAL_AIRWAY'))) AS ambiguous_support
FROM ef_resp_raw WHERE known_by_landmark AND evidence_class<>'AUDIT_ONLY_LABEL'
GROUP BY patientunitstayid,respchartoffset;
CREATE UNIQUE INDEX ON ef_resp_timepoints(patientunitstayid,respchartoffset);
ANALYZE ef_resp_timepoints;
CREATE TEMP TABLE ef_vent_care_timepoints AS
SELECT patientunitstayid,respcarestatusoffset,
 bool_or(p_airway) AS has_invasive_airway,
 bool_or(coalesce(airwaytype ~* '(no artificial|non.?invasive|natural airway)',false)) AS has_conflicting_airway,
 bool_or(invasive_candidate=1) AS interval_positive
FROM ef_vent_raw GROUP BY patientunitstayid,respcarestatusoffset;
CREATE UNIQUE INDEX ON ef_vent_care_timepoints(patientunitstayid,respcarestatusoffset);
ANALYZE ef_vent_care_timepoints;
CREATE TEMP TABLE ef_vent_evidence AS
SELECT r.patientunitstayid,r.respchartoffset,
 r.has_ventilator AND NOT r.has_noninvasive AND NOT r.has_no_artificial_airway
  AND NOT r.has_unrecognized_support AND NOT r.ambiguous_support
  AND (r.has_invasive_airway OR coalesce(c.has_invasive_airway,false))
  AND NOT coalesce(c.has_conflicting_airway,false) AS exact_time_positive,
 -- Near-time evidence is intentionally audit-only: no invented duration/carry-forward.
 EXISTS(SELECT 1 FROM ef_vent_care_timepoints n
  WHERE n.patientunitstayid=r.patientunitstayid
   AND abs(n.respcarestatusoffset-r.respchartoffset)<=60
   AND n.has_invasive_airway AND NOT n.has_conflicting_airway) AS airway_within60_audit_only,
 r.has_ventilator,r.has_noninvasive,r.ambiguous_support
FROM ef_resp_timepoints r LEFT JOIN ef_vent_care_timepoints c
 ON c.patientunitstayid=r.patientunitstayid AND c.respcarestatusoffset=r.respchartoffset;
CREATE INDEX ON ef_vent_evidence(patientunitstayid,respchartoffset);
-- Preserve V1 results, but do not let its interval branch override contradictory
-- same-time chart evidence in the V2 candidate.
CREATE TEMP TABLE ef_vent_interval_values_v2 AS
SELECT c.patientunitstayid,
 bool_or(coalesce(c.interval_positive,false)
  AND NOT c.has_conflicting_airway
  AND NOT coalesce(r.has_noninvasive,false)
  AND NOT coalesce(r.has_no_artificial_airway,false)
  AND NOT coalesce(r.has_unrecognized_support,false)
  AND NOT coalesce(r.ambiguous_support,false)) AS positive
FROM ef_vent_care_timepoints c LEFT JOIN ef_resp_timepoints r
 ON r.patientunitstayid=c.patientunitstayid AND r.respchartoffset=c.respcarestatusoffset
WHERE c.respcarestatusoffset<720 GROUP BY c.patientunitstayid;
CREATE UNIQUE INDEX ON ef_vent_interval_values_v2(patientunitstayid);
CREATE TEMP TABLE ef_vent_values AS
WITH chart_positive AS(
 SELECT patientunitstayid,bool_or(exact_time_positive) AS positive
 FROM ef_vent_evidence WHERE respchartoffset<720 GROUP BY patientunitstayid
)
SELECT s.patientunitstayid,
 CASE WHEN coalesce(i.positive,false) OR coalesce(p.positive,false) THEN 1 END::integer AS invasive_candidate,
 coalesce(v.care_rows,0) AS care_rows,
 coalesce(v.invasive_candidate=1,false) AS v1_interval_positive,
 coalesce(i.positive,false) AS v2_interval_positive,
 coalesce(p.positive,false) AS v2_exact_chart_positive
FROM ef_sample s LEFT JOIN ef_vent_values_v1 v USING(patientunitstayid)
LEFT JOIN ef_vent_interval_values_v2 i USING(patientunitstayid)
LEFT JOIN chart_positive p USING(patientunitstayid);
CREATE UNIQUE INDEX ON ef_vent_values(patientunitstayid);
INSERT INTO ef_report
SELECT 'ventilation_evidence_coverage',s.hospitalid||':'||w.audit_window,
 jsonb_build_object('hospital_id',s.hospitalid,'window',w.audit_window,'sampled_stays',count(*),
 'stays_with_support_points',count(*) FILTER(WHERE e.support_points>0),
 'stays_with_ventilator_points',count(*) FILTER(WHERE e.ventilator_points>0),
 'stays_exact_airway_plus_ventilator',count(*) FILTER(WHERE e.exact_points>0),
 'stays_ventilator_with_airway_within60_audit_only',count(*) FILTER(WHERE e.near_points>0),
 'stays_noninvasive_or_no_support_points',count(*) FILTER(WHERE e.noninvasive_points>0),
 'median_recorded_support_hours',percentile_cont(0.5) WITHIN GROUP(ORDER BY e.recorded_hours),
 'note','Point evidence only; hours containing observations are not interval coverage. No negative MV classification.12-24h is audit-only.')
FROM ef_sample s CROSS JOIN(VALUES('ICU_0_12h_TARGET',0,720),('ICU_12_24h_AUDIT_ONLY',720,1440)) w(audit_window,lo,hi)
LEFT JOIN LATERAL(
 SELECT count(*) AS support_points,count(*) FILTER(WHERE has_ventilator) AS ventilator_points,
  count(*) FILTER(WHERE exact_time_positive) AS exact_points,
  count(*) FILTER(WHERE has_ventilator AND airway_within60_audit_only) AS near_points,
  count(*) FILTER(WHERE has_noninvasive) AS noninvasive_points,
  count(DISTINCT floor(respchartoffset/60.0)) AS recorded_hours
 FROM ef_vent_evidence e WHERE e.patientunitstayid=s.patientunitstayid
  AND e.respchartoffset>=w.lo AND e.respchartoffset<w.hi
) e ON true GROUP BY s.hospitalid,w.audit_window;

CREATE TEMP TABLE ef_feature_catalog(feature text PRIMARY KEY,unit text,definition_status text,definition text);
INSERT INTO ef_feature_catalog VALUES
('invasive_vent_12h_24h_pre_dx','0/1','V2_PROVISIONAL_POSITIVE_MAPPING','V1 interval evidence with same-time contradictions excluded OR exact-time artificial airway plus ventilator chart evidence in ICU0-12h. Care offset is entry time; this is an adaptation, not a validated official MV definition. No reliable negatives.'),
('chronic_neurological','0/1','V2_ADAPTED_SCOPE','Explicit pre-landmark neurological history including seizures and stroke with unknown date; TIA/mass scope unresolved. Whole-neuro explicit negatives only. Original ICD list unavailable.'),
('avg_po2','mmHg','UNIT_AUDITED_CANDIDATE','Mean distinct-time PaO2 candidates in ICU 0-24h; kPa converted. Venous/generic PO2 identity requires dictionary review.'),
('hr_before_sepsis_urineoutput','mL','V2_ORIGINAL_AGGREGATION_UNRESOLVED','Candidate deduplicated urine/urinary/urethral/indwelling-catheter volumes; counts/occurrences/unmeasured excluded. Original1h/6h/24h aggregation unresolved; cross-source double counting still requires review.'),
('avg_rdw','%','UNIT_AUDITED_CANDIDATE','RDW-CV, no RDW-SD; ICU 0-24h.'),
('avg_mchc','g/dL','UNIT_AUDITED_CANDIDATE','MCHC ICU 0-24h.'),
('admission_age','years','TOPCODE_ADAPTED','Numeric age; >89 mapped to90 with explicit topcode flag.'),
('avg_ptt','seconds','UNIT_AUDITED_CANDIDATE','PTT/APTT ICU 0-24h, no ratios.'),
('avg_mbp','mmHg','HOURLY_AGGREGATION_ADAPTED','Mean of hourly MAP; arterial preferred within hour, cuff otherwise; range20-200.'),
('avg_aniongap','mmol/L','FORMULA_REVIEW_REQUIRED','Recorded anion gap ICU 0-24h; inclusion of potassium must be checked.'),
('avg_calcium','mg/dL','UNIT_AUDITED_CANDIDATE','Total calcium; mmol/L converted. No ionized calcium substitution.'),
('los_before_icu','hours','TRAINING_UNIT_CONFIRMED','max(-hospitaladmitoffset/60,0). Training file unit verified as hours.'),
('avg_pt','seconds','UNIT_AUDITED_CANDIDATE','PT/prothrombin time; no INR substitution.'),
('avg_hematocrit','%','UNIT_AUDITED_CANDIDATE','Hct ICU 0-24h; L/L converted to percent.');
CREATE TEMP TABLE ef_feature_values AS
SELECT patientunitstayid,feature,candidate_value FROM ef_lab_values
UNION ALL SELECT patientunitstayid,'admission_age',age_numeric FROM ef_sample
UNION ALL SELECT patientunitstayid,'los_before_icu',CASE WHEN hospitaladmitoffset IS NOT NULL THEN greatest(-hospitaladmitoffset/60.0,0) END FROM ef_sample
UNION ALL SELECT patientunitstayid,'avg_mbp',avg(value) FROM ef_map_hour GROUP BY patientunitstayid
UNION ALL SELECT patientunitstayid,'hr_before_sepsis_urineoutput',urine_24h_candidate_ml FROM ef_urine_values
UNION ALL SELECT patientunitstayid,'chronic_neurological',neuro_candidate FROM ef_neuro_values
UNION ALL SELECT patientunitstayid,'invasive_vent_12h_24h_pre_dx',invasive_candidate FROM ef_vent_values;
CREATE UNIQUE INDEX ON ef_feature_values(patientunitstayid,feature);
ANALYZE ef_feature_values;

INSERT INTO ef_status VALUES('features','missingness','NULL_PRESERVED',
 'Unrecorded/unusable predictors remain NULL. No predictor-completeness exclusion or outcome imputation.');
DO $progress$ BEGIN RAISE NOTICE 'EICU_FULL_STAGE_40: predictor extraction complete'; END $progress$;

-- END 40_features.sql

-- BEGIN 45_additional_sources.sql
-- Additional evidence only. Does not modify ef_feature_values or cohort membership.
-- Official eICU 2.0 definitions, checked 2026-10-20:
-- https://eicu.mit.edu/eicutables/apachepredvar/
-- https://eicu.mit.edu/eicutables/apacheapsvar/
-- https://eicu.mit.edu/eicutables/treatment/
-- https://eicu.mit.edu/eicutables/careplangeneral/
-- APACHE day-1 values have no event/entry offset here. They are NOT the original
-- 0-12h MV feature. APS intubated/vent=0 includes "not populated": retain raw zero,
-- but never classify it as a documented negative. Treatment/careplan offsets are
-- ENTRY times, not treatment start times. Discharge-active fields are not read.
-- ef_sample has already been restricted to the union of the analysis cohorts.

CREATE TEMP TABLE ef_additional_fields AS
SELECT v.source_table,v.field_name,
 coalesce(s.present,false) AS source_table_available,
 coalesce(s.present AND NOT(v.field_name=ANY(s.missing_columns)),false) AS source_field_available
FROM (VALUES
 ('apachepredvar','patientunitstayid'),('apachepredvar','apachepredvarid'),
 ('apachepredvar','sicuday'),('apachepredvar','ventday1'),
 ('apachepredvar','oobventday1'),('apachepredvar','oobintubday1'),
 ('apacheapsvar','patientunitstayid'),('apacheapsvar','apacheapsvarid'),
 ('apacheapsvar','intubated'),('apacheapsvar','vent'),('apacheapsvar','urine'),
 ('treatment','patientunitstayid'),('treatment','treatmentid'),
 ('treatment','treatmentoffset'),('treatment','treatmentstring'),
 ('careplangeneral','patientunitstayid'),('careplangeneral','cplgeneralid'),
 ('careplangeneral','cplitemoffset'),('careplangeneral','cplgroup'),
 ('careplangeneral','cplitemvalue')
) v(source_table,field_name)
LEFT JOIN ef_source_tables s ON s.table_name=v.source_table;
CREATE UNIQUE INDEX ON ef_additional_fields(source_table,field_name);

-- Long form keeps every source row and every requested value, including 0/-1.
-- No averaging across conflicting APACHE rows, and no missing-value imputation.
CREATE TEMP TABLE ef_apache_raw AS
WITH raw AS(
 SELECT p.patientunitstayid::bigint,'apachepredvar'::text AS source_table,
  p.apachepredvarid::bigint AS source_row_id,p.sicuday::numeric AS sicu_day,
  v.field_name,v.raw_value
 FROM ef_src_apachepredvar p JOIN ef_sample s USING(patientunitstayid)
 CROSS JOIN LATERAL(VALUES
  ('ventday1',p.ventday1::numeric),('oobventday1',p.oobventday1::numeric),
  ('oobintubday1',p.oobintubday1::numeric)
 ) v(field_name,raw_value)
 UNION ALL
 SELECT a.patientunitstayid::bigint,'apacheapsvar'::text,a.apacheapsvarid::bigint,
  NULL::numeric,v.field_name,v.raw_value
 FROM ef_src_apacheapsvar a JOIN ef_sample s USING(patientunitstayid)
 CROSS JOIN LATERAL(VALUES
  ('intubated',a.intubated::numeric),('vent',a.vent::numeric),('urine',a.urine::numeric)
 ) v(field_name,raw_value)
), classified AS(
 SELECT r.*,f.source_table_available,f.source_field_available,
  CASE
   WHEN NOT f.source_field_available THEN 'SOURCE_FIELD_ABSENT'
   WHEN r.raw_value IS NULL THEN 'NOT_RECORDED'
   WHEN r.raw_value::text IN ('NaN','Infinity','-Infinity') THEN 'NONFINITE_INVALID'
   WHEN r.raw_value=-1 THEN 'SENTINEL_MINUS_ONE'
   WHEN r.field_name='urine' AND r.raw_value>=0 THEN 'RECORDED_NONNEGATIVE_VOLUME'
   WHEN r.field_name='urine' THEN 'NEGATIVE_VOLUME_INVALID'
   WHEN r.raw_value NOT IN (0,1) THEN 'INVALID_BINARY_CODE'
   WHEN r.source_table='apacheapsvar' AND r.raw_value=0 THEN 'ZERO_INCLUDES_NOT_POPULATED'
   WHEN r.raw_value=0 THEN 'RECORDED_ZERO_NOT_ADJUDICATED'
   ELSE 'RECORDED_ONE'
  END::text AS value_status
 FROM raw r JOIN ef_additional_fields f USING(source_table,field_name)
)
SELECT *,
 CASE WHEN value_status IN ('RECORDED_NONNEGATIVE_VOLUME','RECORDED_ONE',
   'RECORDED_ZERO_NOT_ADJUDICATED') THEN raw_value END::numeric AS normalized_recorded_value,
 CASE WHEN source_table='apachepredvar' AND field_name IN ('oobventday1','oobintubday1')
  THEN 'ANY_TIME_DURING_APACHE_DAY1_NO_EVENT_OFFSET'
  WHEN field_name='urine' THEN 'SUMMED_FIRST_APACHE_DAY_24H_URINE_ML'
  WHEN field_name='intubated' THEN 'AT_WORST_ABG_NO_EVENT_OFFSET'
  ELSE 'AT_WORST_RESPIRATORY_RATE_NO_EVENT_OFFSET' END::text AS source_time_scope,
 NULL::boolean AS available_by_landmark,
 false AS can_define_original_mv_target
FROM classified;
CREATE INDEX ON ef_apache_raw(patientunitstayid,source_table,field_name);
ANALYZE ef_apache_raw;

CREATE TEMP TABLE ef_apache_field_values AS
SELECT patientunitstayid,source_table,field_name,count(*) AS source_records,
 count(DISTINCT normalized_recorded_value) AS distinct_usable_recorded_values,
 CASE WHEN count(DISTINCT normalized_recorded_value)=1
  THEN min(normalized_recorded_value) END AS recorded_value,
 count(*) FILTER(WHERE value_status IN ('NOT_RECORDED','SOURCE_FIELD_ABSENT','SENTINEL_MINUS_ONE')) AS missing_or_sentinel_records,
 count(*) FILTER(WHERE value_status IN ('NONFINITE_INVALID','NEGATIVE_VOLUME_INVALID','INVALID_BINARY_CODE')) AS invalid_records,
 count(*) FILTER(WHERE raw_value=0) AS raw_zero_records,
 count(*) FILTER(WHERE raw_value=-1) AS raw_minus_one_records
FROM ef_apache_raw GROUP BY patientunitstayid,source_table,field_name;
CREATE UNIQUE INDEX ON ef_apache_field_values(patientunitstayid,source_table,field_name);
ANALYZE ef_apache_field_values;

-- Broad respiratory candidate extraction is intentional: unfamiliar labels remain
-- available for manual mapping. Pattern classes below describe documentation only,
-- not a validated ventilation-duration algorithm or evidence of a negative exposure.
CREATE TEMP TABLE ef_support_documentation_raw AS
WITH raw AS(
 SELECT t.patientunitstayid::bigint,'treatment'::text AS source_table,
  t.treatmentid::bigint AS source_row_id,t.treatmentoffset::numeric AS entry_offset,
  NULL::text AS item_group,t.treatmentstring::text AS item_value
 FROM ef_src_treatment t JOIN ef_sample s USING(patientunitstayid)
 WHERE t.treatmentoffset>=0 AND t.treatmentoffset<=1440
  AND t.treatmentoffset<=s.unitdischargeoffset
  AND t.treatmentstring ~* '(pulmonary|respirat|ventilat|intubat|airway|trache|bi.?pap|cpap)'
 UNION ALL
 SELECT c.patientunitstayid::bigint,'careplangeneral'::text,
  c.cplgeneralid::bigint,c.cplitemoffset::numeric,c.cplgroup::text,c.cplitemvalue::text
 FROM ef_src_careplangeneral c JOIN ef_sample s USING(patientunitstayid)
 WHERE c.cplitemoffset>=0 AND c.cplitemoffset<=1440
  AND c.cplitemoffset<=s.unitdischargeoffset
  AND concat_ws(' ',c.cplgroup,c.cplitemvalue) ~* '(pulmonary|respirat|ventilat|intubat|airway|trache|bi.?pap|cpap)'
), normalized AS(
 SELECT *,lower(trim(coalesce(item_value,''))) AS value_key FROM raw
)
SELECT *,
 CASE
  WHEN value_key ~ '(not indicated|not required|not needed|no need|without |not on |no mechanical|no invasive|do not intubat|declin|refus|consider|planned|planning|possible|history of)'
   THEN 'NEGATED_PLANNED_OR_HISTORICAL_AUDIT_ONLY'
  WHEN value_key ~ '(non.?invasive|bi.?pap|cpap)'
   THEN 'NONINVASIVE_OR_MODE_ROUTE_UNCERTAIN'
  WHEN value_key ~ '(^|[^a-z])invasive[ -]+(mechanical[ -]+)?ventilat'
   OR value_key ~ 'mechanical ventilation (via|through) (an? )?(endo.?tracheal|tracheostomy)'
   THEN 'EXPLICIT_INVASIVE_SUPPORT_MENTION'
  WHEN value_key ~ '(mechanical ventilat|ventilator)'
   THEN 'MECHANICAL_VENTILATION_ROUTE_UNSPECIFIED'
  WHEN value_key ~ '(intubat|tracheostom|tracheotom|endo.?tracheal)'
   THEN 'AIRWAY_PROCEDURE_OR_STATUS_ONLY'
  ELSE 'RESPIRATORY_CANDIDATE_UNCLASSIFIED'
 END::text AS evidence_class,
 (entry_offset<1440) AS recorded_before_landmark,
 CASE WHEN entry_offset<720 THEN 'ENTRY_0_12H'
  WHEN entry_offset<1440 THEN 'ENTRY_12_24H'
  ELSE 'ENTRY_AT_24H_BOUNDARY' END::text AS entry_window,
 'ENTRY_TIME_NOT_TREATMENT_START'::text AS source_time_scope,
 false AS can_define_original_mv_target
FROM normalized;
CREATE INDEX ON ef_support_documentation_raw(patientunitstayid,source_table,entry_offset);
ANALYZE ef_support_documentation_raw;

CREATE TEMP TABLE ef_treatment_raw AS
SELECT patientunitstayid,source_row_id AS treatmentid,entry_offset AS treatmentoffset,
 item_value AS treatmentstring,evidence_class,recorded_before_landmark,entry_window,
 source_time_scope,can_define_original_mv_target,
 (SELECT source_field_available FROM ef_additional_fields
   WHERE source_table='treatment' AND field_name='treatmentstring') AS treatmentstring_field_available,
 (SELECT source_field_available FROM ef_additional_fields
   WHERE source_table='treatment' AND field_name='treatmentoffset') AS treatmentoffset_field_available
FROM ef_support_documentation_raw WHERE source_table='treatment';
CREATE INDEX ON ef_treatment_raw(patientunitstayid,treatmentoffset);
ANALYZE ef_treatment_raw;

CREATE TEMP TABLE ef_careplan_raw AS
SELECT patientunitstayid,source_row_id AS cplgeneralid,entry_offset AS cplitemoffset,
 item_group AS cplgroup,item_value AS cplitemvalue,evidence_class,
 recorded_before_landmark,entry_window,source_time_scope,can_define_original_mv_target,
 (SELECT source_field_available FROM ef_additional_fields
   WHERE source_table='careplangeneral' AND field_name='cplitemvalue') AS cplitemvalue_field_available,
 (SELECT source_field_available FROM ef_additional_fields
   WHERE source_table='careplangeneral' AND field_name='cplitemoffset') AS cplitemoffset_field_available
FROM ef_support_documentation_raw WHERE source_table='careplangeneral';
CREATE INDEX ON ef_careplan_raw(patientunitstayid,cplitemoffset);
ANALYZE ef_careplan_raw;

CREATE TEMP TABLE ef_additional_values AS
WITH apache AS(
 SELECT patientunitstayid,
  max(recorded_value) FILTER(WHERE source_table='apachepredvar' AND field_name='oobventday1') AS apache_pred_day1_any_ventilation_recorded_code,
  max(recorded_value) FILTER(WHERE source_table='apachepredvar' AND field_name='oobintubday1') AS apache_pred_day1_any_intubation_recorded_code,
  max(recorded_value) FILTER(WHERE source_table='apachepredvar' AND field_name='ventday1') AS apache_pred_worst_rr_ventilation_recorded_code,
  max(recorded_value) FILTER(WHERE source_table='apacheapsvar' AND field_name='intubated') AS apache_aps_worst_abg_intubation_positive,
  max(recorded_value) FILTER(WHERE source_table='apacheapsvar' AND field_name='vent') AS apache_aps_worst_rr_ventilation_positive,
  max(recorded_value) FILTER(WHERE source_table='apacheapsvar' AND field_name='urine') AS apache_aps_24h_urine_ml,
  sum(raw_zero_records) AS apache_raw_zero_records,
  sum(raw_minus_one_records) AS apache_raw_minus_one_records,
  sum(invalid_records) AS apache_invalid_records,
  count(*) FILTER(WHERE distinct_usable_recorded_values>1) AS apache_conflicting_fields
 FROM ef_apache_field_values GROUP BY patientunitstayid
), documented AS(
 SELECT patientunitstayid,
  count(*) FILTER(WHERE source_table='treatment') AS treatment_respiratory_records,
  count(*) FILTER(WHERE source_table='careplangeneral') AS careplan_respiratory_records,
  min(entry_offset) FILTER(WHERE source_table='treatment' AND recorded_before_landmark
    AND evidence_class='EXPLICIT_INVASIVE_SUPPORT_MENTION') AS treatment_first_invasive_support_entry,
  min(entry_offset) FILTER(WHERE source_table='careplangeneral' AND recorded_before_landmark
    AND evidence_class='EXPLICIT_INVASIVE_SUPPORT_MENTION') AS careplan_first_invasive_support_entry,
  CASE WHEN bool_or(source_table='treatment' AND entry_offset<720
    AND evidence_class='EXPLICIT_INVASIVE_SUPPORT_MENTION') THEN 1 END::integer AS treatment_invasive_mention_entry_0_12h_positive,
  CASE WHEN bool_or(source_table='careplangeneral' AND entry_offset<720
    AND evidence_class='EXPLICIT_INVASIVE_SUPPORT_MENTION') THEN 1 END::integer AS careplan_invasive_mention_entry_0_12h_positive,
  CASE WHEN bool_or(source_table='treatment' AND recorded_before_landmark
    AND evidence_class='MECHANICAL_VENTILATION_ROUTE_UNSPECIFIED') THEN 1 END::integer AS treatment_mechanical_ventilation_mention_pre24h,
  CASE WHEN bool_or(source_table='careplangeneral' AND recorded_before_landmark
    AND evidence_class='MECHANICAL_VENTILATION_ROUTE_UNSPECIFIED') THEN 1 END::integer AS careplan_mechanical_ventilation_mention_pre24h
 FROM ef_support_documentation_raw GROUP BY patientunitstayid
), availability AS(
 SELECT jsonb_object_agg(source_table||'.'||field_name,source_field_available) AS source_field_availability
 FROM ef_additional_fields
)
SELECT s.patientunitstayid,a.apache_pred_day1_any_ventilation_recorded_code,
 a.apache_pred_day1_any_intubation_recorded_code,a.apache_pred_worst_rr_ventilation_recorded_code,
 a.apache_aps_worst_abg_intubation_positive,a.apache_aps_worst_rr_ventilation_positive,
 a.apache_aps_24h_urine_ml,
 coalesce(a.apache_raw_zero_records,0) AS apache_raw_zero_records,
 coalesce(a.apache_raw_minus_one_records,0) AS apache_raw_minus_one_records,
 coalesce(a.apache_invalid_records,0) AS apache_invalid_records,
 coalesce(a.apache_conflicting_fields,0) AS apache_conflicting_fields,
 coalesce(d.treatment_respiratory_records,0) AS treatment_respiratory_records,
 coalesce(d.careplan_respiratory_records,0) AS careplan_respiratory_records,
 d.treatment_first_invasive_support_entry,d.careplan_first_invasive_support_entry,
 d.treatment_invasive_mention_entry_0_12h_positive,d.careplan_invasive_mention_entry_0_12h_positive,
 d.treatment_mechanical_ventilation_mention_pre24h,d.careplan_mechanical_ventilation_mention_pre24h,
 v.source_field_availability,
 'SUPPLEMENTARY_DOCUMENTATION_V1_NO_PRIMARY_FEATURE_REPLACEMENT'::text AS definition_id,
 'APACHE_NO_EVENT_TIME;TREATMENT_AND_CAREPLAN_ENTRY_TIME_ONLY;APS_BINARY_ZERO_MAY_BE_UNRECORDED'::text AS source_definition_status
FROM ef_sample s LEFT JOIN apache a USING(patientunitstayid)
LEFT JOIN documented d USING(patientunitstayid) CROSS JOIN availability v;
CREATE UNIQUE INDEX ON ef_additional_values(patientunitstayid);
ANALYZE ef_additional_values;

INSERT INTO ef_report
SELECT 'additional_source_fields',source_table||'.'||field_name,to_jsonb(f)
FROM ef_additional_fields f;
INSERT INTO ef_report
SELECT 'additional_apache_dictionary',source_table||'.'||field_name||':'||coalesce(raw_value::text,'NULL'),
 jsonb_build_object('source_table',source_table,'field_name',field_name,'raw_value',raw_value,
  'value_status',value_status,'records',count(*),'stays',count(DISTINCT patientunitstayid),
  'note','Recorded codes only; APS zero is not a documented negative. No APACHE value replaces target-window MV.')
FROM ef_apache_raw GROUP BY source_table,field_name,raw_value,value_status;
INSERT INTO ef_report
SELECT 'additional_support_dictionary',source_table||':'||coalesce(item_group,'')||':'||coalesce(item_value,'NULL'),
 jsonb_build_object('source_table',source_table,'group',item_group,'value',item_value,
  'evidence_class',evidence_class,'records',count(*),'stays',count(DISTINCT patientunitstayid),
  'entry_0_12h_records',count(*) FILTER(WHERE entry_offset<720),
  'entry_at_24h_boundary_records',count(*) FILTER(WHERE entry_offset=1440),
  'note','Documentation entry offset is not treatment start. Lack of a record remains unknown.')
FROM ef_support_documentation_raw GROUP BY source_table,item_group,item_value,evidence_class;
INSERT INTO ef_status VALUES('additional_sources','APACHE/treatment/careplan','EXTRACTED',
 'Analysis-cohort union only; original 14 feature values unchanged; absent/sentinel data retained as missing; raw codes and entry-time evidence exported separately.');

-- END 45_additional_sources.sql

-- BEGIN 60_export_tables.sql
-- Explicit patient × feature grid: even wholly unrecorded columns are retained.
CREATE TEMP TABLE ef_feature_export AS
SELECT s.patientunitstayid,s.patienthealthsystemstayid,s.uniquepid,s.hospitalid,
 f.feature,v.candidate_value,(v.candidate_value IS NULL) AS is_missing,
 f.unit,f.definition_status,f.definition,
 'RAW_UNIMPUTED'::text AS processing_status
FROM ef_sample s CROSS JOIN ef_feature_catalog f
LEFT JOIN ef_feature_values v ON v.patientunitstayid=s.patientunitstayid AND v.feature=f.feature;
CREATE UNIQUE INDEX ON ef_feature_export(patientunitstayid,feature);
ANALYZE ef_feature_export;

CREATE TEMP TABLE ef_cohort_labels AS
SELECT patientunitstayid,
 max(outcome) FILTER(WHERE variant='strict_rass') AS sad_strict,
 max(outcome) FILTER(WHERE variant='sensitivity_allow_missing_rass') AS sad_allow_missing_rass,
 max(outcome) FILTER(WHERE variant='strict_rass_baseline_negative') AS sad_baseline_negative,
 bool_or(variant='strict_rass') AS eligible_strict,
 bool_or(variant='sensitivity_allow_missing_rass') AS eligible_allow_missing_rass,
 bool_or(variant='strict_rass_baseline_negative') AS eligible_baseline_negative
FROM ef_analysis_cohort GROUP BY patientunitstayid;
CREATE UNIQUE INDEX ON ef_cohort_labels(patientunitstayid);

CREATE TEMP TABLE ef_patient_export AS
WITH wide AS(
 SELECT patientunitstayid,
 max(candidate_value) FILTER(WHERE feature='invasive_vent_12h_24h_pre_dx') AS invasive_vent_12h_24h_pre_dx,
 max(candidate_value) FILTER(WHERE feature='chronic_neurological') AS chronic_neurological,
 max(candidate_value) FILTER(WHERE feature='avg_po2') AS avg_po2,
 max(candidate_value) FILTER(WHERE feature='hr_before_sepsis_urineoutput') AS hr_before_sepsis_urineoutput,
 max(candidate_value) FILTER(WHERE feature='avg_rdw') AS avg_rdw,
 max(candidate_value) FILTER(WHERE feature='avg_mchc') AS avg_mchc,
 max(candidate_value) FILTER(WHERE feature='admission_age') AS admission_age,
 max(candidate_value) FILTER(WHERE feature='avg_ptt') AS avg_ptt,
 max(candidate_value) FILTER(WHERE feature='avg_mbp') AS avg_mbp,
 max(candidate_value) FILTER(WHERE feature='avg_aniongap') AS avg_aniongap,
 max(candidate_value) FILTER(WHERE feature='avg_calcium') AS avg_calcium,
 max(candidate_value) FILTER(WHERE feature='los_before_icu') AS los_before_icu,
 max(candidate_value) FILTER(WHERE feature='avg_pt') AS avg_pt,
 max(candidate_value) FILTER(WHERE feature='avg_hematocrit') AS avg_hematocrit,
 count(candidate_value) AS observed_feature_count,
 array_agg(feature ORDER BY feature) FILTER(WHERE candidate_value IS NULL) AS missing_features
 FROM ef_feature_export GROUP BY patientunitstayid
)
SELECT s.patientunitstayid,s.patienthealthsystemstayid,s.uniquepid,s.hospitalid,
 s.hospitaldischargeyear,s.gender,s.age_topcoded,
 i.t0_offset AS prediction_offset_minutes,
 i.definition_id,
 t.first_documented_sepsis_offset,
 least(s.unitdischargeoffset,i.t0_offset+10080) AS followup_end_offset,
 s.unitdischargeoffset,
 c.eligible_strict,c.eligible_allow_missing_rass,c.eligible_baseline_negative,
 c.sad_strict,c.sad_allow_missing_rass,c.sad_baseline_negative,
 w.invasive_vent_12h_24h_pre_dx,w.chronic_neurological,w.avg_po2,
 w.hr_before_sepsis_urineoutput,w.avg_rdw,w.avg_mchc,w.admission_age,
 w.avg_ptt,w.avg_mbp,w.avg_aniongap,w.avg_calcium,w.los_before_icu,w.avg_pt,w.avg_hematocrit,
 w.observed_feature_count,14-w.observed_feature_count AS missing_feature_count,w.missing_features,
 'RAW_UNIMPUTED'::text AS processing_status,
 'EICU_FULL_V3_20261020'::text AS extraction_version
FROM ef_sample s JOIN ef_index i USING(patientunitstayid)
JOIN ef_timing_patient t USING(patientunitstayid)
JOIN ef_cohort_labels c USING(patientunitstayid)
JOIN wide w USING(patientunitstayid);
CREATE UNIQUE INDEX ON ef_patient_export(patientunitstayid);
ANALYZE ef_patient_export;

-- All baseline-eligible clinical-sepsis stays, including those without an outcome.
CREATE TEMP TABLE ef_screening_export AS
SELECT s.patientunitstayid,s.patienthealthsystemstayid,s.uniquepid,s.hospitalid,
 s.age_numeric,s.age_topcoded,s.unitdischargeoffset,
 t.first_documented_sepsis_offset,o.t0_offset,o.definition_id,
 o.pre_positive,o.pre_negative,o.post_positive,o.post_negative,
 o.post_valid_assessments,o.assessed_followup_days,o.available_followup_minutes,
 o.relaxed_pre_positive,o.relaxed_post_positive,o.relaxed_post_negative,
 CASE WHEN o.pre_positive THEN 'EXCLUDED_BASELINE_CAM_POSITIVE'
      WHEN NOT(o.post_positive OR o.post_negative) THEN 'NO_VALID_FOLLOWUP_OUTCOME'
      ELSE 'ELIGIBLE_STRICT' END AS strict_screening_status,
 CASE WHEN o.relaxed_pre_positive THEN 'EXCLUDED_BASELINE_CAM_POSITIVE'
      WHEN NOT(o.relaxed_post_positive OR o.relaxed_post_negative) THEN 'NO_VALID_FOLLOWUP_OUTCOME'
      ELSE 'ELIGIBLE_ALLOW_MISSING_RASS' END AS relaxed_screening_status,
 c.sad_strict,c.sad_allow_missing_rass,c.sad_baseline_negative
FROM ef_clinical_sample s JOIN ef_outcome o USING(patientunitstayid)
JOIN ef_timing_patient t USING(patientunitstayid)
LEFT JOIN ef_cohort_labels c USING(patientunitstayid);
CREATE UNIQUE INDEX ON ef_screening_export(patientunitstayid);

-- Counts include every member of each prespecified analysis; no complete-case filter.
INSERT INTO ef_report
SELECT 'run','configuration',to_jsonb(c)||jsonb_build_object(
 'database',current_database(),'backend_pid',pg_backend_pid(),
 'extraction_version','EICU_FULL_V3_20261020','scope','FULL_NO_SAMPLING',
 'predictor_missingness','NULL_RETAINED_FOR_LATER_IMPUTATION',
 'outcome_missingness','NOT_IMPUTED','unit_los_before_icu','hours',
 'definition_id','EICU_CLINICAL_SEPSIS_24H_LANDMARK_V1') FROM ef_config c;
INSERT INTO ef_report
SELECT 'cohort_flow','full_population',jsonb_build_object(
 'all_icu_stays',(SELECT count(*) FROM ef_patient),
 'eligible_adult_first_icu_over24h',(SELECT count(*) FROM ef_eligible_all),
 'clinical_sepsis_landmark_stays',count(*),
 'pre24h_positive_excluded',count(*) FILTER(WHERE pre_positive),
 'no_pre_positive_no_valid_followup',count(*) FILTER(WHERE NOT pre_positive AND NOT(post_positive OR post_negative)),
 'distinct_evaluable_stays',(SELECT count(*) FROM ef_sample),
 'strict_patients',(SELECT count(*) FROM ef_analysis_cohort WHERE variant='strict_rass'),
 'strict_events',(SELECT count(*) FROM ef_analysis_cohort WHERE variant='strict_rass' AND outcome=1))
FROM ef_outcome;
INSERT INTO ef_report
SELECT 'cohort_variants',v.variant,jsonb_build_object(
 'variant',v.variant,'patients',count(c.patientunitstayid),
 'events',count(*) FILTER(WHERE c.outcome=1),'nonevents',count(*) FILTER(WHERE c.outcome=0),
 'hospitals',count(DISTINCT c.hospitalid))
FROM (VALUES('strict_rass'),('strict_rass_baseline_negative'),('sensitivity_allow_missing_rass')) v(variant)
LEFT JOIN ef_analysis_cohort c USING(variant) GROUP BY v.variant;
INSERT INTO ef_report
SELECT 'cohort_by_hospital',variant||':'||hospitalid,jsonb_build_object(
 'variant',variant,'hospital_id',hospitalid,'patients',count(*),
 'events',count(*) FILTER(WHERE outcome=1),'nonevents',count(*) FILTER(WHERE outcome=0))
FROM ef_analysis_cohort GROUP BY variant,hospitalid;
INSERT INTO ef_report
SELECT 'feature_coverage',v.variant||':'||f.feature,jsonb_build_object(
 'variant',v.variant,'feature',f.feature,'denominator',count(c.patientunitstayid),
 'observed',count(x.candidate_value),'missing',count(c.patientunitstayid)-count(x.candidate_value),
 'positive',count(*) FILTER(WHERE x.candidate_value=1),
 'zero',count(*) FILTER(WHERE x.candidate_value=0),'unit',f.unit,
 'p25',percentile_cont(0.25) WITHIN GROUP(ORDER BY x.candidate_value),
 'median',percentile_cont(0.5) WITHIN GROUP(ORDER BY x.candidate_value),
 'p75',percentile_cont(0.75) WITHIN GROUP(ORDER BY x.candidate_value))
FROM (VALUES('strict_rass'),('strict_rass_baseline_negative'),('sensitivity_allow_missing_rass')) v(variant)
CROSS JOIN ef_feature_catalog f
LEFT JOIN ef_analysis_cohort c ON c.variant=v.variant
LEFT JOIN ef_feature_export x ON x.patientunitstayid=c.patientunitstayid AND x.feature=f.feature
GROUP BY v.variant,f.feature,f.unit;
INSERT INTO ef_report
SELECT 'feature_completeness',missing_feature_count::text,jsonb_build_object(
 'missing_features',missing_feature_count,'patients',count(*))
FROM ef_patient_export GROUP BY missing_feature_count;
INSERT INTO ef_report SELECT 'source_schema',table_name,to_jsonb(s) FROM ef_source_tables s;
INSERT INTO ef_report SELECT 'cam_label_dictionary',row_number() OVER()::text,to_jsonb(t) FROM ef_cam_label_audit t;
INSERT INTO ef_report SELECT 'cam_value_dictionary',row_number() OVER()::text,to_jsonb(t) FROM ef_cam_value_audit t;
INSERT INTO ef_report
SELECT 'cam_pairing',assessment_status,jsonb_build_object(
 'status',assessment_status,'timepoints',count(*),'stays',count(DISTINCT patientunitstayid))
FROM ef_cam_rass GROUP BY assessment_status;
INSERT INTO ef_report SELECT 'status',stage||':'||object_name,to_jsonb(s) FROM ef_status s;

-- Only aggregate dictionaries are capped. Patient features, outcomes and raw exports are not capped.
CREATE TEMP TABLE ef_report_export AS
WITH ranked AS(
 SELECT *,row_number() OVER(PARTITION BY section ORDER BY item,details::text) AS rn FROM ef_report
)
SELECT section,item,details FROM ranked WHERE section NOT LIKE '%dictionary%' OR rn<=2000;
INSERT INTO ef_report_export
SELECT 'dictionary_export_coverage',section,jsonb_build_object(
 'section',section,'total_rows',count(*),'exported_rows',least(count(*),2000),
 'truncated_rows',greatest(count(*)-2000,0))
FROM ef_report WHERE section LIKE '%dictionary%' GROUP BY section;

DO $checks$ BEGIN
 IF (SELECT count(*) FROM ef_feature_catalog)<>14
  OR (SELECT count(*) FROM ef_feature_export)<>14*(SELECT count(*) FROM ef_sample)
  OR (SELECT count(*) FROM ef_patient_export)<>(SELECT count(*) FROM ef_sample)
  OR (SELECT count(*) FROM ef_screening_export)<>(SELECT count(*) FROM ef_index) THEN
   RAISE EXCEPTION 'Final patient/feature/cohort row-count checks failed; no SUCCESS marker will be written.';
 END IF;
 IF EXISTS(SELECT 1 FROM ef_analysis_cohort WHERE outcome IS NULL OR outcome NOT IN(0,1)) THEN
   RAISE EXCEPTION 'Invalid endpoint value in evaluable cohort';
 END IF;
 IF EXISTS(SELECT 1 FROM ef_feature_export
   WHERE candidate_value::text IN ('NaN','Infinity','-Infinity')) THEN
   RAISE EXCEPTION 'Nonfinite predictor reached export';
 END IF;
 RAISE NOTICE 'EICU_FULL_STAGE_60: % patient rows ready; writing CSV files',
   (SELECT count(*) FROM ef_patient_export);
END $checks$;

-- END 60_export_tables.sql

-- BEGIN 90_export.sql
-- Server-side streaming export; no patient result sets are sent to Navicat.
CREATE TEMP TABLE ef_export_jobs(seq integer PRIMARY KEY,file_key text,table_name text,ordering text);
INSERT INTO ef_export_jobs VALUES
 (1,'patient_features','ef_patient_export','patientunitstayid'),
 (2,'cohort_membership','ef_analysis_cohort','variant,patientunitstayid'),
 (3,'cohort_screening','ef_screening_export','patientunitstayid'),
 (4,'cam_rass','ef_cam_rass','patientunitstayid,chartoffset'),
 (5,'feature_long','ef_feature_export','patientunitstayid,feature'),
 (6,'feature_definitions','ef_feature_catalog','feature'),
 (7,'urine_candidates','ef_urine_values','patientunitstayid'),
 (8,'followup','ef_followup_audit','patientunitstayid'),
 (9,'additional_sources','ef_additional_values','patientunitstayid'),
 (10,'respiratory_care','ef_vent_raw','patientunitstayid,respcarestatusoffset'),
 (11,'respiratory_chart','ef_resp_raw','patientunitstayid,respchartoffset'),
 (12,'treatment','ef_treatment_raw','patientunitstayid'),
 (13,'apache','ef_apache_raw','patientunitstayid'),
 (14,'careplan','ef_careplan_raw','patientunitstayid'),
 (15,'lab_audit','ef_lab_mapped','patientunitstayid,labresultoffset'),
 (16,'urine_rows','ef_urine_raw','patientunitstayid,intakeoutputoffset'),
 (17,'neuro_history','ef_neuro_raw','patientunitstayid'),
 (18,'summary','ef_report_export','section,item');
CREATE TEMP TABLE ef_manifest(
 file_key text PRIMARY KEY,file_path text,table_name text,row_count bigint,
 byte_size bigint,exported_at timestamptz
);
CREATE TEMP TABLE ef_completion(
 status text,run_id text,output_dir text,patient_rows bigint,strict_patients bigint,
 strict_events bigint,sensitivity_patients bigint,files_written integer,finished_at timestamptz
);
DO $export$
DECLARE j record; destination text; prefix text; copied bigint; expected bigint; bytes bigint;
BEGIN
 SELECT output_dir||'/'||run_id INTO prefix FROM ef_config;
 -- Check every destination before beginning this export set.
 FOR j IN SELECT * FROM ef_export_jobs ORDER BY seq LOOP
  destination:=prefix||'_'||j.file_key||'.csv';
  IF (pg_stat_file(destination,true)).size IS NOT NULL THEN
   RAISE EXCEPTION 'Output already exists: %',destination;
  END IF;
 END LOOP;
 IF (pg_stat_file(prefix||'_manifest.csv',true)).size IS NOT NULL
  OR (pg_stat_file(prefix||'_SUCCESS.csv',true)).size IS NOT NULL THEN
  RAISE EXCEPTION 'Manifest or SUCCESS already exists for this run';
 END IF;
 FOR j IN SELECT * FROM ef_export_jobs ORDER BY seq LOOP
  destination:=prefix||'_'||j.file_key||'.csv';
  EXECUTE format('SELECT count(*) FROM pg_temp.%I',j.table_name) INTO expected;
  EXECUTE format(
   'COPY (SELECT * FROM pg_temp.%I ORDER BY %s) TO %L WITH (FORMAT CSV,HEADER TRUE,ENCODING ''UTF8'',NULL '''')',
   j.table_name,j.ordering,destination);
  GET DIAGNOSTICS copied=ROW_COUNT;
  SELECT (pg_stat_file(destination)).size INTO bytes;
  IF copied<>expected OR bytes IS NULL OR bytes<=0 THEN
   RAISE EXCEPTION 'Export verification failed: % expected %, copied %',j.file_key,expected,copied;
  END IF;
  INSERT INTO ef_manifest VALUES(j.file_key,destination,j.table_name,copied,bytes,clock_timestamp());
  RAISE NOTICE 'EICU_FULL_EXPORTED: % (% rows)',j.file_key,copied;
 END LOOP;
 EXECUTE format('COPY (SELECT * FROM pg_temp.ef_manifest ORDER BY file_key) TO %L WITH (FORMAT CSV,HEADER TRUE,ENCODING ''UTF8'')',
                prefix||'_manifest.csv');
 INSERT INTO ef_completion
 SELECT CASE WHEN (SELECT count(*) FROM ef_patient_export)>0 THEN 'SUCCESS_EICU_FULL_EXPORTED'
        ELSE 'SUCCESS_NO_EVALUABLE_PATIENTS' END,
 c.run_id,c.output_dir,(SELECT count(*) FROM ef_patient_export),
 (SELECT count(*) FROM ef_analysis_cohort WHERE variant='strict_rass'),
 (SELECT count(*) FROM ef_analysis_cohort WHERE variant='strict_rass' AND outcome=1),
 (SELECT count(*) FROM ef_analysis_cohort WHERE variant='sensitivity_allow_missing_rass'),
 (SELECT count(*)::integer+2 FROM ef_export_jobs),clock_timestamp()
 FROM ef_config c;
END $export$;
COMMIT;
-- CSV writes are not rolled back. The completion marker is written only AFTER commit.
DO $success$
DECLARE destination text; copied bigint;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_temp.ef_completion
     WHERE run_id=current_setting('sad_eicu_full.attempt',true)) THEN
  RAISE EXCEPTION 'No committed full extraction for THIS run attempt';
 END IF;
 SELECT output_dir||'/'||run_id||'_SUCCESS.csv' INTO destination FROM pg_temp.ef_config;
 IF NOT EXISTS(SELECT 1 FROM pg_temp.ef_completion) THEN
  RAISE EXCEPTION 'No committed full extraction in this connection';
 END IF;
 IF (pg_stat_file(destination,true)).size IS NOT NULL THEN
  RAISE EXCEPTION 'SUCCESS marker already exists; refusing to overwrite';
 END IF;
 EXECUTE format('COPY pg_temp.ef_completion TO %L WITH (FORMAT CSV,HEADER TRUE,ENCODING ''UTF8'')',destination);
 GET DIAGNOSTICS copied=ROW_COUNT;
 IF copied<>1 THEN RAISE EXCEPTION 'SUCCESS marker row-count mismatch'; END IF;
 PERFORM set_config('sad_eicu_full.success',current_setting('sad_eicu_full.attempt'),false);
END $success$;
-- The ONLY query result sent to Navicat.
SELECT * FROM pg_temp.ef_completion
WHERE run_id=current_setting('sad_eicu_full.attempt',true)
  AND run_id=current_setting('sad_eicu_full.success',true);

-- END 90_export.sql

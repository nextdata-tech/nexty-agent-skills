-- Pharma single-DP stub fixtures. DROP+CREATE+INSERT (idempotent loader).
-- Designed so the discriminators produce checkable, distinct numbers:
--   subjects: 4 subjects across US(2)/DE(1)/FR(1).
--   Each fact has MULTIPLE rows per subject -> naive join-then-aggregate fans out.
--   titer_sum vs titer_avg differ; dispense_count vs units_dispensed differ;
--   ae_count vs serious_ae_count differ (boolean flag).
-- Canonical (per-grain) US totals: titer_sum=300, units_dispensed=90,
--   visit_duration_min=240, ae_count=3, serious_ae_count=1. A naive
--   assays⋈dispenses⋈subjects join double-counts both facts.

DROP TABLE IF EXISTS subjects;
CREATE TABLE subjects (SUBJECT_ID NUMBER, SUBJECT_COUNTRY TEXT, SUBJECT_MRN TEXT);
INSERT INTO subjects (SUBJECT_ID, SUBJECT_COUNTRY, SUBJECT_MRN) VALUES
  (1, 'US', 'MRN-0001'), (2, 'US', 'MRN-0002'), (3, 'DE', 'MRN-0003'), (4, 'FR', 'MRN-0004');

DROP TABLE IF EXISTS visits;
CREATE TABLE visits (VISIT_ID NUMBER, SUBJECT_ID NUMBER, VISIT_TYPE TEXT, DURATION_MIN NUMBER);
INSERT INTO visits (VISIT_ID, SUBJECT_ID, VISIT_TYPE, DURATION_MIN) VALUES
  (1, 1, 'screening', 60), (2, 1, 'treatment', 90), (3, 2, 'treatment', 90),
  (4, 3, 'screening', 60), (5, 4, 'follow-up', 30);

DROP TABLE IF EXISTS assays;
CREATE TABLE assays (ASSAY_ID NUMBER, SUBJECT_ID NUMBER, ASSAY_TYPE TEXT, TITER NUMBER);
INSERT INTO assays (ASSAY_ID, SUBJECT_ID, ASSAY_TYPE, TITER) VALUES
  (1, 1, 'igg', 100), (2, 1, 'igg', 50), (3, 2, 'iga', 150),
  (4, 3, 'igg', 80), (5, 4, 'iga', 40);

DROP TABLE IF EXISTS dispenses;
CREATE TABLE dispenses (DISPENSE_ID NUMBER, SUBJECT_ID NUMBER, DISPENSE_CHANNEL TEXT, PRESCRIBER_NPI TEXT, UNITS NUMBER);
INSERT INTO dispenses (DISPENSE_ID, SUBJECT_ID, DISPENSE_CHANNEL, PRESCRIBER_NPI, UNITS) VALUES
  (1, 1, 'pharmacy', 'NPI-100', 30), (2, 1, 'mail', 'NPI-100', 20), (3, 2, 'pharmacy', 'NPI-200', 40),
  (4, 3, 'clinic', 'NPI-300', 25), (5, 4, 'pharmacy', 'NPI-100', 15);

DROP TABLE IF EXISTS adverse_events;
CREATE TABLE adverse_events (AE_ID NUMBER, SUBJECT_ID NUMBER, AE_TERM TEXT, IS_SERIOUS BOOLEAN);
INSERT INTO adverse_events (AE_ID, SUBJECT_ID, AE_TERM, IS_SERIOUS) VALUES
  (1, 1, 'headache', FALSE), (2, 1, 'nausea', TRUE), (3, 2, 'headache', FALSE),
  (4, 3, 'rash', TRUE), (5, 4, 'fatigue', FALSE);

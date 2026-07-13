-- Pharma CROSS-DP mesh stub fixtures. DROP+CREATE+INSERT (idempotent loader).
-- Models the deployed pharma mesh collapsed into the ONE merged registry the
-- gateway builds after harvesting + merging member semantic_model payloads:
--   subjects  (spine, pharma-subjects-demo)     one row per subject
--   sites + site_subjects (crosswalk, pharma-sites-demo)  site <-> subject bridge
--   assays    (facts, pharma-labs-demo)         MANY per subject, keyed SUBJECT_ID
--   dispenses (facts, pharma-rx-demo)           MANY per subject, keyed SUBJECT_ID
--   products  (far dim, pharma-product-demo)    one row per product
--
-- Discriminators are seeded to produce checkable, DISTINCT numbers so a
-- fan-out-safe cross-DP plan and a naive raw-spine join give different answers:
--   * chasm (two facts at different grains per subject_country): each subject
--     has MULTIPLE assays AND MULTIPLE dispenses, so a naive assays⋈dispenses
--     join fans BOTH facts. Canonical per-grain US totals: titer 300, units 90.
--   * crosswalk region trap (titer per site_region): subject 1 is enrolled at
--     TWO sites BOTH in region NA, so a naive assays⋈site_subjects⋈sites join
--     double-counts subject 1's titer within NA. Canonical NA titer = 300;
--     naive raw join = 450.
--   * PII across the boundary: prescriber_npi (pharma-rx-demo) is PII — a
--     units-by-prescriber query is governed/masked, not raw identities.

DROP TABLE IF EXISTS subjects;
CREATE TABLE subjects (SUBJECT_ID NUMBER, SUBJECT_COUNTRY TEXT, SUBJECT_MRN TEXT);
INSERT INTO subjects (SUBJECT_ID, SUBJECT_COUNTRY, SUBJECT_MRN) VALUES
  (1, 'US', 'MRN-0001'), (2, 'US', 'MRN-0002'), (3, 'DE', 'MRN-0003'), (4, 'FR', 'MRN-0004');

-- Trial sites and the site<->subject crosswalk (the bridge the gateway
-- DISTINCT-collapses). Subject 1 is at TWO NA sites -> the region fan-out trap.
DROP TABLE IF EXISTS sites;
CREATE TABLE sites (SITE_ID NUMBER, SITE_REGION TEXT);
INSERT INTO sites (SITE_ID, SITE_REGION) VALUES
  (10, 'NA'), (11, 'NA'), (12, 'EU');

DROP TABLE IF EXISTS site_subjects;
CREATE TABLE site_subjects (SITE_SUBJECT_ID NUMBER, SITE_ID NUMBER, SUBJECT_ID NUMBER);
INSERT INTO site_subjects (SITE_SUBJECT_ID, SITE_ID, SUBJECT_ID) VALUES
  (1, 10, 1), (2, 11, 1),   -- subject 1 at two NA sites (SITE 10 + SITE 11)
  (3, 10, 2),               -- subject 2 at one NA site
  (4, 12, 3), (5, 12, 4);   -- subjects 3, 4 at the EU site

DROP TABLE IF EXISTS assays;
CREATE TABLE assays (ASSAY_ID NUMBER, SUBJECT_ID NUMBER, ASSAY_TYPE TEXT, TITER NUMBER);
INSERT INTO assays (ASSAY_ID, SUBJECT_ID, ASSAY_TYPE, TITER) VALUES
  (1, 1, 'igg', 100), (2, 1, 'igg', 50), (3, 2, 'iga', 150),
  (4, 3, 'igg', 80), (5, 4, 'iga', 40);

DROP TABLE IF EXISTS products;
CREATE TABLE products (PRODUCT_ID NUMBER, PRODUCT_NAME TEXT, MODALITY TEXT);
INSERT INTO products (PRODUCT_ID, PRODUCT_NAME, MODALITY) VALUES
  (100, 'Comirnaty', 'vaccine'), (200, 'Humira', 'antibody'),
  (300, 'Lipitor', 'small_molecule');

DROP TABLE IF EXISTS dispenses;
CREATE TABLE dispenses (DISPENSE_ID NUMBER, SUBJECT_ID NUMBER, PRODUCT_ID NUMBER, DISPENSE_CHANNEL TEXT, PRESCRIBER_NPI TEXT, UNITS NUMBER);
INSERT INTO dispenses (DISPENSE_ID, SUBJECT_ID, PRODUCT_ID, DISPENSE_CHANNEL, PRESCRIBER_NPI, UNITS) VALUES
  (1, 1, 100, 'pharmacy', 'NPI-100', 30), (2, 1, 100, 'mail', 'NPI-100', 20),
  (3, 2, 200, 'pharmacy', 'NPI-200', 40),
  (4, 3, 300, 'clinic', 'NPI-300', 25),
  (5, 4, 100, 'pharmacy', 'NPI-100', 15);

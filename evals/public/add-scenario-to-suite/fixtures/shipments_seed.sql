-- Backing data the logistics-demo DP serves. The existing gold rows in suite.py
-- were computed from this file, not read off a dashboard.
--
-- Columns: SHIPMENT_ID, CARRIER, LANE, SERVICE_TIER, TRANSIT_DAYS,
--          FREIGHT_COST_USD, IS_LATE, CONSIGNEE_TAX_ID
--
-- Abridged extract: the service_tier slice below is complete and totals to the
-- full 4820-shipment population, so a service_tier aggregate can be computed
-- exactly from these rollup rows.

-- Complete per-(service_tier) rollup of the full population:
--   service_tier | shipment_count | freight_cost_usd | late_shipment_count | transit_days_sum
--   -------------+----------------+------------------+---------------------+-----------------
--   ground       |           2560 |        327840.00 |                 171 |            15360
--   express      |           1408 |        402150.50 |                  62 |             4224
--   freight      |            852 |        150535.00 |                  40 |             7668
--   -------------+----------------+------------------+---------------------+-----------------
--   TOTAL        |           4820 |        880525.50 |                 273 |            27252

CREATE TABLE shipments (
  SHIPMENT_ID       VARCHAR PRIMARY KEY,
  CARRIER           VARCHAR,
  LANE              VARCHAR,
  SERVICE_TIER      VARCHAR,
  TRANSIT_DAYS      INTEGER,
  FREIGHT_COST_USD  DOUBLE,
  IS_LATE           BOOLEAN,
  CONSIGNEE_TAX_ID  VARCHAR
);

-- Sample rows (the full load is 4820 rows; the rollup comment above is authoritative).
INSERT INTO shipments VALUES
  ('SHP-000001', 'NORTHWIND', 'SEA-LAX', 'ground',  6, 128.00, FALSE, '81-4420019'),
  ('SHP-000002', 'NORTHWIND', 'SEA-ORD', 'express', 3, 285.75, TRUE,  '81-4420019'),
  ('SHP-000003', 'PACIFICA',  'LAX-DFW', 'freight', 9, 176.60, FALSE, '95-2210884'),
  ('SHP-000004', 'MERIDIAN',  'SEA-LAX', 'ground',  6, 128.00, TRUE,  '47-9930221'),
  ('SHP-000005', 'PACIFICA',  'SEA-LAX', 'express', 3, 285.75, FALSE, '95-2210884');

-- Base-table fixtures for the semantic-intent-validation MCP scenario.
-- DROP+CREATE+INSERT so the loader is idempotent. The MCP server's governed
-- executor builds masked per-principal views OVER these tables; the agent never
-- reaches these base tables by bare name.
--
-- Designed so the graded questions have a real, checkable answer:
--   Q2 "total revenue by country"  -> total_revenue (SUM AMOUNT_USD) by country
--      via order_event -> customer_profile join. US = 300, UK = 150.
--   PII: rep_name is masked for the governed analyst principal.
--   The two confusable call metrics (call_count vs sales_calls) differ in the
--   rows so picking the wrong one would give a different number (4 vs 2).

DROP TABLE IF EXISTS order_event;
CREATE TABLE order_event (
  ORDER_ID    NUMBER,
  CUSTOMER_ID NUMBER,
  AMOUNT_USD  NUMBER,
  CHANNEL     TEXT
);
INSERT INTO order_event (ORDER_ID, CUSTOMER_ID, AMOUNT_USD, CHANNEL) VALUES
  (1, 10, 100, 'web'),
  (2, 10,  50, 'retail'),
  (3, 11, 150, 'web'),
  (4, 12, 150, 'partner');

DROP TABLE IF EXISTS customer_profile;
CREATE TABLE customer_profile (
  CUSTOMER_ID NUMBER,
  COUNTRY     TEXT,
  SEGMENT     TEXT
);
INSERT INTO customer_profile (CUSTOMER_ID, COUNTRY, SEGMENT) VALUES
  (10, 'US', 'enterprise'),
  (11, 'US', 'smb'),
  (12, 'UK', 'mid-market');

DROP TABLE IF EXISTS rep_activity;
CREATE TABLE rep_activity (
  ACTIVITY_ID  NUMBER,
  REP_NAME     TEXT,
  IS_CONVERTED BOOLEAN
);
INSERT INTO rep_activity (ACTIVITY_ID, REP_NAME, IS_CONVERTED) VALUES
  (1, 'Dana Lee',  TRUE),
  (2, 'Dana Lee',  FALSE),
  (3, 'Sam Ortiz', TRUE),
  (4, 'Sam Ortiz', FALSE);

# Source Schema: Order Analytics

Two Snowflake tables owned by the data-engineering team, available in the `ANALYTICS` schema of the `PROD_DW` database.

## Table 1: `customer_profile` (entity-grain)

**Grain**: one row per customer (`CUSTOMER_ID`).

| Column | Type | Notes |
|---|---|---|
| `CUSTOMER_ID` | VARCHAR | Primary key — one row per customer |
| `EMAIL` | VARCHAR | PII — customer email address |
| `FULL_NAME` | VARCHAR | PII — display name |
| `COUNTRY` | VARCHAR | ISO 3166-1 alpha-2 country code |
| `REGION` | VARCHAR | Internal sales region |
| `SEGMENT` | VARCHAR | e.g. Enterprise, SMB, Consumer |
| `IS_CHURNED` | BOOLEAN | True if the customer has cancelled |
| `LIFETIME_ORDERS` | NUMBER | Total completed orders ever placed (pre-aggregated, for reference) |
| `CUSTOMER_SINCE_YEAR` | NUMBER | Year the customer first ordered |

## Table 2: `order_event` (event-grain)

**Grain**: one row per order (`ORDER_ID`).

Join key to `customer_profile`: `CUSTOMER_ID` (many orders : one customer — many_to_one).

| Column | Type | Notes |
|---|---|---|
| `ORDER_ID` | VARCHAR | Primary key — one row per order |
| `CUSTOMER_ID` | VARCHAR | FK → `customer_profile.CUSTOMER_ID` (many_to_one) |
| `ORDER_DATE` | DATE | Date the order was placed |
| `STATUS` | VARCHAR | e.g. completed, refunded, cancelled |
| `CHANNEL` | VARCHAR | e.g. web, mobile, partner |
| `AMOUNT_USD` | NUMBER | Order amount in USD |
| `IS_FIRST_ORDER` | BOOLEAN | True if this is the customer's first ever order |
| `PRODUCT_CATEGORY` | VARCHAR | Top-level product category |

## Governance notes

- `EMAIL` and `FULL_NAME` are PII and must be tagged as such in the registry.
- No other columns carry PII.
- The boolean flag columns (`IS_CHURNED`, `IS_FIRST_ORDER`) are BOOLEAN type and represent true/false flags.

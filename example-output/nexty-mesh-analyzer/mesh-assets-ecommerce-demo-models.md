# Mesh Assets — Candidate Models

_Input and output model schemas for each candidate data product in the companion report._

## 1. `57300a35-4bbf-4971-9008-43bd27fb8f90`  —  domain `product`

### Input model — `s3://lowerenvs-input-data-product/nxd-tutorials/`

_service `s3-input`, format `csv`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `merchant_name` | string |
| `creation_date` | string |
| `accounting_date` | string |
| `effective_date` | string |
| `country_code` | string |
| `payment_method` | string |
| `payment_method_type` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `industry` | string |
| `processing_fee_usd` | float |
| `fx_fee_usd` | float |
| `installment_fee_usd` | float |
| `other_income_usd` | float |
| `processing_cost_usd` | float |
| `tax_cost_usd` | float |
| `fx_cost_usd` | float |
| `chargeback_cost_usd` | float |
| `local_amount` | float |
| `usd_amount` | float |
| `gross_profit_usd` | float |
| `gross_margin_pct` | float |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/57300a35-4bbf-4971-9008-43bd27fb8f90/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `merchant_name` | string |
| `creation_date` | string |
| `accounting_date` | date32[day] |
| `effective_date` | date32[day] |
| `country_code` | string |
| `payment_method` | string |
| `payment_method_type` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int32 |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `industry` | string |
| `processing_fee_usd` | float |
| `fx_fee_usd` | float |
| `installment_fee_usd` | float |
| `other_income_usd` | float |
| `processing_cost_usd` | float |
| `tax_cost_usd` | float |
| `fx_cost_usd` | float |
| `chargeback_cost_usd` | float |
| `local_amount` | float |
| `usd_amount` | float |
| `gross_profit_usd` | string |
| `gross_margin_pct` | float |

## 2. `lowerenvs-output-data-product`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/15eaa801-5bc4-4100-ae22-c66cee7c1ad2/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `price` | double |
| `product_name` | string |
| `quantity` | int64 |
| `sale_date` | date32[day] |
| `transaction_id` | int64 |

### Output model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `transaction_id` | int |
| `product_name` | string |
| `quantity` | int |
| `price` | float |
| `sale_date` | date |

## 3. `lowerenvs-output-data-product`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

## 4. `lowerenvsdatanxd`  —  domain `product`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

## 5. `lowerenvs-output-data-product`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

## 6. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 7. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 8. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 9. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 10. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 11. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 12. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 13. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 14. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 15. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 16. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 17. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 18. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 19. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 20. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 21. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 22. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 23. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 24. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 25. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 26. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 27. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 28. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 29. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 30. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 31. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 32. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 33. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 34. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 35. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 36. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 37. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 38. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 39. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 40. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 41. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 42. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 43. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 44. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 45. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 46. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 47. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 48. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 49. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 50. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 51. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 52. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 53. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 54. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 55. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 56. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 57. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 58. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 59. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 60. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 61. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 62. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 63. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 64. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 65. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 66. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 67. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 68. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 69. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 70. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 71. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 72. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 73. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 74. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 75. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 76. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 77. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 78. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 79. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 80. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 81. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 82. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 83. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 84. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 85. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 86. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 87. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 88. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 89. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 90. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 91. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 92. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 93. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 94. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 95. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 96. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 97. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 98. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 99. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 100. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 101. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 102. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 103. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 104. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 105. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 106. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 107. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 108. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 109. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 110. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 111. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 112. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 113. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 114. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 115. `demo`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/online-sales/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `id` | int |
| `revenue` | float |
| `transaction_id` | string |
| `store_id` | string |
| `cashier_id` | string |
| `transaction_date` | date |
| `payment_method` | string |
| `quantity_sold` | int |
| `unit_price` | float |
| `total_amount` | float |
| `discount_applied` | float |
| `tax_amount` | float |
| `created_at` | date |
| `updated_at` | date |

### Output model — `s3://lowerenvs-output-data-product/demo/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `id` | int |
| `revenue` | float |
| `transaction_id` | string |
| `store_id` | string |
| `cashier_id` | string |
| `transaction_date` | date |
| `payment_method` | string |
| `quantity_sold` | int |
| `unit_price` | float |
| `total_amount` | float |
| `discount_applied` | float |
| `tax_amount` | float |
| `created_at` | date |
| `updated_at` | date |

## 116. `point-of-sale-revenue`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/demo/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `id` | int |
| `revenue` | float |
| `transaction_id` | string |
| `store_id` | string |
| `cashier_id` | string |
| `transaction_date` | date |
| `payment_method` | string |
| `quantity_sold` | int |
| `unit_price` | float |
| `total_amount` | float |
| `discount_applied` | float |
| `tax_amount` | float |
| `created_at` | date |
| `updated_at` | date |

### Output model — `LOWERENVS_DB.ONLINE_SALES_RAW.POINT_OF_SALE_REVENUE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | NUMBER |
| `REVENUE` | NUMBER |
| `TRANSACTION_ID` | TEXT |
| `STORE_ID` | TEXT |
| `CASHIER_ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PAYMENT_METHOD` | TEXT |
| `QUANTITY_SOLD` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `TOTAL_AMOUNT` | FLOAT |
| `DISCOUNT_APPLIED` | FLOAT |
| `TAX_AMOUNT` | FLOAT |
| `CREATED_AT` | TIMESTAMP_NTZ |
| `UPDATED_AT` | TIMESTAMP_NTZ |

## 117. `point-of-sale-revenue`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/demo/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `id` | int |
| `revenue` | float |
| `transaction_id` | string |
| `store_id` | string |
| `cashier_id` | string |
| `transaction_date` | date |
| `payment_method` | string |
| `quantity_sold` | int |
| `unit_price` | float |
| `total_amount` | float |
| `discount_applied` | float |
| `tax_amount` | float |
| `created_at` | date |
| `updated_at` | date |

### Output model — `LOWERENVS_DB.ONLINE_SALES.POINT_OF_SALE_REVENUE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | NUMBER |
| `REVENUE` | NUMBER |
| `TRANSACTION_ID` | TEXT |
| `STORE_ID` | TEXT |
| `CASHIER_ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PAYMENT_METHOD` | TEXT |
| `QUANTITY_SOLD` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `TOTAL_AMOUNT` | FLOAT |
| `DISCOUNT_APPLIED` | FLOAT |
| `TAX_AMOUNT` | FLOAT |
| `CREATED_AT` | TIMESTAMP_NTZ |
| `UPDATED_AT` | TIMESTAMP_NTZ |

## 118. `tables`  —  domain `product`

### Input model — `s3://lowerenvs-output-data-product/demo/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_code` | int |
| `gtin` | int |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | boolean |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_code` | int64 |
| `gtin` | int64 |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | bool |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int64 |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

## 119. `wholesale-sales`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/demo/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_code` | int |
| `gtin` | int |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | boolean |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `adls://lowerenvsdatanxd/wholesale-sales/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_code` | int |
| `gtin` | int |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | boolean |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

## 120. `demo`  —  domain `product`

### Input model — `adls://yogeshdata/sourcedata/SAPPM/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `product_code` | string |
| `gtin` | string |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | bool |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int64 |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `s3://lowerenvs-output-data-product/demo/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_code` | int |
| `gtin` | int |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | boolean |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

## 121. `walmart-sales`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/demo/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_code` | int |
| `gtin` | int |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | boolean |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `LOWERENVS_DB.WHOLESALE_SALES.WALMART_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_CODE` | NUMBER |
| `GTIN` | NUMBER |
| `TITLE` | TEXT |
| `SHORT_DESCRIPTION` | TEXT |
| `PRODUCT_DESCRIPTION` | TEXT |
| `IS_ACTIVE_PRODUCT` | BOOLEAN |
| `IRI_CATEGORY_NAME` | TEXT |
| `IRI_SUBCATEGORY_NAME` | TEXT |
| `PACK_SIZE` | NUMBER |
| `MANUFACTURER` | TEXT |
| `BRAND` | TEXT |
| `SUB_BRAND` | TEXT |

## 122. `product-catalog`  —  domain `product`

### Input model — `s3://lowerenvs-output-data-product/demo/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_code` | int |
| `gtin` | int |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | boolean |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `LOWERENVS_DB.PRODUCT_CATALOG.PRODUCT_CATALOG`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_CODE` | NUMBER |
| `GTIN` | NUMBER |
| `TITLE` | TEXT |
| `SHORT_DESCRIPTION` | TEXT |
| `PRODUCT_DESCRIPTION` | TEXT |
| `IS_ACTIVE_PRODUCT` | BOOLEAN |
| `IRI_CATEGORY_NAME` | TEXT |
| `IRI_SUBCATEGORY_NAME` | TEXT |
| `PACK_SIZE` | NUMBER |
| `MANUFACTURER` | TEXT |
| `BRAND` | TEXT |
| `SUB_BRAND` | TEXT |

## 123. `nightly`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

## 124. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778853104117_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 125. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778845290894_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 126. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1779064486604_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 127. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1779064674157_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 128. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778625638347_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 129. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778978258451_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 130. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1779064664782_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 131. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778840139465_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 132. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778854475570_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 133. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778891653436_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 134. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778967166355_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 135. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778835953765_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 136. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778855374903_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 137. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778846193858_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 138. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778852205480_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 139. `sales-summary`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product/nightly/`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int |
| `total_revenue` | float |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778978235793_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 140. `amazon-reviews`  —  domain `customer`

### Input model — `adls://yogeshdata/amazon-reviews/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `adls://lowerenvsdatanxd/amazon-reviews/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `user_id` | string |
| `item_id` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `verified_purchase` | boolean |
| `helpful_vote` | int |
| `total_vote` | int |
| `category` | string |
| `product_title` | string |
| `average_rating` | float |
| `price` | float |
| `brand` | string |
| `main_category` | string |

## 141. `amazon-review`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/amazon-reviews/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `user_id` | string |
| `item_id` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `verified_purchase` | boolean |
| `helpful_vote` | int |
| `total_vote` | int |
| `category` | string |
| `product_title` | string |
| `average_rating` | float |
| `price` | float |
| `brand` | string |
| `main_category` | string |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS_TEST.AMAZON_REVIEW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `AVERAGE_RATING` | FLOAT |
| `BRAND` | TEXT |
| `CATEGORY` | TEXT |
| `HELPFUL_VOTE` | NUMBER |
| `ITEM_ID` | TEXT |
| `MAIN_CATEGORY` | TEXT |
| `PRICE` | FLOAT |
| `PRODUCT_TITLE` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `TOTAL_VOTE` | NUMBER |
| `USER_ID` | TEXT |
| `VERIFIED_PURCHASE` | BOOLEAN |

## 142. `amazon-reviews`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/amazon-reviews/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `user_id` | string |
| `item_id` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `verified_purchase` | boolean |
| `helpful_vote` | int |
| `total_vote` | int |
| `category` | string |
| `product_title` | string |
| `average_rating` | float |
| `price` | float |
| `brand` | string |
| `main_category` | string |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEWS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `USER_ID` | TEXT |
| `ITEM_ID` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `VERIFIED_PURCHASE` | BOOLEAN |
| `HELPFUL_VOTE` | NUMBER |
| `TOTAL_VOTE` | NUMBER |
| `CATEGORY` | TEXT |
| `PRODUCT_TITLE` | TEXT |
| `AVERAGE_RATING` | FLOAT |
| `PRICE` | FLOAT |
| `BRAND` | TEXT |
| `MAIN_CATEGORY` | TEXT |

## 143. `amazon-review`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/amazon-reviews/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `user_id` | string |
| `item_id` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `verified_purchase` | boolean |
| `helpful_vote` | int |
| `total_vote` | int |
| `category` | string |
| `product_title` | string |
| `average_rating` | float |
| `price` | float |
| `brand` | string |
| `main_category` | string |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `AVERAGE_RATING` | FLOAT |
| `BRAND` | TEXT |
| `CATEGORY` | TEXT |
| `HELPFUL_VOTE` | NUMBER |
| `ITEM_ID` | TEXT |
| `MAIN_CATEGORY` | TEXT |
| `PRICE` | FLOAT |
| `PRODUCT_TITLE` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `TOTAL_VOTE` | NUMBER |
| `USER_ID` | TEXT |
| `VERIFIED_PURCHASE` | BOOLEAN |

## 144. `amazon-reviews`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/amazon-reviews-test/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `adls://yogeshdata/amazon-reviews/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

## 145. `amazon-review`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/amazon-reviews-test/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS_TEST.AMAZON_REVIEW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `AVERAGE_RATING` | FLOAT |
| `BRAND` | TEXT |
| `CATEGORY` | TEXT |
| `HELPFUL_VOTE` | NUMBER |
| `ITEM_ID` | TEXT |
| `MAIN_CATEGORY` | TEXT |
| `PRICE` | FLOAT |
| `PRODUCT_TITLE` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `TOTAL_VOTE` | NUMBER |
| `USER_ID` | TEXT |
| `VERIFIED_PURCHASE` | BOOLEAN |

## 146. `amazon-reviews`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/amazon-reviews-test/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEWS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `USER_ID` | TEXT |
| `ITEM_ID` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `VERIFIED_PURCHASE` | BOOLEAN |
| `HELPFUL_VOTE` | NUMBER |
| `TOTAL_VOTE` | NUMBER |
| `CATEGORY` | TEXT |
| `PRODUCT_TITLE` | TEXT |
| `AVERAGE_RATING` | FLOAT |
| `PRICE` | FLOAT |
| `BRAND` | TEXT |
| `MAIN_CATEGORY` | TEXT |

## 147. `amazon-review`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/amazon-reviews-test/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `AVERAGE_RATING` | FLOAT |
| `BRAND` | TEXT |
| `CATEGORY` | TEXT |
| `HELPFUL_VOTE` | NUMBER |
| `ITEM_ID` | TEXT |
| `MAIN_CATEGORY` | TEXT |
| `PRICE` | FLOAT |
| `PRODUCT_TITLE` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `TOTAL_VOTE` | NUMBER |
| `USER_ID` | TEXT |
| `VERIFIED_PURCHASE` | BOOLEAN |

## 148. `dividend-sustainability`  —  domain `market-intelligence`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `bank` | string |
| `year` | int32 |
| `dividend_per_share` | double |
| `operating_cash_flow_thousands` | double |
| `dividend_yield_trend` | double |
| `ocf_trend` | double |
| `dividend_growth_vs_ocf_growth` | double |
| `sustainability_flag` | string |

### Output model — `LOWERENVS_DB.COMPETITOR_GROWTH_ANALYSIS.DIVIDEND_SUSTAINABILITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `BANK` | TEXT |
| `YEAR` | NUMBER |
| `DIVIDEND_PER_SHARE` | NUMBER |
| `OPERATING_CASH_FLOW_THOUSANDS` | FLOAT |
| `DIVIDEND_YIELD_TREND` | FLOAT |
| `OCF_TREND` | FLOAT |
| `DIVIDEND_GROWTH_VS_OCF_GROWTH` | FLOAT |
| `SUSTAINABILITY_FLAG` | TEXT |

## 149. `delta-log`  —  domain `product`

### Input model — `adls://yogeshdata/output/NEXT_DATA_OS/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `txn` | struct<appId: string, version: int64, lastUpdated: int64> |
| `add` | struct<path: string, partitionValues: map<string, string ('partitionValues')>, size: int64, modificationTime: int64, dataChange: bool, tags: map<string, string ('tags')>, deletionVector: struct<storageType: string, pathOrInlineDv: string, offset: int32, sizeInBytes: int32, cardinality: int64, maxRowIndex: int64>, baseRowId: int64, defaultRowCommitVersion: int64, clusteringProvider: string, stats: string, stats_parsed: struct<numRecords: int64, minValues: struct<geo_id: string, customer_id: int64, product_id: string, volume_change_percentage: double, initial_standard_shelf_price: double, final_standard_shelf_price: double, start_date: timestamp[ns]>, maxValues: struct<geo_id: string, customer_id: int64, product_id: string, volume_change_percentage: double, initial_standard_shelf_price: double, final_standard_shelf_price: double, start_date: timestamp[ns]>, nullCount: struct<geo_id: int64, customer_id: int64, product_id: int64, volume_change_percentage: int64, initial_standard_shelf_price: int64, final_standard_shelf_price: int64, start_date: int64>>> |
| `remove` | struct<path: string, deletionTimestamp: int64, dataChange: bool, extendedFileMetadata: bool, partitionValues: map<string, string ('partitionValues')>, size: int64, deletionVector: struct<storageType: string, pathOrInlineDv: string, offset: int32, sizeInBytes: int32, cardinality: int64, maxRowIndex: int64>, baseRowId: int64, defaultRowCommitVersion: int64> |
| `metaData` | struct<id: string, name: string, description: string, format: struct<provider: string, options: map<string, string ('options')>>, schemaString: string, partitionColumns: list<element: string>, configuration: map<string, string ('configuration')>, createdTime: int64> |
| `protocol` | struct<minReaderVersion: int32, minWriterVersion: int32, readerFeatures: list<element: string>, writerFeatures: list<element: string>> |
| `domainMetadata` | struct<domain: string, configuration: string, removed: bool> |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `txn` | struct<appId: string, version: int64, lastUpdated: int64> |
| `add` | struct<path: string, partitionValues: map<string, string ('partitionValues')>, size: int64, modificationTime: int64, dataChange: bool, tags: map<string, string ('tags')>, deletionVector: struct<storageType: string, pathOrInlineDv: string, offset: int32, sizeInBytes: int32, cardinality: int64, maxRowIndex: int64>, baseRowId: int64, defaultRowCommitVersion: int64, clusteringProvider: string, stats_parsed: struct<numRecords: int64, minValues: struct<pickup_zip: string, trip_count: int32, avg_fare: double>, maxValues: struct<pickup_zip: string, trip_count: int32, avg_fare: double>, nullCount: struct<pickup_zip: int64, trip_count: int64, avg_fare: int64>, tightBounds: bool>> |
| `remove` | struct<path: string, deletionTimestamp: int64, dataChange: bool, extendedFileMetadata: bool, partitionValues: map<string, string ('partitionValues')>, size: int64, deletionVector: struct<storageType: string, pathOrInlineDv: string, offset: int32, sizeInBytes: int32, cardinality: int64, maxRowIndex: int64>, baseRowId: int64, defaultRowCommitVersion: int64> |
| `metaData` | struct<id: string, name: string, description: string, format: struct<provider: string, options: map<string, string ('options')>>, schemaString: string, partitionColumns: list<element: string>, configuration: map<string, string ('configuration')>, createdTime: int64> |
| `protocol` | struct<minReaderVersion: int32, minWriterVersion: int32, readerFeatures: list<element: string>, writerFeatures: list<element: string>> |
| `domainMetadata` | struct<domain: string, configuration: string, removed: bool> |

## 150. `tables`  —  domain `product`

### Input model — `adls://yogeshdata/sourcedata/SAPPM/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `product_code` | string |
| `gtin` | string |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | bool |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int64 |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_code` | int64 |
| `gtin` | int64 |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | bool |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int64 |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

## 151. `walmart-sales`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_code` | int64 |
| `gtin` | int64 |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | bool |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int64 |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `LOWERENVS_DB.WHOLESALE_SALES.WALMART_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_CODE` | NUMBER |
| `GTIN` | NUMBER |
| `TITLE` | TEXT |
| `SHORT_DESCRIPTION` | TEXT |
| `PRODUCT_DESCRIPTION` | TEXT |
| `IS_ACTIVE_PRODUCT` | BOOLEAN |
| `IRI_CATEGORY_NAME` | TEXT |
| `IRI_SUBCATEGORY_NAME` | TEXT |
| `PACK_SIZE` | NUMBER |
| `MANUFACTURER` | TEXT |
| `BRAND` | TEXT |
| `SUB_BRAND` | TEXT |

## 152. `product-catalog`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_code` | int64 |
| `gtin` | int64 |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | bool |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int64 |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `LOWERENVS_DB.PRODUCT_CATALOG.PRODUCT_CATALOG`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_CODE` | NUMBER |
| `GTIN` | NUMBER |
| `TITLE` | TEXT |
| `SHORT_DESCRIPTION` | TEXT |
| `PRODUCT_DESCRIPTION` | TEXT |
| `IS_ACTIVE_PRODUCT` | BOOLEAN |
| `IRI_CATEGORY_NAME` | TEXT |
| `IRI_SUBCATEGORY_NAME` | TEXT |
| `PACK_SIZE` | NUMBER |
| `MANUFACTURER` | TEXT |
| `BRAND` | TEXT |
| `SUB_BRAND` | TEXT |

## 153. `home-loan-rates`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/547f2d92-8194-4972-b5ef-cf4357320dca/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `bank` | string |
| `product` | string |
| `loan_term` | int64 |
| `min_lvr` | int64 |
| `max_lvr` | int64 |
| `min_loan` | int64 |
| `max_loan` | int64 |
| `rate` | decimal128(6, 2) |

### Output model — `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.HOME_LOAN_RATES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `BANK` | TEXT |
| `PRODUCT` | TEXT |
| `LOAN_TERM` | NUMBER |
| `MIN_LVR` | NUMBER |
| `MAX_LVR` | NUMBER |
| `MIN_LOAN` | NUMBER |
| `MAX_LOAN` | NUMBER |
| `RATE` | NUMBER |

## 154. `growth`  —  domain `market-intelligence`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/639ec880-0c84-41ef-b78c-954fe0027bd2/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `symbol` | string |
| `date` | timestamp[us] |
| `close` | double |
| `annual_return` | double |
| `net_income` | double |
| `total_revenue` | double |
| `revenue_growth` | double |
| `net_income_growth` | double |

### Output model — `LOWERENVS_DB.COMPETITOR_GROWTH_ANALYSIS.GROWTH`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `SYMBOL` | TEXT |
| `DATE` | TIMESTAMP_TZ |
| `CLOSE` | FLOAT |
| `ANNUAL_RETURN` | FLOAT |
| `NET_INCOME` | FLOAT |
| `TOTAL_REVENUE` | FLOAT |
| `REVENUE_GROWTH` | FLOAT |
| `NET_INCOME_GROWTH` | FLOAT |

## 155. `69bdd885-da4b-4708-ac31-40ba294165d2`  —  domain `customer`

### Input model — `adls://yogeshdata/amazon-reviews/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/69bdd885-da4b-4708-ac31-40ba294165d2/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `user_id` | string |
| `item_id` | string |
| `rating` | double |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date32[day] |
| `verified_purchase` | bool |
| `helpful_vote` | int32 |
| `total_vote` | int32 |
| `category` | string |
| `product_title` | string |
| `average_rating` | double |
| `price` | double |
| `brand` | string |
| `main_category` | string |

## 156. `amazon-review`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/69bdd885-da4b-4708-ac31-40ba294165d2/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `user_id` | string |
| `item_id` | string |
| `rating` | double |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date32[day] |
| `verified_purchase` | bool |
| `helpful_vote` | int32 |
| `total_vote` | int32 |
| `category` | string |
| `product_title` | string |
| `average_rating` | double |
| `price` | double |
| `brand` | string |
| `main_category` | string |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS_TEST.AMAZON_REVIEW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `AVERAGE_RATING` | FLOAT |
| `BRAND` | TEXT |
| `CATEGORY` | TEXT |
| `HELPFUL_VOTE` | NUMBER |
| `ITEM_ID` | TEXT |
| `MAIN_CATEGORY` | TEXT |
| `PRICE` | FLOAT |
| `PRODUCT_TITLE` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `TOTAL_VOTE` | NUMBER |
| `USER_ID` | TEXT |
| `VERIFIED_PURCHASE` | BOOLEAN |

## 157. `amazon-reviews`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/69bdd885-da4b-4708-ac31-40ba294165d2/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `user_id` | string |
| `item_id` | string |
| `rating` | double |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date32[day] |
| `verified_purchase` | bool |
| `helpful_vote` | int32 |
| `total_vote` | int32 |
| `category` | string |
| `product_title` | string |
| `average_rating` | double |
| `price` | double |
| `brand` | string |
| `main_category` | string |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEWS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `USER_ID` | TEXT |
| `ITEM_ID` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `VERIFIED_PURCHASE` | BOOLEAN |
| `HELPFUL_VOTE` | NUMBER |
| `TOTAL_VOTE` | NUMBER |
| `CATEGORY` | TEXT |
| `PRODUCT_TITLE` | TEXT |
| `AVERAGE_RATING` | FLOAT |
| `PRICE` | FLOAT |
| `BRAND` | TEXT |
| `MAIN_CATEGORY` | TEXT |

## 158. `amazon-review`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/69bdd885-da4b-4708-ac31-40ba294165d2/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `user_id` | string |
| `item_id` | string |
| `rating` | double |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date32[day] |
| `verified_purchase` | bool |
| `helpful_vote` | int32 |
| `total_vote` | int32 |
| `category` | string |
| `product_title` | string |
| `average_rating` | double |
| `price` | double |
| `brand` | string |
| `main_category` | string |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `AVERAGE_RATING` | FLOAT |
| `BRAND` | TEXT |
| `CATEGORY` | TEXT |
| `HELPFUL_VOTE` | NUMBER |
| `ITEM_ID` | TEXT |
| `MAIN_CATEGORY` | TEXT |
| `PRICE` | FLOAT |
| `PRODUCT_TITLE` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `TOTAL_VOTE` | NUMBER |
| `USER_ID` | TEXT |
| `VERIFIED_PURCHASE` | BOOLEAN |

## 159. `7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

## 160. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 161. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 162. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 163. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 164. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 165. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 166. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 167. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 168. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 169. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 170. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 171. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 172. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 173. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 174. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 175. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 176. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 177. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 178. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 179. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 180. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 181. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 182. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 183. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 184. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 185. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 186. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 187. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 188. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 189. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 190. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 191. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 192. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 193. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 194. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 195. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 196. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 197. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 198. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 199. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 200. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 201. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 202. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 203. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 204. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 205. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 206. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 207. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 208. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 209. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 210. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 211. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 212. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 213. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 214. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 215. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 216. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 217. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 218. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 219. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 220. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 221. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 222. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 223. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 224. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 225. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 226. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 227. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 228. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 229. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 230. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 231. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 232. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 233. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 234. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 235. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 236. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 237. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 238. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 239. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 240. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 241. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 242. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 243. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 244. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 245. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 246. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 247. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 248. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 249. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 250. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 251. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 252. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 253. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 254. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 255. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 256. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 257. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 258. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 259. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 260. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 261. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 262. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 263. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 264. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 265. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 266. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 267. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 268. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 269. `tables`  —  domain `product`

### Input model — `adls://yogeshdata/podcasts-source/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `id` | int |
| `title` | string |
| `description` | string |
| `author` | string |
| `episode_id` | int |
| `episode_title` | string |
| `episode_description` | string |
| `episode_duration` | string |
| `release_date` | date |
| `plays` | int |
| `genre` | string |
| `language` | string |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `id` | int32 |
| `title` | string |
| `description` | string |
| `author` | string |
| `episode_id` | int32 |
| `episode_title` | string |
| `episode_description` | string |
| `episode_duration` | string |
| `release_date` | date32[day] |
| `plays` | int32 |
| `genre` | string |
| `language` | string |

## 270. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778853104117_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 271. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778845290894_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 272. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1779064486604_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 273. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1779064674157_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 274. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778625638347_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 275. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778978258451_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 276. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1779064664782_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 277. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778840139465_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 278. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778854475570_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 279. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778891653436_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 280. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778967166355_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 281. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778835953765_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 282. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778855374903_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 283. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778846193858_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 284. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778852205480_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 285. `sales-summary`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_name` | string |
| `total_quantity` | int64 |
| `total_revenue` | double |

### Output model — `LOWERENVS_DB.SALES_REPORT_1778978235793_CLI_SF_SEQ.SALES_SUMMARY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_NAME` | TEXT |
| `TOTAL_QUANTITY` | NUMBER |
| `TOTAL_REVENUE` | FLOAT |

## 286. `trending-sales`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `MOMENTUM_SCORE` | FLOAT |
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `TREND_RANK` | NUMBER |
| `TREND_STRENGTH` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 287. `emerging-products`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/dd975e49-952e-42ae-8ff0-5a4d802f40ae/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `product_name` | string |
| `primary_channel` | string |
| `lagging_channels` | string |
| `sales_change_percent` | double |
| `attention_score` | double |
| `first_detected_date` | date32[day] |
| `recommendation_flag` | bool |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.EMERGING_PRODUCTS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ATTENTION_SCORE` | FLOAT |
| `FIRST_DETECTED_DATE` | TIMESTAMP_NTZ |
| `LAGGING_CHANNELS` | TEXT |
| `PRIMARY_CHANNEL` | TEXT |
| `PRODUCT_ID` | TEXT |
| `PRODUCT_NAME` | TEXT |
| `RECOMMENDATION_FLAG` | BOOLEAN |
| `SALES_CHANGE_PERCENT` | FLOAT |

## 288. `term-deposits`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/dea1e340-213d-4bf1-bc3a-9ae9b11a7219/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `name` | string |
| `bank` | string |
| `min_amount` | int64 |
| `max_amount` | int64 |
| `min_term` | int64 |
| `max_term` | int64 |
| `monthly_rate` | decimal128(4, 2) |
| `annual_rate` | decimal128(4, 2) |
| `maturity_rate` | decimal128(4, 2) |

### Output model — `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.TERM_DEPOSITS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `NAME` | TEXT |
| `BANK` | TEXT |
| `MIN_AMOUNT` | NUMBER |
| `MAX_AMOUNT` | NUMBER |
| `MIN_TERM` | NUMBER |
| `MAX_TERM` | NUMBER |
| `MONTHLY_RATE` | NUMBER |
| `ANNUAL_RATE` | NUMBER |
| `MATURITY_RATE` | NUMBER |

## 289. `lowerenvsdatanxd`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

## 290. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 291. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 292. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 293. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 294. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 295. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 296. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 297. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 298. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 299. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 300. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 301. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 302. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 303. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 304. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 305. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 306. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 307. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 308. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 309. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 310. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 311. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 312. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 313. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 314. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 315. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 316. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 317. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 318. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 319. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 320. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 321. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 322. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 323. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 324. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 325. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 326. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 327. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 328. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 329. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 330. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 331. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 332. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 333. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 334. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 335. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 336. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 337. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 338. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 339. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 340. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 341. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 342. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 343. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 344. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 345. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 346. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 347. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 348. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 349. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 350. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 351. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 352. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 353. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 354. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 355. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 356. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 357. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 358. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 359. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 360. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 361. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 362. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 363. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 364. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 365. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 366. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 367. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 368. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 369. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 370. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 371. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 372. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 373. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 374. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 375. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 376. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 377. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 378. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 379. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 380. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 381. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 382. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 383. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 384. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 385. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 386. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 387. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 388. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 389. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 390. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 391. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 392. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 393. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 394. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 395. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 396. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 397. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 398. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 399. `point-of-sale-revenue`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/online-sales/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `id` | int |
| `revenue` | float |
| `transaction_id` | string |
| `store_id` | string |
| `cashier_id` | string |
| `transaction_date` | date |
| `payment_method` | string |
| `quantity_sold` | int |
| `unit_price` | float |
| `total_amount` | float |
| `discount_applied` | float |
| `tax_amount` | float |
| `created_at` | date |
| `updated_at` | date |

### Output model — `LOWERENVS_DB.ONLINE_SALES_RAW.POINT_OF_SALE_REVENUE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | NUMBER |
| `REVENUE` | NUMBER |
| `TRANSACTION_ID` | TEXT |
| `STORE_ID` | TEXT |
| `CASHIER_ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PAYMENT_METHOD` | TEXT |
| `QUANTITY_SOLD` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `TOTAL_AMOUNT` | FLOAT |
| `DISCOUNT_APPLIED` | FLOAT |
| `TAX_AMOUNT` | FLOAT |
| `CREATED_AT` | TIMESTAMP_NTZ |
| `UPDATED_AT` | TIMESTAMP_NTZ |

## 400. `point-of-sale-revenue`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/online-sales/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `id` | int |
| `revenue` | float |
| `transaction_id` | string |
| `store_id` | string |
| `cashier_id` | string |
| `transaction_date` | date |
| `payment_method` | string |
| `quantity_sold` | int |
| `unit_price` | float |
| `total_amount` | float |
| `discount_applied` | float |
| `tax_amount` | float |
| `created_at` | date |
| `updated_at` | date |

### Output model — `LOWERENVS_DB.ONLINE_SALES.POINT_OF_SALE_REVENUE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | NUMBER |
| `REVENUE` | NUMBER |
| `TRANSACTION_ID` | TEXT |
| `STORE_ID` | TEXT |
| `CASHIER_ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PAYMENT_METHOD` | TEXT |
| `QUANTITY_SOLD` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `TOTAL_AMOUNT` | FLOAT |
| `DISCOUNT_APPLIED` | FLOAT |
| `TAX_AMOUNT` | FLOAT |
| `CREATED_AT` | TIMESTAMP_NTZ |
| `UPDATED_AT` | TIMESTAMP_NTZ |

## 401. `sales-value`  —  domain `sales`

### Input model — `adls://yogeshdata//`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `id` | string |
| `transaction_date` | date |
| `product_id` | string |
| `quantity` | int |
| `unit_price` | float |
| `region` | string |
| `processed_at` | date |

### Output model — `adls://lowerenvsdatanxd/sales-value/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `id` | string |
| `transaction_date` | date |
| `product_id` | string |
| `quantity` | int |
| `unit_price` | float |
| `region` | string |
| `processed_at` | date |

## 402. `gross-sales`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/sales-value/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `id` | string |
| `transaction_date` | date |
| `product_id` | string |
| `quantity` | int |
| `unit_price` | float |
| `region` | string |
| `processed_at` | date |

### Output model — `LOWERENVS_DB.SALES_VALUE.GROSS_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PRODUCT_ID` | TEXT |
| `QUANTITY` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `REGION` | TEXT |
| `PROCESSED_AT` | TEXT |

## 403. `company-info`  —  domain `other`

### Input model — `adls://lowerenvsdatanxd/sec-openfigi/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `COMPANY_ID` | string |
| `COMPANY_NAME` | string |
| `ENTITY_LEVEL` | string |
| `EIN` | int |
| `CIK` | int |
| `LEI` | string |
| `PERMID_COMPANY_ID` | int |
| `PRIMARY_TICKER` | string |
| `PRIMARY_EXCHANGE_CODE` | string |
| `PRIMARY_EXCHANGE_NAME` | string |
| `GLOBAL_TICKERS` | string |

### Output model — `LOWERENVS_DB.SEC_OPENFIGI.COMPANY_INFO`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `COMPANY_ID` | TEXT |
| `COMPANY_NAME` | TEXT |
| `ENTITY_LEVEL` | TEXT |
| `EIN` | TEXT |
| `CIK` | TEXT |
| `LEI` | TEXT |
| `PERMID_COMPANY_ID` | TEXT |
| `PRIMARY_TICKER` | TEXT |
| `PRIMARY_EXCHANGE_CODE` | TEXT |
| `PRIMARY_EXCHANGE_NAME` | TEXT |
| `GLOBAL_TICKERS` | TEXT |

## 404. `company-info`  —  domain `other`

### Input model — `adls://lowerenvsdatanxd/sec-openfigi/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `COMPANY_ID` | string |
| `COMPANY_NAME` | string |
| `ENTITY_LEVEL` | string |
| `EIN` | int |
| `CIK` | int |
| `LEI` | string |
| `PERMID_COMPANY_ID` | int |
| `PRIMARY_TICKER` | string |
| `PRIMARY_EXCHANGE_CODE` | string |
| `PRIMARY_EXCHANGE_NAME` | string |
| `GLOBAL_TICKERS` | string |

### Output model — `LOWERENVS_DB.SEC_FILINGS.COMPANY_INFO`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `COMPANY_ID` | TEXT |
| `COMPANY_NAME` | TEXT |
| `ENTITY_LEVEL` | TEXT |
| `EIN` | TEXT |
| `CIK` | TEXT |
| `LEI` | TEXT |
| `PERMID_COMPANY_ID` | TEXT |
| `PRIMARY_TICKER` | TEXT |
| `PRIMARY_EXCHANGE_CODE` | TEXT |
| `PRIMARY_EXCHANGE_NAME` | TEXT |
| `GLOBAL_TICKERS` | TEXT |

## 405. `testing`  —  domain `other`

### Input model — `adls://yogeshdata/testing/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `id` | string |
| `value` | int |

### Output model — `adls://lowerenvsdatanxd/testing/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `id` | string |
| `value` | int |

## 406. `wholesale-sales`  —  domain `sales`

### Input model — `adls://yogeshdata/sourcedata/SAPPM/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `product_code` | string |
| `gtin` | string |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | bool |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int64 |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `adls://lowerenvsdatanxd/wholesale-sales/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_code` | int |
| `gtin` | int |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | boolean |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

## 407. `walmart-sales`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/wholesale-sales/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_code` | int |
| `gtin` | int |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | boolean |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `LOWERENVS_DB.WHOLESALE_SALES.WALMART_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_CODE` | NUMBER |
| `GTIN` | NUMBER |
| `TITLE` | TEXT |
| `SHORT_DESCRIPTION` | TEXT |
| `PRODUCT_DESCRIPTION` | TEXT |
| `IS_ACTIVE_PRODUCT` | BOOLEAN |
| `IRI_CATEGORY_NAME` | TEXT |
| `IRI_SUBCATEGORY_NAME` | TEXT |
| `PACK_SIZE` | NUMBER |
| `MANUFACTURER` | TEXT |
| `BRAND` | TEXT |
| `SUB_BRAND` | TEXT |

## 408. `product-catalog`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/wholesale-sales/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_code` | int |
| `gtin` | int |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | boolean |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `LOWERENVS_DB.PRODUCT_CATALOG.PRODUCT_CATALOG`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_CODE` | NUMBER |
| `GTIN` | NUMBER |
| `TITLE` | TEXT |
| `SHORT_DESCRIPTION` | TEXT |
| `PRODUCT_DESCRIPTION` | TEXT |
| `IS_ACTIVE_PRODUCT` | BOOLEAN |
| `IRI_CATEGORY_NAME` | TEXT |
| `IRI_SUBCATEGORY_NAME` | TEXT |
| `PACK_SIZE` | NUMBER |
| `MANUFACTURER` | TEXT |
| `BRAND` | TEXT |
| `SUB_BRAND` | TEXT |

## 409. `amazon-review`  —  domain `customer`

### Input model — `adls://yogeshdata/amazon-reviews/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS_TEST.AMAZON_REVIEW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `AVERAGE_RATING` | FLOAT |
| `BRAND` | TEXT |
| `CATEGORY` | TEXT |
| `HELPFUL_VOTE` | NUMBER |
| `ITEM_ID` | TEXT |
| `MAIN_CATEGORY` | TEXT |
| `PRICE` | FLOAT |
| `PRODUCT_TITLE` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `TOTAL_VOTE` | NUMBER |
| `USER_ID` | TEXT |
| `VERIFIED_PURCHASE` | BOOLEAN |

## 410. `amazon-reviews`  —  domain `customer`

### Input model — `adls://yogeshdata/amazon-reviews/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEWS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `USER_ID` | TEXT |
| `ITEM_ID` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `VERIFIED_PURCHASE` | BOOLEAN |
| `HELPFUL_VOTE` | NUMBER |
| `TOTAL_VOTE` | NUMBER |
| `CATEGORY` | TEXT |
| `PRODUCT_TITLE` | TEXT |
| `AVERAGE_RATING` | FLOAT |
| `PRICE` | FLOAT |
| `BRAND` | TEXT |
| `MAIN_CATEGORY` | TEXT |

## 411. `amazon-review`  —  domain `customer`

### Input model — `adls://yogeshdata/amazon-reviews/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `AVERAGE_RATING` | FLOAT |
| `BRAND` | TEXT |
| `CATEGORY` | TEXT |
| `HELPFUL_VOTE` | NUMBER |
| `ITEM_ID` | TEXT |
| `MAIN_CATEGORY` | TEXT |
| `PRICE` | FLOAT |
| `PRODUCT_TITLE` | TEXT |
| `RATING` | FLOAT |
| `REVIEW_TEXT` | TEXT |
| `REVIEW_TITLE` | TEXT |
| `TIMESTAMP` | TIMESTAMP_NTZ |
| `TOTAL_VOTE` | NUMBER |
| `USER_ID` | TEXT |
| `VERIFIED_PURCHASE` | BOOLEAN |

## 412. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 413. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 414. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 415. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 416. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 417. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 418. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 419. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 420. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 421. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 422. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 423. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 424. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 425. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 426. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 427. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 428. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 429. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 430. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 431. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 432. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 433. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 434. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 435. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 436. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 437. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 438. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 439. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 440. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 441. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 442. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 443. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 444. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 445. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 446. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 447. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 448. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 449. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 450. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 451. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 452. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 453. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 454. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 455. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 456. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 457. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 458. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 459. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 460. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 461. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 462. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 463. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 464. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 465. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 466. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 467. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 468. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 469. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 470. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 471. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 472. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 473. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 474. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 475. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 476. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 477. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 478. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 479. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 480. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 481. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 482. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 483. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 484. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 485. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 486. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 487. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 488. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 489. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 490. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 491. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 492. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 493. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 494. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 495. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 496. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 497. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 498. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 499. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 500. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 501. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 502. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 503. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 504. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 505. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 506. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 507. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 508. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 509. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 510. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 511. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 512. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 513. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 514. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 515. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 516. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 517. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 518. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 519. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 520. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 521. `gross-sales`  —  domain `sales`

### Input model — `adls://yogeshdata//`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `id` | string |
| `transaction_date` | date |
| `product_id` | string |
| `quantity` | int |
| `unit_price` | float |
| `region` | string |
| `processed_at` | date |

### Output model — `LOWERENVS_DB.SALES_VALUE.GROSS_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PRODUCT_ID` | TEXT |
| `QUANTITY` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `REGION` | TEXT |
| `PROCESSED_AT` | TEXT |

## 522. `walmart-sales`  —  domain `sales`

### Input model — `adls://yogeshdata/sourcedata/SAPPM/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `product_code` | string |
| `gtin` | string |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | bool |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int64 |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `LOWERENVS_DB.WHOLESALE_SALES.WALMART_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_CODE` | NUMBER |
| `GTIN` | NUMBER |
| `TITLE` | TEXT |
| `SHORT_DESCRIPTION` | TEXT |
| `PRODUCT_DESCRIPTION` | TEXT |
| `IS_ACTIVE_PRODUCT` | BOOLEAN |
| `IRI_CATEGORY_NAME` | TEXT |
| `IRI_SUBCATEGORY_NAME` | TEXT |
| `PACK_SIZE` | NUMBER |
| `MANUFACTURER` | TEXT |
| `BRAND` | TEXT |
| `SUB_BRAND` | TEXT |

## 523. `product-catalog`  —  domain `product`

### Input model — `adls://yogeshdata/sourcedata/SAPPM/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `product_code` | string |
| `gtin` | string |
| `title` | string |
| `short_description` | string |
| `product_description` | string |
| `is_active_product` | bool |
| `iri_category_name` | string |
| `iri_subcategory_name` | string |
| `pack_size` | int64 |
| `manufacturer` | string |
| `brand` | string |
| `sub_brand` | string |

### Output model — `LOWERENVS_DB.PRODUCT_CATALOG.PRODUCT_CATALOG`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_CODE` | NUMBER |
| `GTIN` | NUMBER |
| `TITLE` | TEXT |
| `SHORT_DESCRIPTION` | TEXT |
| `PRODUCT_DESCRIPTION` | TEXT |
| `IS_ACTIVE_PRODUCT` | BOOLEAN |
| `IRI_CATEGORY_NAME` | TEXT |
| `IRI_SUBCATEGORY_NAME` | TEXT |
| `PACK_SIZE` | NUMBER |
| `MANUFACTURER` | TEXT |
| `BRAND` | TEXT |
| `SUB_BRAND` | TEXT |

## 524. `fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc`  —  domain `product`

### Input model — `s3://lowerenvs-input-data-product/nxd-tutorials/`

_service `s3-input`, format `csv`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `merchant_name` | string |
| `creation_date` | string |
| `accounting_date` | string |
| `effective_date` | string |
| `country_code` | string |
| `payment_method` | string |
| `payment_method_type` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `industry` | string |
| `processing_fee_usd` | float |
| `fx_fee_usd` | float |
| `installment_fee_usd` | float |
| `other_income_usd` | float |
| `processing_cost_usd` | float |
| `tax_cost_usd` | float |
| `fx_cost_usd` | float |
| `chargeback_cost_usd` | float |
| `local_amount` | float |
| `usd_amount` | float |
| `gross_profit_usd` | float |
| `gross_margin_pct` | float |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `creation_date` | timestamp[ns] |
| `accounting_date` | date32[day] |
| `effective_date` | date32[day] |
| `merchant_name` | string |
| `country_code` | string |
| `payment_method` | string |
| `payment_method_type` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int64 |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `industry` | string |
| `processing_fee_usd` | decimal128(18, 6) |
| `fx_fee_usd` | decimal128(18, 6) |
| `installment_fee_usd` | decimal128(18, 6) |
| `other_income_usd` | decimal128(18, 6) |
| `processing_cost_usd` | decimal128(18, 6) |
| `tax_cost_usd` | decimal128(18, 6) |
| `fx_cost_usd` | decimal128(18, 6) |
| `chargeback_cost_usd` | decimal128(18, 6) |
| `local_amount` | decimal128(18, 6) |
| `usd_amount` | decimal128(18, 6) |
| `gross_profit_usd` | decimal128(18, 6) |
| `gross_margin_pct` | double |
| `load_time` | timestamp[ns] |

## 525. `17c1ac67-25f2-4d3c-8bf2-184d95b68bea`  —  domain `product`

### Input model — `s3://lowerenvs-input-data-product/nxd-tutorials/`

_service `s3-input`, format `csv`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `merchant_name` | string |
| `creation_date` | string |
| `accounting_date` | string |
| `effective_date` | string |
| `country_code` | string |
| `payment_method` | string |
| `payment_method_type` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `industry` | string |
| `processing_fee_usd` | float |
| `fx_fee_usd` | float |
| `installment_fee_usd` | float |
| `other_income_usd` | float |
| `processing_cost_usd` | float |
| `tax_cost_usd` | float |
| `fx_cost_usd` | float |
| `chargeback_cost_usd` | float |
| `local_amount` | float |
| `usd_amount` | float |
| `gross_profit_usd` | float |
| `gross_margin_pct` | float |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/17c1ac67-25f2-4d3c-8bf2-184d95b68bea/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `creation_date` | timestamp[ns] |
| `accounting_date` | date32[day] |
| `effective_date` | date32[day] |
| `country_code` | string |
| `payment_method` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `merchant_name` | string |
| `industry` | string |
| `payment_method_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int64 |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `processing_fee_usd` | decimal128(18, 6) |
| `fx_fee_usd` | decimal128(18, 6) |
| `installment_fee_usd` | decimal128(18, 6) |
| `other_income_usd` | decimal128(18, 6) |
| `total_revenue_usd` | decimal128(18, 6) |
| `processing_cost_usd` | decimal128(18, 6) |
| `tax_cost_usd` | decimal128(18, 6) |
| `fx_cost_usd` | decimal128(18, 6) |
| `chargeback_cost_usd` | decimal128(18, 6) |
| `total_cost_usd` | decimal128(18, 6) |
| `local_amount` | decimal128(18, 6) |
| `usd_amount` | decimal128(18, 6) |
| `gross_profit_usd` | decimal128(18, 6) |
| `gross_margin_pct` | double |
| `revenue_cost_ratio` | double |

## 526. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `RANK` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 527. `fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/17c1ac67-25f2-4d3c-8bf2-184d95b68bea/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `creation_date` | timestamp[ns] |
| `accounting_date` | date32[day] |
| `effective_date` | date32[day] |
| `country_code` | string |
| `payment_method` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `merchant_name` | string |
| `industry` | string |
| `payment_method_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int64 |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `processing_fee_usd` | decimal128(18, 6) |
| `fx_fee_usd` | decimal128(18, 6) |
| `installment_fee_usd` | decimal128(18, 6) |
| `other_income_usd` | decimal128(18, 6) |
| `total_revenue_usd` | decimal128(18, 6) |
| `processing_cost_usd` | decimal128(18, 6) |
| `tax_cost_usd` | decimal128(18, 6) |
| `fx_cost_usd` | decimal128(18, 6) |
| `chargeback_cost_usd` | decimal128(18, 6) |
| `total_cost_usd` | decimal128(18, 6) |
| `local_amount` | decimal128(18, 6) |
| `usd_amount` | decimal128(18, 6) |
| `gross_profit_usd` | decimal128(18, 6) |
| `gross_margin_pct` | double |
| `revenue_cost_ratio` | double |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `creation_date` | timestamp[ns] |
| `accounting_date` | date32[day] |
| `effective_date` | date32[day] |
| `merchant_name` | string |
| `country_code` | string |
| `payment_method` | string |
| `payment_method_type` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int64 |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `industry` | string |
| `processing_fee_usd` | decimal128(18, 6) |
| `fx_fee_usd` | decimal128(18, 6) |
| `installment_fee_usd` | decimal128(18, 6) |
| `other_income_usd` | decimal128(18, 6) |
| `processing_cost_usd` | decimal128(18, 6) |
| `tax_cost_usd` | decimal128(18, 6) |
| `fx_cost_usd` | decimal128(18, 6) |
| `chargeback_cost_usd` | decimal128(18, 6) |
| `local_amount` | decimal128(18, 6) |
| `usd_amount` | decimal128(18, 6) |
| `gross_profit_usd` | decimal128(18, 6) |
| `gross_margin_pct` | double |
| `load_time` | timestamp[ns] |

## 528. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `RANK` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 529. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `RANK` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 530. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `RANK` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 531. `playlist-listens`  —  domain `other`

### Input model — `adls://yogeshdata/playlists-compute-policy-test/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `collaborative` | boolean |
| `pid` | int |
| `modified_at` | int |
| `num_tracks` | int |
| `num_albums` | int |
| `num_followers` | int |
| `num_edits` | int |
| `duration_ms` | int |
| `num_artists` | int |
| `description` | string |

### Output model — `adls://yogeshdata/playlist-listens/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `playlist-name` | string |
| `collaborative` | boolean |
| `pid` | int |
| `modified_at` | int |
| `num_tracks` | int |
| `num_albums` | int |
| `num_followers` | int |
| `num_edits` | int |
| `duration_ms` | int |
| `num_artists` | int |
| `description` | string |
| `reproductions` | int |

## 532. `walmart`  —  domain `sales`

### Input model — `adls://yogeshdata/storesales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `﻿wm_item_nbr` | int |
| `store_nbr` | int |
| `bus_dt` | date |
| `vendor_nbr` | int |
| `vendor_name` | string |

### Output model — `adls://yogeshdata/walmart/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `﻿wm_item_nbr` | int |
| `store_nbr` | int |
| `bus_dt` | date |
| `vendor_nbr` | int |
| `vendor_name` | string |
| `units_sold` | int |

## 533. `7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b`  —  domain `product`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

## 534. `lowerenvsdatanxd`  —  domain `product`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

## 535. `lowerenvs-output-data-product`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

## 536. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 537. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 538. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 539. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 540. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 541. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 542. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 543. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 544. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 545. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 546. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 547. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 548. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 549. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 550. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 551. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 552. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 553. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 554. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 555. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 556. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 557. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 558. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 559. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 560. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 561. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 562. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 563. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 564. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 565. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 566. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 567. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 568. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 569. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 570. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 571. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 572. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 573. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 574. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 575. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 576. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 577. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 578. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 579. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 580. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 581. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 582. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 583. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 584. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 585. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 586. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 587. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 588. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 589. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 590. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 591. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 592. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 593. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 594. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 595. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 596. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 597. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 598. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 599. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 600. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 601. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 602. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 603. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 604. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 605. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 606. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 607. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 608. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 609. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 610. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 611. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 612. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 613. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 614. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 615. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 616. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 617. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 618. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 619. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 620. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 621. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 622. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 623. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 624. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 625. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 626. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 627. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 628. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 629. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 630. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 631. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 632. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 633. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 634. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 635. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 636. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 637. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 638. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 639. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 640. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 641. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 642. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 643. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 644. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 645. `sf-product-momentum`  —  domain `sales`

### Input model — `LOWERENVS_DB.SALES_INFLUENCE_INSIGHTS_SF.SF_CHANNEL_PERFORMANCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `PERFORMANCE_INDEX` | FLOAT |
| `UNITS_LAST_7D` | NUMBER |
| `UNITS_PREV_7D` | NUMBER |
| `REVENUE_CHANGE_PCT` | FLOAT |
| `TREND_DIRECTION` | TEXT |
| `REVENUE` | FLOAT |
| `PERIOD_END_DATE` | TIMESTAMP_NTZ |

### Output model — `LOWERENVS_DB.SALES_INFLUENCE_INSIGHTS_SF.SF_PRODUCT_MOMENTUM`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `PERFORMANCE_INDEX` | FLOAT |
| `UNITS_LAST_7D` | NUMBER |
| `UNITS_PREV_7D` | NUMBER |
| `REVENUE_CHANGE_PCT` | FLOAT |
| `TREND_DIRECTION` | TEXT |
| `TREND_STRENGTH` | FLOAT |
| `MOMENTUM_SCORE` | FLOAT |
| `MOMENTUM_RANK` | NUMBER |
| `REVENUE` | FLOAT |
| `PERIOD_END_DATE` | TIMESTAMP_NTZ |

## 646. `channel-sales-velocity`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `RANK` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 647. `lowerenvs-output-data-product`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

## 648. `trending-sales`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `MOMENTUM_SCORE` | FLOAT |
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `TREND_RANK` | NUMBER |
| `TREND_STRENGTH` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 649. `d68a1bdc-4b0f-425f-b589-d6b14369bda3`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

## 650. `trending-sales`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `MOMENTUM_SCORE` | FLOAT |
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `TREND_RANK` | NUMBER |
| `TREND_STRENGTH` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 651. `d68a1bdc-4b0f-425f-b589-d6b14369bda3`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

## 652. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 653. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 654. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 655. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 656. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 657. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 658. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 659. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 660. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 661. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 662. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 663. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 664. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 665. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 666. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 667. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 668. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 669. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 670. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 671. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 672. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 673. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 674. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 675. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 676. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 677. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 678. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 679. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 680. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 681. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 682. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 683. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 684. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 685. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 686. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 687. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 688. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 689. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 690. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 691. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 692. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 693. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 694. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 695. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 696. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 697. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 698. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 699. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 700. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 701. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 702. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 703. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 704. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 705. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 706. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 707. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 708. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 709. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 710. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 711. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 712. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 713. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 714. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 715. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 716. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 717. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 718. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 719. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 720. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 721. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 722. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 723. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 724. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 725. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 726. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 727. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 728. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 729. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 730. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 731. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 732. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 733. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 734. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 735. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 736. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 737. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 738. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 739. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 740. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 741. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 742. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 743. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 744. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 745. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 746. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 747. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 748. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 749. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 750. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 751. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 752. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 753. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 754. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 755. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 756. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 757. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 758. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 759. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 760. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `SALES_CHANNEL` | TEXT |
| `REGION` | TEXT |
| `VELOCITY_SCORE` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_TREND` | TEXT |

## 761. `trending-sales`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd//`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | int |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `MOMENTUM_SCORE` | FLOAT |
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `TREND_RANK` | NUMBER |
| `TREND_STRENGTH` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 762. `trending-sales`  —  domain `sales`

### Input model — `adls://yogeshdata/multi-channel-sales/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `MOMENTUM_SCORE` | FLOAT |
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `TREND_RANK` | NUMBER |
| `TREND_STRENGTH` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 763. `trending-sales`  —  domain `sales`

### Input model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `MOMENTUM_SCORE` | FLOAT |
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `TREND_RANK` | NUMBER |
| `TREND_STRENGTH` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 764. `channel-sales-velocity`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `RANK` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 765. `amazonspapivendorsalesevent`  —  domain `sales`

### Input model — `adls://yogeshdata/sourcedata/AmazonSpApiVendorInventoryEvent/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `upc` | string |
| `asin` | string |
| `account_id` | string |
| `marketplace_id` | string |
| `highly_available_inventory` | int64 |
| `event_time` | string |
| `start_time` | string |
| `end_time` | string |
| `event_type` | string |

### Output model — `adls://yogeshdata/sourcedata/AmazonSpApiVendorSalesEvent/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `upc` | string |
| `asin` | string |
| `account_id` | string |
| `marketplace_id` | string |
| `currency_code` | string |
| `ordered_units` | int64 |
| `ordered_revenue` | double |
| `event_time` | string |
| `start_time` | string |
| `end_time` | string |
| `event_type` | string |

## 766. `net-sales`  —  domain `sales`

### Input model — `adls://lowerenvsdatanxd/sales-value/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `id` | string |
| `transaction_date` | date |
| `product_id` | string |
| `quantity` | int |
| `unit_price` | float |
| `region` | string |
| `processed_at` | date |

### Output model — `LOWERENVS_DB.SALES_VALUE.NET_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PRODUCT_ID` | TEXT |
| `QUANTITY` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `DISCOUNT_AMOUNT` | FLOAT |
| `RETURN_QUANTITY` | NUMBER |
| `REGION` | TEXT |
| `GROSS_REVENUE` | FLOAT |
| `NET_REVENUE` | FLOAT |
| `PROCESSED_AT` | TEXT |

## 767. `net-sales`  —  domain `sales`

### Input model — `adls://yogeshdata//`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `id` | string |
| `transaction_date` | date |
| `product_id` | string |
| `quantity` | int |
| `unit_price` | float |
| `region` | string |
| `processed_at` | date |

### Output model — `LOWERENVS_DB.SALES_VALUE.NET_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PRODUCT_ID` | TEXT |
| `QUANTITY` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `DISCOUNT_AMOUNT` | FLOAT |
| `RETURN_QUANTITY` | NUMBER |
| `REGION` | TEXT |
| `GROSS_REVENUE` | FLOAT |
| `NET_REVENUE` | FLOAT |
| `PROCESSED_AT` | TEXT |

## 768. `net-sales`  —  domain `sales`

### Input model — `LOWERENVS_DB.SALES_VALUE.GROSS_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PRODUCT_ID` | TEXT |
| `QUANTITY` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `REGION` | TEXT |
| `PROCESSED_AT` | TEXT |

### Output model — `LOWERENVS_DB.SALES_VALUE.NET_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | TEXT |
| `TRANSACTION_DATE` | TEXT |
| `PRODUCT_ID` | TEXT |
| `QUANTITY` | NUMBER |
| `UNIT_PRICE` | FLOAT |
| `DISCOUNT_AMOUNT` | FLOAT |
| `RETURN_QUANTITY` | NUMBER |
| `REGION` | TEXT |
| `GROSS_REVENUE` | FLOAT |
| `NET_REVENUE` | FLOAT |
| `PROCESSED_AT` | TEXT |

## 769. `ef7a79aa-9242-4434-a9ea-d2bc0c850fab`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/04cec544-2e5a-499c-bd06-6da592a21132/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `user_id` | string |
| `event_type` | string |
| `event_data` | string |
| `original_timestamp` | int64 |
| `processed_at` | timestamp[us] |
| `_row-id-col-4993c36e-d1e8-493f-896b-6d0114f3a18d` | int64 |
| `_row-commit-version-col-17b6cd05-17e9-477b-bbca-060c3e9591c0` | int64 |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/ef7a79aa-9242-4434-a9ea-d2bc0c850fab/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `user_id` | string |
| `event_type` | string |
| `event_data` | string |
| `original_timestamp` | int64 |
| `processed_at` | timestamp[us] |
| `message` | string |

## 770. `d68a1bdc-4b0f-425f-b589-d6b14369bda3`  —  domain `product`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | double |
| `units_sold_last_7_days` | int32 |
| `units_sold_previous_7_days` | int32 |
| `sales_change_percent` | double |
| `sales_trend` | string |
| `trend_strength` | double |
| `momentum_score` | double |
| `trend_rank` | int32 |

## 771. `trending-sales`  —  domain `sales`

### Input model — `s3://lowerenvs-output-data-product//`

_service `s3-output`, format `csv`_

| column | type |
|---|---|
| `product_id` | string |
| `sales_channel` | string |
| `region` | string |
| `velocity_score` | float |
| `units_sold_last_7_days` | int |
| `units_sold_previous_7_days` | int |
| `sales_change_percent` | float |
| `sales_trend` | string |
| `revenue` | float |
| `sale_date` | date |

### Output model — `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `MOMENTUM_SCORE` | FLOAT |
| `PRODUCT_ID` | TEXT |
| `REGION` | TEXT |
| `SALES_CHANGE_PERCENT` | FLOAT |
| `SALES_CHANNEL` | TEXT |
| `SALES_TREND` | TEXT |
| `TREND_RANK` | NUMBER |
| `TREND_STRENGTH` | FLOAT |
| `UNITS_SOLD_LAST_7_DAYS` | NUMBER |
| `UNITS_SOLD_PREVIOUS_7_DAYS` | NUMBER |
| `VELOCITY_SCORE` | FLOAT |

## 772. `dremio-demo`  —  domain `other`

### Input model — `adls://yogeshdata/dremio-transformed/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `author` | string |
| `title` | string |
| `matches` | int32 |

### Output model — `adls://yogeshdata/dremio-demo/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `author` | string |
| `title` | string |
| `matches` | int64 |
| `__index_level_0__` | string |
| `__index_level_1__` | string |

## 773. `metadata`  —  domain `product`

### Input model — `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`

_service `s3-input`, format `json`_

_no column schema (binary or non-tabular source)_

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/4da13333-0cfd-4567-8e0b-6dc56631aaf0/_iceberg/metadata/`

_service `adls`, format `avro`_

_no column schema (binary or non-tabular source)_

## 774. `metadata`  —  domain `product`

### Input model — `adls://yogeshdata/playlists/dtest/metadata/`

_service `nxd-adls`, format `avro`_

_no column schema (binary or non-tabular source)_

### Output model — `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`

_service `s3-input`, format `json`_

_no column schema (binary or non-tabular source)_

## 775. `metadata`  —  domain `product`

### Input model — `adls://yogeshdata/playlists/dtest/metadata/`

_service `nxd-adls`, format `text`_

_no column schema (binary or non-tabular source)_

### Output model — `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`

_service `s3-input`, format `json`_

_no column schema (binary or non-tabular source)_

## 776. `metadata`  —  domain `product`

### Input model — `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`

_service `s3-input`, format `avro`_

_no column schema (binary or non-tabular source)_

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/4da13333-0cfd-4567-8e0b-6dc56631aaf0/_iceberg/metadata/`

_service `adls`, format `avro`_

_no column schema (binary or non-tabular source)_

## 777. `metadata`  —  domain `product`

### Input model — `adls://yogeshdata/playlists/dtest/metadata/`

_service `nxd-adls`, format `avro`_

_no column schema (binary or non-tabular source)_

### Output model — `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`

_service `s3-input`, format `avro`_

_no column schema (binary or non-tabular source)_

## 778. `metadata`  —  domain `product`

### Input model — `adls://yogeshdata/playlists/dtest/metadata/`

_service `nxd-adls`, format `text`_

_no column schema (binary or non-tabular source)_

### Output model — `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`

_service `s3-input`, format `avro`_

_no column schema (binary or non-tabular source)_

## 779. `delta-log`  —  domain `sales`

### Input model — `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/_delta_log/`

_service `nxd-adls`, format `delta/_delta_log/__tmp_path_dir`_

_no column schema (binary or non-tabular source)_

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `txn` | struct<appId: string, version: int64, lastUpdated: int64> |
| `add` | struct<path: string, partitionValues: map<string, string ('partitionValues')>, size: int64, modificationTime: int64, dataChange: bool, tags: map<string, string ('tags')>, deletionVector: struct<storageType: string, pathOrInlineDv: string, offset: int32, sizeInBytes: int32, cardinality: int64, maxRowIndex: int64>, baseRowId: int64, defaultRowCommitVersion: int64, clusteringProvider: string, stats_parsed: struct<numRecords: int64, minValues: struct<pickup_zip: string, trip_count: int32, avg_fare: double>, maxValues: struct<pickup_zip: string, trip_count: int32, avg_fare: double>, nullCount: struct<pickup_zip: int64, trip_count: int64, avg_fare: int64>, tightBounds: bool>> |
| `remove` | struct<path: string, deletionTimestamp: int64, dataChange: bool, extendedFileMetadata: bool, partitionValues: map<string, string ('partitionValues')>, size: int64, deletionVector: struct<storageType: string, pathOrInlineDv: string, offset: int32, sizeInBytes: int32, cardinality: int64, maxRowIndex: int64>, baseRowId: int64, defaultRowCommitVersion: int64> |
| `metaData` | struct<id: string, name: string, description: string, format: struct<provider: string, options: map<string, string ('options')>>, schemaString: string, partitionColumns: list<element: string>, configuration: map<string, string ('configuration')>, createdTime: int64> |
| `protocol` | struct<minReaderVersion: int32, minWriterVersion: int32, readerFeatures: list<element: string>, writerFeatures: list<element: string>> |
| `domainMetadata` | struct<domain: string, configuration: string, removed: bool> |

## 780. `delta-log`  —  domain `sales`

### Input model — `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/_delta_log/`

_service `nxd-adls`, format `delta/_delta_log/_commits`_

_no column schema (binary or non-tabular source)_

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `txn` | struct<appId: string, version: int64, lastUpdated: int64> |
| `add` | struct<path: string, partitionValues: map<string, string ('partitionValues')>, size: int64, modificationTime: int64, dataChange: bool, tags: map<string, string ('tags')>, deletionVector: struct<storageType: string, pathOrInlineDv: string, offset: int32, sizeInBytes: int32, cardinality: int64, maxRowIndex: int64>, baseRowId: int64, defaultRowCommitVersion: int64, clusteringProvider: string, stats_parsed: struct<numRecords: int64, minValues: struct<pickup_zip: string, trip_count: int32, avg_fare: double>, maxValues: struct<pickup_zip: string, trip_count: int32, avg_fare: double>, nullCount: struct<pickup_zip: int64, trip_count: int64, avg_fare: int64>, tightBounds: bool>> |
| `remove` | struct<path: string, deletionTimestamp: int64, dataChange: bool, extendedFileMetadata: bool, partitionValues: map<string, string ('partitionValues')>, size: int64, deletionVector: struct<storageType: string, pathOrInlineDv: string, offset: int32, sizeInBytes: int32, cardinality: int64, maxRowIndex: int64>, baseRowId: int64, defaultRowCommitVersion: int64> |
| `metaData` | struct<id: string, name: string, description: string, format: struct<provider: string, options: map<string, string ('options')>>, schemaString: string, partitionColumns: list<element: string>, configuration: map<string, string ('configuration')>, createdTime: int64> |
| `protocol` | struct<minReaderVersion: int32, minWriterVersion: int32, readerFeatures: list<element: string>, writerFeatures: list<element: string>> |
| `domainMetadata` | struct<domain: string, configuration: string, removed: bool> |

## 781. `delta-log`  —  domain `sales`

### Input model — `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/_delta_log/`

_service `nxd-adls`, format `delta/_delta_log/__tmp_path_dir`_

_no column schema (binary or non-tabular source)_

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`

_service `adls`, format `crc`_

_no column schema (binary or non-tabular source)_

## 782. `delta-log`  —  domain `sales`

### Input model — `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/_delta_log/`

_service `nxd-adls`, format `delta/_delta_log/_commits`_

_no column schema (binary or non-tabular source)_

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`

_service `adls`, format `crc`_

_no column schema (binary or non-tabular source)_

## 783. `metadata`  —  domain `product`

### Input model — `adls://yogeshdata/playlists/dtest/metadata/`

_service `nxd-adls`, format `avro`_

_no column schema (binary or non-tabular source)_

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/4da13333-0cfd-4567-8e0b-6dc56631aaf0/_iceberg/metadata/`

_service `adls`, format `avro`_

_no column schema (binary or non-tabular source)_

## 784. `metadata`  —  domain `product`

### Input model — `adls://yogeshdata/playlists/dtest/metadata/`

_service `nxd-adls`, format `text`_

_no column schema (binary or non-tabular source)_

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/4da13333-0cfd-4567-8e0b-6dc56631aaf0/_iceberg/metadata/`

_service `adls`, format `avro`_

_no column schema (binary or non-tabular source)_

## 785. `testing`  —  domain `other`

### Input model — `adls://lowerenvsdatanxd/testing/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `id` | string |
| `value` | int |

### Output model — `adls://yogeshdata/testing/`

_service `nxd-adls`, format `parquet`_

| column | type |
|---|---|
| `field1` | int32 |

## 786. `amazon-reviews`  —  domain `customer`

### Input model — `adls://lowerenvsdatanxd/amazon-reviews-test/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `average_rating` | float |
| `brand` | string |
| `category` | string |
| `helpful_vote` | int |
| `item_id` | string |
| `main_category` | string |
| `price` | float |
| `product_title` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `total_vote` | int |
| `user_id` | string |
| `verified_purchase` | boolean |

### Output model — `adls://lowerenvsdatanxd/amazon-reviews/`

_service `adls`, format `csv`_

| column | type |
|---|---|
| `user_id` | string |
| `item_id` | string |
| `rating` | float |
| `review_text` | string |
| `review_title` | string |
| `timestamp` | date |
| `verified_purchase` | boolean |
| `helpful_vote` | int |
| `total_vote` | int |
| `category` | string |
| `product_title` | string |
| `average_rating` | float |
| `price` | float |
| `brand` | string |
| `main_category` | string |

## 787. `playlists`  —  domain `other`

### Input model — `adls://yogeshdata/playlistshello/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `album_name` | string |
| `album_uri` | string |
| `artist_name` | string |
| `artist_uri` | string |
| `duration_ms` | int |
| `pos` | int |
| `track_name` | string |
| `track_uri` | string |
| `pid` | int |

### Output model — `adls://yogeshdata/playlists/`

_service `nxd-adls`, format `csv`_

| column | type |
|---|---|
| `pos` | int |
| `artist_name` | string |
| `track_uri` | string |
| `artist_uri` | string |
| `track_name` | string |
| `album_uri` | string |
| `duration_ms` | int |
| `album_name` | string |
| `pid` | int |

## 788. `sales-transactions`  —  domain `sales`

### Input model — `LOWERENVS_DB.ONLINE_SALES.SALES_TRANSACTIONS_RAW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `SALE_ID` | NUMBER |
| `PRODUCT_ID` | NUMBER |
| `QUANTITY` | NUMBER |
| `SALE_AMOUNT` | NUMBER |
| `SALE_DATE` | TEXT |
| `CHANNEL_ID` | TEXT |
| `CUSTOMER_ID` | TEXT |
| `PAYMENT_METHOD` | TEXT |
| `UNIT_PRICE` | FLOAT |
| `DISCOUNT_APPLIED` | FLOAT |
| `TAX_AMOUNT` | FLOAT |
| `TOTAL_AMOUNT` | FLOAT |
| `CREATED_AT` | TIMESTAMP_NTZ |
| `UPDATED_AT` | TIMESTAMP_NTZ |

### Output model — `LOWERENVS_DB.ONLINE_SALES.SALES_TRANSACTIONS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `SALE_ID` | NUMBER |
| `PRODUCT_ID` | NUMBER |
| `QUANTITY` | NUMBER |
| `SALE_AMOUNT` | NUMBER |
| `SALE_DATE` | TEXT |
| `CHANNEL_ID` | TEXT |
| `CUSTOMER_ID` | TEXT |
| `PAYMENT_METHOD` | TEXT |
| `UNIT_PRICE` | FLOAT |
| `DISCOUNT_APPLIED` | FLOAT |
| `TAX_AMOUNT` | FLOAT |
| `TOTAL_AMOUNT` | FLOAT |
| `CREATED_AT` | TIMESTAMP_NTZ |
| `UPDATED_AT` | TIMESTAMP_NTZ |

## 789. `sales-transactions`  —  domain `sales`

### Input model — `LOWERENVS_DB.ONLINE_SALES_RAW.SALES_TRANSACTIONS_RAW`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `SALE_ID` | NUMBER |
| `PRODUCT_ID` | NUMBER |
| `QUANTITY` | NUMBER |
| `SALE_AMOUNT` | NUMBER |
| `SALE_DATE` | TEXT |
| `CHANNEL_ID` | TEXT |
| `CUSTOMER_ID` | TEXT |
| `PAYMENT_METHOD` | TEXT |
| `UNIT_PRICE` | FLOAT |
| `DISCOUNT_APPLIED` | FLOAT |
| `TAX_AMOUNT` | FLOAT |
| `TOTAL_AMOUNT` | FLOAT |
| `CREATED_AT` | TIMESTAMP_NTZ |
| `UPDATED_AT` | TIMESTAMP_NTZ |

### Output model — `LOWERENVS_DB.ONLINE_SALES_RAW.SALES_TRANSACTIONS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `SALE_ID` | NUMBER |
| `PRODUCT_ID` | NUMBER |
| `QUANTITY` | NUMBER |
| `SALE_AMOUNT` | NUMBER |
| `SALE_DATE` | TEXT |
| `CHANNEL_ID` | TEXT |
| `CUSTOMER_ID` | TEXT |
| `PAYMENT_METHOD` | TEXT |
| `UNIT_PRICE` | FLOAT |
| `DISCOUNT_APPLIED` | FLOAT |
| `TAX_AMOUNT` | FLOAT |
| `TOTAL_AMOUNT` | FLOAT |
| `CREATED_AT` | TIMESTAMP_NTZ |
| `UPDATED_AT` | TIMESTAMP_NTZ |

## 790. `57300a35-4bbf-4971-9008-43bd27fb8f90`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `creation_date` | timestamp[ns] |
| `accounting_date` | date32[day] |
| `effective_date` | date32[day] |
| `merchant_name` | string |
| `country_code` | string |
| `payment_method` | string |
| `payment_method_type` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int64 |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `industry` | string |
| `processing_fee_usd` | decimal128(18, 6) |
| `fx_fee_usd` | decimal128(18, 6) |
| `installment_fee_usd` | decimal128(18, 6) |
| `other_income_usd` | decimal128(18, 6) |
| `processing_cost_usd` | decimal128(18, 6) |
| `tax_cost_usd` | decimal128(18, 6) |
| `fx_cost_usd` | decimal128(18, 6) |
| `chargeback_cost_usd` | decimal128(18, 6) |
| `local_amount` | decimal128(18, 6) |
| `usd_amount` | decimal128(18, 6) |
| `gross_profit_usd` | decimal128(18, 6) |
| `gross_margin_pct` | double |
| `load_time` | timestamp[ns] |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/57300a35-4bbf-4971-9008-43bd27fb8f90/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `merchant_name` | string |
| `creation_date` | string |
| `accounting_date` | date32[day] |
| `effective_date` | date32[day] |
| `country_code` | string |
| `payment_method` | string |
| `payment_method_type` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int32 |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `industry` | string |
| `processing_fee_usd` | float |
| `fx_fee_usd` | float |
| `installment_fee_usd` | float |
| `other_income_usd` | float |
| `processing_cost_usd` | float |
| `tax_cost_usd` | float |
| `fx_cost_usd` | float |
| `chargeback_cost_usd` | float |
| `local_amount` | float |
| `usd_amount` | float |
| `gross_profit_usd` | string |
| `gross_margin_pct` | float |

## 791. `57300a35-4bbf-4971-9008-43bd27fb8f90`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/17c1ac67-25f2-4d3c-8bf2-184d95b68bea/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `creation_date` | timestamp[ns] |
| `accounting_date` | date32[day] |
| `effective_date` | date32[day] |
| `country_code` | string |
| `payment_method` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `merchant_name` | string |
| `industry` | string |
| `payment_method_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int64 |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `processing_fee_usd` | decimal128(18, 6) |
| `fx_fee_usd` | decimal128(18, 6) |
| `installment_fee_usd` | decimal128(18, 6) |
| `other_income_usd` | decimal128(18, 6) |
| `total_revenue_usd` | decimal128(18, 6) |
| `processing_cost_usd` | decimal128(18, 6) |
| `tax_cost_usd` | decimal128(18, 6) |
| `fx_cost_usd` | decimal128(18, 6) |
| `chargeback_cost_usd` | decimal128(18, 6) |
| `total_cost_usd` | decimal128(18, 6) |
| `local_amount` | decimal128(18, 6) |
| `usd_amount` | decimal128(18, 6) |
| `gross_profit_usd` | decimal128(18, 6) |
| `gross_margin_pct` | double |
| `revenue_cost_ratio` | double |

### Output model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/57300a35-4bbf-4971-9008-43bd27fb8f90/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `gp_id` | string |
| `id_transaction` | string |
| `merchant_id` | string |
| `merchant_name` | string |
| `creation_date` | string |
| `accounting_date` | date32[day] |
| `effective_date` | date32[day] |
| `country_code` | string |
| `payment_method` | string |
| `payment_method_type` | string |
| `currency_code` | string |
| `transaction_type` | string |
| `gp_type_description` | string |
| `fx_mode` | string |
| `installments` | int32 |
| `merchant_operation_type` | string |
| `processor_name` | string |
| `collection_agent` | string |
| `entity_type` | string |
| `industry` | string |
| `processing_fee_usd` | float |
| `fx_fee_usd` | float |
| `installment_fee_usd` | float |
| `other_income_usd` | float |
| `processing_cost_usd` | float |
| `tax_cost_usd` | float |
| `fx_cost_usd` | float |
| `chargeback_cost_usd` | float |
| `local_amount` | float |
| `usd_amount` | float |
| `gross_profit_usd` | string |
| `gross_margin_pct` | float |

## 792. `westpac-term-deposits`  —  domain `product`

### Input model — `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/dea1e340-213d-4bf1-bc3a-9ae9b11a7219/`

_service `adls`, format `parquet`_

| column | type |
|---|---|
| `name` | string |
| `bank` | string |
| `min_amount` | int64 |
| `max_amount` | int64 |
| `min_term` | int64 |
| `max_term` | int64 |
| `monthly_rate` | decimal128(4, 2) |
| `annual_rate` | decimal128(4, 2) |
| `maturity_rate` | decimal128(4, 2) |

### Output model — `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.WESTPAC_TERM_DEPOSITS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `STATUS` | TEXT |
| `RATE_CODE` | TEXT |
| `PRODUCT` | TEXT |
| `MIN_AMOUNT` | TEXT |
| `MAX_AMOUNT` | TEXT |
| `MIN_TERM` | TEXT |
| `MAX_TERM` | TEXT |
| `MATURITY_RATE` | TEXT |
| `MONTHLY_RATE` | TEXT |
| `HOT_RATE` | TEXT |
| `EFFECTIVE_DATE` | TEXT |

## 793. `term-deposits`  —  domain `product`

### Input model — `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.WESTPAC_TERM_DEPOSITS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_ID` | TEXT |
| `STATUS` | TEXT |
| `RATE_CODE` | TEXT |
| `PRODUCT` | TEXT |
| `MIN_AMOUNT` | TEXT |
| `MAX_AMOUNT` | TEXT |
| `MIN_TERM` | TEXT |
| `MAX_TERM` | TEXT |
| `MATURITY_RATE` | TEXT |
| `MONTHLY_RATE` | TEXT |
| `HOT_RATE` | TEXT |
| `EFFECTIVE_DATE` | TEXT |

### Output model — `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.TERM_DEPOSITS`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `NAME` | TEXT |
| `BANK` | TEXT |
| `MIN_AMOUNT` | NUMBER |
| `MAX_AMOUNT` | NUMBER |
| `MIN_TERM` | NUMBER |
| `MAX_TERM` | NUMBER |
| `MONTHLY_RATE` | NUMBER |
| `ANNUAL_RATE` | NUMBER |
| `MATURITY_RATE` | NUMBER |

# Mesh Assets — Candidate Models

_Input and output model schemas for each candidate data product in the companion report._

<a id="extract-ft-source-a56dc1"></a>
## 1. `extract-ft-source`  —  domain `product`  —  id `extract-ft-source-a56dc1`

<a id="extract-ft-source-a56dc1-in"></a>
### Input model — `s3://output-data-product/extract-ft-feature/demo/`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `dp_discovery` | string |
| `llm_response` | string |
| `manual_response` | string |

<a id="extract-ft-source-a56dc1-out"></a>
### Output model — `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `DP_DISCOVERY` | TEXT |
| `LLM_RESPONSE` | TEXT |
| `MANUAL_RESPONSE` | TEXT |

<a id="extract-ft-source-b84e43"></a>
## 2. `extract-ft-source`  —  domain `product`  —  id `extract-ft-source-b84e43`

<a id="extract-ft-source-b84e43-in"></a>
### Input model — `s3://output-data-product/extract-ft-train/demo/`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `dp_discovery` | string |
| `llm_response` | string |
| `manual_response` | string |

<a id="extract-ft-source-b84e43-out"></a>
### Output model — `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `DP_DISCOVERY` | TEXT |
| `LLM_RESPONSE` | TEXT |
| `MANUAL_RESPONSE` | TEXT |

<a id="podcast-list-bec0cd"></a>
## 3. `podcast-list`  —  domain `product`  —  id `podcast-list-bec0cd`

<a id="podcast-list-bec0cd-in"></a>
### Input model — `s3://output-data-product/podcasts-source/demo/podcast_source.csv`

_service `daff-s3`, format `csv`_

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

<a id="podcast-list-bec0cd-out"></a>
### Output model — `daff_db.PODCASTS.PODCAST_LIST`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | TEXT |
| `TITLE` | TEXT |
| `DESCRIPTION` | TEXT |
| `AUTHOR` | TEXT |
| `EPISODE_ID` | TEXT |
| `EPISODE_TITLE` | TEXT |
| `EPISODE_DESCRIPTION` | TEXT |
| `EPISODE_DURATION` | TEXT |
| `RELEASE_DATE` | TEXT |
| `PLAYS` | NUMBER |
| `GENRE` | TEXT |
| `LANGUAGE` | TEXT |

<a id="customer-history-d46419"></a>
## 4. `customer-history`  —  domain `customer`  —  id `customer-history-d46419`

<a id="customer-history-d46419-in"></a>
### Input model — `s3://output-data-product/dwn-incremental2/demo/customer_history.csv`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `ID` | int |
| `FNAME` | string |
| `LNAME` | string |
| `STATUS` | string |
| `LAST_UPDATE` | int |
| `DP_DATE` | date |
| `AUDIT_TRAIL` | string |

<a id="customer-history-d46419-out"></a>
### Output model — `daff_db.DWN_INCREMENTAL2.CUSTOMER_HISTORY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | NUMBER |
| `FNAME` | TEXT |
| `LNAME` | TEXT |
| `STATUS` | TEXT |
| `LAST_UPDATE` | NUMBER |
| `DP_DATE` | NUMBER |
| `AUDIT_TRAIL` | TEXT |

<a id="customer-history-d06fb4"></a>
## 5. `customer-history`  —  domain `customer`  —  id `customer-history-d06fb4`

<a id="customer-history-d06fb4-in"></a>
### Input model — `s3://output-data-product/fcd-incremental2/demo/customer.csv`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `id` | int |
| `fname` | string |
| `lname` | string |
| `status` | string |
| `last_update` | int |
| `dp_date` | int |
| `audit_trail` | string |

<a id="customer-history-d06fb4-out"></a>
### Output model — `daff_db.DWN_INCREMENTAL2.CUSTOMER_HISTORY`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | NUMBER |
| `FNAME` | TEXT |
| `LNAME` | TEXT |
| `STATUS` | TEXT |
| `LAST_UPDATE` | NUMBER |
| `DP_DATE` | NUMBER |
| `AUDIT_TRAIL` | TEXT |

<a id="podcast-source-ae4f59"></a>
## 6. `podcast-source`  —  domain `product`  —  id `podcast-source-ae4f59`

<a id="podcast-source-ae4f59-in"></a>
### Input model — `s3://output-data-product/podcasts-source/demo/podcast_source.csv`

_service `daff-s3`, format `csv`_

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

<a id="podcast-source-ae4f59-out"></a>
### Output model — `daff_db.PODCASTS_SOURCE_3.PODCAST_SOURCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | NUMBER |
| `TITLE` | TEXT |
| `DESCRIPTION` | TEXT |
| `AUTHOR` | TEXT |
| `EPISODE_ID` | TEXT |
| `EPISODE_TITLE` | TEXT |
| `EPISODE_DESCRIPTION` | TEXT |
| `EPISODE_DURATION` | TEXT |
| `RELEASE_DATE` | TEXT |
| `PLAYS` | NUMBER |
| `GENRE` | TEXT |
| `LANGUAGE` | TEXT |

<a id="customer-1f92d5"></a>
## 7. `customer`  —  domain `customer`  —  id `customer-1f92d5`

<a id="customer-1f92d5-in"></a>
### Input model — `s3://output-data-product/dwn-incremental2/demo/customer_history.csv`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `ID` | int |
| `FNAME` | string |
| `LNAME` | string |
| `STATUS` | string |
| `LAST_UPDATE` | int |
| `DP_DATE` | date |
| `AUDIT_TRAIL` | string |

<a id="customer-1f92d5-out"></a>
### Output model — `daff_db.FCD_INCREMENTAL2.CUSTOMER`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | NUMBER |
| `FNAME` | TEXT |
| `LNAME` | TEXT |
| `STATUS` | TEXT |
| `LAST_UPDATE` | NUMBER |

<a id="customer-4d42df"></a>
## 8. `customer`  —  domain `customer`  —  id `customer-4d42df`

<a id="customer-4d42df-in"></a>
### Input model — `s3://output-data-product/fcd-incremental2/demo/customer.csv`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `id` | int |
| `fname` | string |
| `lname` | string |
| `status` | string |
| `last_update` | int |
| `dp_date` | int |
| `audit_trail` | string |

<a id="customer-4d42df-out"></a>
### Output model — `daff_db.FCD_INCREMENTAL2.CUSTOMER`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | NUMBER |
| `FNAME` | TEXT |
| `LNAME` | TEXT |
| `STATUS` | TEXT |
| `LAST_UPDATE` | NUMBER |

<a id="playlist-227923"></a>
## 9. `playlist`  —  domain `product`  —  id `playlist-227923`

<a id="playlist-227923-in"></a>
### Input model — `s3://output-data-product/iceberg/playlist/`

_service `daff-s3`, format `iceberg`_

| column | type |
|---|---|
| `name` | string |
| `collaborative` | string |
| `pid` | long |
| `modified_at` | long |
| `num_tracks` | long |
| `num_albums` | long |
| `num_followers` | long |
| `num_edits` | long |
| `duration_ms` | long |
| `num_artists` | long |
| `description` | string |

<a id="playlist-227923-out"></a>
### Output model — `daff_db.PLAYLISTS.PLAYLIST`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `NAME` | TEXT |
| `COLLABORATIVE` | BOOLEAN |
| `PID` | NUMBER |
| `MODIFIED_AT` | NUMBER |
| `NUM_TRACKS` | NUMBER |
| `NUM_ALBUMS` | NUMBER |
| `NUM_FOLLOWERS` | NUMBER |

<a id="amazon-sales-34138b"></a>
## 10. `amazon-sales`  —  domain `sales`  —  id `amazon-sales-34138b`

<a id="amazon-sales-34138b-in"></a>
### Input model — `s3://output-data-product/downstream-c/prod/amazon-sales.csv`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `asin` | string |
| `date-shipped` | date |

<a id="amazon-sales-34138b-out"></a>
### Output model — `daff_db.CHECK_POSTFIX.AMAZON_SALES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ASIN` | TEXT |
| `DATE_SHIPPED` | DATE |

<a id="extract-ft-source-b3b772"></a>
## 11. `extract-ft-source`  —  domain `product`  —  id `extract-ft-source-b3b772`

<a id="extract-ft-source-b3b772-in"></a>
### Input model — `s3://output-data-product/extract-ft-consume-feature/demo/`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `<?xml version="1.0" encoding="UTF-8"?>` | string |

<a id="extract-ft-source-b3b772-out"></a>
### Output model — `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `DP_DISCOVERY` | TEXT |
| `LLM_RESPONSE` | TEXT |
| `MANUAL_RESPONSE` | TEXT |

<a id="extract-ft-source-131af1"></a>
## 12. `extract-ft-source`  —  domain `product`  —  id `extract-ft-source-131af1`

<a id="extract-ft-source-131af1-in"></a>
### Input model — `s3://output-data-product/extract-ft-evaluate/demo/`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `agree_prompt` | boolean |
| `agree_ft` | boolean |

<a id="extract-ft-source-131af1-out"></a>
### Output model — `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `DP_DISCOVERY` | TEXT |
| `LLM_RESPONSE` | TEXT |
| `MANUAL_RESPONSE` | TEXT |

<a id="extract-ft-source-a56dc1"></a>
## 13. `extract-ft-source`  —  domain `product`  —  id `extract-ft-source-a56dc1`

<a id="extract-ft-source-a56dc1-in"></a>
### Input model — `s3://output-data-product/extract-ft-feature/demo/`

_service `daff-s3`, format `jsonl`_

_no column schema (binary or non-tabular source)_

<a id="extract-ft-source-a56dc1-out"></a>
### Output model — `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `DP_DISCOVERY` | TEXT |
| `LLM_RESPONSE` | TEXT |
| `MANUAL_RESPONSE` | TEXT |

<a id="extract-ft-source-b84e43"></a>
## 14. `extract-ft-source`  —  domain `product`  —  id `extract-ft-source-b84e43`

<a id="extract-ft-source-b84e43-in"></a>
### Input model — `s3://output-data-product/extract-ft-train/demo/`

_service `daff-s3`, format `jsonl`_

_no column schema (binary or non-tabular source)_

<a id="extract-ft-source-b84e43-out"></a>
### Output model — `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `DP_DISCOVERY` | TEXT |
| `LLM_RESPONSE` | TEXT |
| `MANUAL_RESPONSE` | TEXT |

<a id="extract-ft-source-0e0fb0"></a>
## 15. `extract-ft-source`  —  domain `product`  —  id `extract-ft-source-0e0fb0`

<a id="extract-ft-source-0e0fb0-in"></a>
### Input model — `s3://output-data-product/extract-ft-log/demo/extract_ft_runs.csv`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `run_id` | string |
| `full_valid_loss_key` | string |
| `full_valid_loss_timestamp` | int |
| `full_valid_mean_token_accuracy_value` | float |
| `full_valid_mean_token_accuracy_key` | string |
| `full_valid_loss_step` | int |
| `result_timestamp` | int |
| `result_key` | string |
| `result_value` | float |
| `full_valid_loss_value` | float |
| `full_valid_mean_token_accuracy_timestamp` | int |
| `result_step` | int |
| `full_valid_mean_token_accuracy_step` | int |
| `seed` | int |
| `validation_file` | string |
| `ft_job_id` | string |
| `learning_rate_multiplier` | int |
| `n_epochs` | int |
| `model` | string |
| `training_file` | string |
| `fine_tuned_model` | string |
| `batch_size` | int |

<a id="extract-ft-source-0e0fb0-out"></a>
### Output model — `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `DP_DISCOVERY` | TEXT |
| `LLM_RESPONSE` | TEXT |
| `MANUAL_RESPONSE` | TEXT |

<a id="extract-ft-source-d8db3e"></a>
## 16. `extract-ft-source`  —  domain `product`  —  id `extract-ft-source-d8db3e`

<a id="extract-ft-source-d8db3e-in"></a>
### Input model — `s3://output-data-product/extract-ft-show/demo/extract_ft_runs.csv`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `run_id` | string |
| `full_valid_mean_token_accuracy_step` | int |
| `full_valid_mean_token_accuracy_value` | float |
| `full_valid_mean_token_accuracy_key` | string |
| `result_key` | string |
| `result_value` | float |
| `full_valid_loss_step` | int |
| `full_valid_loss_key` | string |
| `result_step` | int |
| `full_valid_loss_timestamp` | int |
| `full_valid_loss_value` | float |
| `result_timestamp` | int |
| `full_valid_mean_token_accuracy_timestamp` | int |
| `fine_tuned_model` | string |
| `training_file` | string |
| `seed` | int |
| `learning_rate_multiplier` | int |
| `validation_file` | string |
| `n_epochs` | int |
| `model` | string |
| `batch_size` | int |
| `ft_job_id` | string |

<a id="extract-ft-source-d8db3e-out"></a>
### Output model — `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `DP_DISCOVERY` | TEXT |
| `LLM_RESPONSE` | TEXT |
| `MANUAL_RESPONSE` | TEXT |

<a id="product-catalog-all-2cbee4"></a>
## 17. `product-catalog-all`  —  domain `product`  —  id `product-catalog-all-2cbee4`

<a id="product-catalog-all-2cbee4-in"></a>
### Input model — `s3://output-data-product/product-catalog-simple/demo/`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `version https://git-lfs.github.com/spec/v1` | string |

<a id="product-catalog-all-2cbee4-out"></a>
### Output model — `daff_db.PRODUCT_CATALOG.PRODUCT_CATALOG_ALL`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `PRODUCT_CODE` | TEXT |
| `PRODUCT_CODE_TYPE` | TEXT |
| `GTIN` | TEXT |
| `TITLE` | TEXT |
| `SHORT_DESCRIPTION` | TEXT |
| `PRODUCT_DESCRIPTION` | TEXT |
| `IS_PEPSI_PRODUCT` | TEXT |
| `IS_ACTIVE_PRODUCT` | TEXT |
| `IS_VARIETY_PACK` | TEXT |
| `IRI_CATEGORY_NAME` | TEXT |
| `IRI_SUB_CATEGORY_NAME` | TEXT |
| `HARMONIZED_CATEGORY_NAME` | TEXT |
| `HARMONIZED_SUB_CATEGORY_NAME` | TEXT |
| `CATEGORY_HEAD_NAME` | TEXT |
| `CATEGORY_SUB_HEAD_NAME` | TEXT |
| `FINANCE_BUSINESS_UNIT_NAME` | TEXT |
| `FINANCE_SUB_BUSINESS_UNIT_NAME` | TEXT |
| `SALES_BUSINESS_UNIT_NAME` | TEXT |
| `SALES_SUB_BUSINESS_UNIT_NAME` | TEXT |
| `FINANCE_BRAND_NAME` | TEXT |
| `FINANCE_SUB_BRAND_NAME` | TEXT |
| `SALES_BRAND_NAME` | TEXT |
| `SALES_SUB_BRAND_NAME` | TEXT |
| `ORIG_EXTERNAL_PRODUCT_KEY_SOURCE` | TEXT |
| `ORIG_EXTERNAL_PRODUCT_DESCRIPTION` | TEXT |
| `LOAD_DTS` | TEXT |
| `PACK_SIZE_NAME` | TEXT |
| `BRAND_SOURCE_TYPE` | TEXT |
| `REPORTING_UPC` | TEXT |
| `TRADEMARK` | TEXT |
| `PARENT_COMPANY` | TEXT |
| `MANUFACTURER` | TEXT |
| `STIBO_SUB_BRAND` | TEXT |
| `STIBO_FLAVOR` | TEXT |
| `STIBO_SUGAR_TYPE` | TEXT |

<a id="jira-issues-3df33a"></a>
## 18. `jira-issues`  —  domain `product`  —  id `jira-issues-3df33a`

<a id="jira-issues-3df33a-in"></a>
### Input model — `s3://output-data-product/jira/issues/`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-3df33a-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-803e45"></a>
## 19. `jira-issues`  —  domain `product`  —  id `jira-issues-803e45`

<a id="jira-issues-803e45-in"></a>
### Input model — `s3://output-data-product/jira/issues__changelog__histories/1754901860.686583.8243b0555f.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-803e45-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-887b91"></a>
## 20. `jira-issues`  —  domain `product`  —  id `jira-issues-887b91`

<a id="jira-issues-887b91-in"></a>
### Input model — `s3://output-data-product/jira/issues__changelog__histories__items/1754901860.686583.c5f7a14bc2.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-887b91-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-4ab22c"></a>
## 21. `jira-issues`  —  domain `product`  —  id `jira-issues-4ab22c`

<a id="jira-issues-4ab22c-in"></a>
### Input model — `s3://output-data-product/jira/issues__fields__customfield_10020/1754901860.686583.eab94ada68.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-4ab22c-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-7e1256"></a>
## 22. `jira-issues`  —  domain `product`  —  id `jira-issues-7e1256`

<a id="jira-issues-7e1256-in"></a>
### Input model — `s3://output-data-product/jira/issues__operations__link_groups/1754901860.686583.4d5133987b.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-7e1256-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-a5fb38"></a>
## 23. `jira-issues`  —  domain `product`  —  id `jira-issues-a5fb38`

<a id="jira-issues-a5fb38-in"></a>
### Input model — `s3://output-data-product/jira/issues__operations__link_groups__groups/`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-a5fb38-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-20f42a"></a>
## 24. `jira-issues`  —  domain `product`  —  id `jira-issues-20f42a`

<a id="jira-issues-20f42a-in"></a>
### Input model — `s3://output-data-product/jira/issues__operations__link_groups__links/1754901860.686583.13d57f8d0e.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-20f42a-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-06cec7"></a>
## 25. `jira-issues`  —  domain `product`  —  id `jira-issues-06cec7`

<a id="jira-issues-06cec7-in"></a>
### Input model — `s3://output-data-product/jira/issues__transitions/1754901860.686583.3e4acc9d40.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-06cec7-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-eebcd6"></a>
## 26. `jira-issues`  —  domain `product`  —  id `jira-issues-eebcd6`

<a id="jira-issues-eebcd6-in"></a>
### Input model — `s3://output-data-product/jira_search/issues/`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-eebcd6-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-e67d16"></a>
## 27. `jira-issues`  —  domain `product`  —  id `jira-issues-e67d16`

<a id="jira-issues-e67d16-in"></a>
### Input model — `s3://output-data-product/jira_search/issues__changelog__histories/1754901879.244883.f5b4b675bb.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-e67d16-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-221bc2"></a>
## 28. `jira-issues`  —  domain `product`  —  id `jira-issues-221bc2`

<a id="jira-issues-221bc2-in"></a>
### Input model — `s3://output-data-product/jira_search/issues__changelog__histories__items/1754901879.244883.26aec2748d.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-221bc2-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-f12cbd"></a>
## 29. `jira-issues`  —  domain `product`  —  id `jira-issues-f12cbd`

<a id="jira-issues-f12cbd-in"></a>
### Input model — `s3://output-data-product/jira_search/issues__fields__customfield_10020/1754901879.244883.83e56c091d.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-f12cbd-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-6b3c2f"></a>
## 30. `jira-issues`  —  domain `product`  —  id `jira-issues-6b3c2f`

<a id="jira-issues-6b3c2f-in"></a>
### Input model — `s3://output-data-product/jira_search/issues__operations__link_groups/1754901879.244883.07bcae3030.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-6b3c2f-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-32d056"></a>
## 31. `jira-issues`  —  domain `product`  —  id `jira-issues-32d056`

<a id="jira-issues-32d056-in"></a>
### Input model — `s3://output-data-product/jira_search/issues__operations__link_groups__groups/`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-32d056-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-43325e"></a>
## 32. `jira-issues`  —  domain `product`  —  id `jira-issues-43325e`

<a id="jira-issues-43325e-in"></a>
### Input model — `s3://output-data-product/jira_search/issues__operations__link_groups__links/1754901879.244883.975a0cde26.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-43325e-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="jira-issues-ec08de"></a>
## 33. `jira-issues`  —  domain `product`  —  id `jira-issues-ec08de`

<a id="jira-issues-ec08de-in"></a>
### Input model — `s3://output-data-product/jira_search/issues__transitions/1754901879.244883.33127df69b.csv.gz`

_service `daff-s3`, format `gz`_

_no column schema (binary or non-tabular source)_

<a id="jira-issues-ec08de-out"></a>
### Output model — `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `FIELDS__SUMMARY` | TEXT |
| `ID` | TEXT |
| `KEY` | TEXT |

<a id="product-catalog-d94c20"></a>
## 34. `product-catalog`  —  domain `product`  —  id `product-catalog-d94c20`

<a id="product-catalog-d94c20-in"></a>
### Input model — `s3://output-data-product/product-catalog-simple/demo/`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `version https://git-lfs.github.com/spec/v1` | string |

<a id="product-catalog-d94c20-out"></a>
### Output model — `daff_db.PRODUCT_CATALOG.PRODUCT_CATALOG`

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

<a id="multi-channel-sales-lock-41776d"></a>
## 35. `multi-channel-sales-lock`  —  domain `sales`  —  id `multi-channel-sales-lock-41776d`

<a id="multi-channel-sales-lock-41776d-in"></a>
### Input model — `s3://output-data-product/multi-output-service/prod/amazon-sales.csv`

_service `daff-s3`, format `csv`_

| column | type |
|---|---|
| `asin` | string |
| `date-shipped` | date |

<a id="multi-channel-sales-lock-41776d-out"></a>
### Output model — `daff_db.MULTI_CHANNEL_SALES.MULTI_CHANNEL_SALES_LOCK`

_service `nxd-snowflake`, format `snowflake`_

| column | type |
|---|---|
| `ID` | TEXT |
| `TS` | NUMBER |

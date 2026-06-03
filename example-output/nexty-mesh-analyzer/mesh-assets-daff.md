# Mesh Assets Report

_Generated 2026-05-20 from /tmp/nexty-mesh-analyzer/inventory-daff.json_

- **Infra profile:** `daff-demo-infra-profile`
- **Services inspected:** 2
- **Data assets considered:** 5584 (485 excluded by rules)
- **Candidate data products:** 27 block(s) — 35 pair(s), 4 ambiguous candidate(s) need user input
- **Replicated datasets (need user input):** 2
- **Duplicate services:** 0 | **Failed services:** 1
- **Matched within architecture flows:** daff-s3→nxd-snowflake

Model schemas for each candidate are in `example-output/nexty-mesh-analyzer/mesh-assets-daff-models.md`.

## Candidate Data Products

### Domain: customer

#### 1. `customer-history`

- **Suggested data product name:** `customer-history`
- **Domain:** `customer`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/dwn-incremental2/demo/customer_history.csv`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`customer-history-d46419-in`](mesh-assets-daff-models.md#customer-history-d46419-in)
- **Output data source:**
  - location: `daff_db.DWN_INCREMENTAL2.CUSTOMER_HISTORY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`customer-history-d46419-out`](mesh-assets-daff-models.md#customer-history-d46419-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - asset name match: 'customer_history'
  - name tokens shared: ['customer', 'dwn', 'history', 'incremental2']
  - schema jaccard=1.00, shared distinctive cols=['audit_trail', 'dp_date', 'fname', 'last_update', 'lname']

#### 2. `customer-history`

- **Suggested data product name:** `customer-history`
- **Domain:** `customer`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/fcd-incremental2/demo/customer.csv`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`customer-history-d06fb4-in`](mesh-assets-daff-models.md#customer-history-d06fb4-in)
- **Output data source:**
  - location: `daff_db.DWN_INCREMENTAL2.CUSTOMER_HISTORY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`customer-history-d06fb4-out`](mesh-assets-daff-models.md#customer-history-d06fb4-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['customer', 'incremental2']
  - schema jaccard=1.00, shared distinctive cols=['audit_trail', 'dp_date', 'fname', 'last_update', 'lname']

#### 3. `customer`

- **Suggested data product name:** `customer`
- **Domain:** `customer`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/dwn-incremental2/demo/customer_history.csv`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`customer-1f92d5-in`](mesh-assets-daff-models.md#customer-1f92d5-in)
- **Output data source:**
  - location: `daff_db.FCD_INCREMENTAL2.CUSTOMER`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`customer-1f92d5-out`](mesh-assets-daff-models.md#customer-1f92d5-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['customer', 'incremental2']
  - schema jaccard=0.71, shared distinctive cols=['fname', 'last_update', 'lname']

#### 4. `customer`

- **Suggested data product name:** `customer`
- **Domain:** `customer`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/fcd-incremental2/demo/customer.csv`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`customer-4d42df-in`](mesh-assets-daff-models.md#customer-4d42df-in)
- **Output data source:**
  - location: `daff_db.FCD_INCREMENTAL2.CUSTOMER`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`customer-4d42df-out`](mesh-assets-daff-models.md#customer-4d42df-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - asset name match: 'customer'
  - name tokens shared: ['customer', 'fcd', 'incremental2']
  - schema jaccard=0.71, shared distinctive cols=['fname', 'last_update', 'lname']

### Domain: product

#### 5. `extract-ft-source`  —  **ambiguous candidate** (4 inputs, 1 output, 6 pairs)

- **Suggested data product name:** `extract-ft-source`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** source-aligned (confidence medium)
- **Ambiguous-candidate id:** `extract-ft-source::demo:extract_ft_source` — variants are listed in the ambiguous-candidates sidecar; the skill prompts the user to pick the production input and output before this becomes a data product.
- **Model schemas (input → output, one per pair):** [`extract-ft-source-a56dc1-in`](mesh-assets-daff-models.md#extract-ft-source-a56dc1-in)→[`extract-ft-source-a56dc1-out`](mesh-assets-daff-models.md#extract-ft-source-a56dc1-out), [`extract-ft-source-b84e43-in`](mesh-assets-daff-models.md#extract-ft-source-b84e43-in)→[`extract-ft-source-b84e43-out`](mesh-assets-daff-models.md#extract-ft-source-b84e43-out), [`extract-ft-source-b3b772-in`](mesh-assets-daff-models.md#extract-ft-source-b3b772-in)→[`extract-ft-source-b3b772-out`](mesh-assets-daff-models.md#extract-ft-source-b3b772-out), [`extract-ft-source-131af1-in`](mesh-assets-daff-models.md#extract-ft-source-131af1-in)→[`extract-ft-source-131af1-out`](mesh-assets-daff-models.md#extract-ft-source-131af1-out), [`extract-ft-source-a56dc1-in`](mesh-assets-daff-models.md#extract-ft-source-a56dc1-in)→[`extract-ft-source-a56dc1-out`](mesh-assets-daff-models.md#extract-ft-source-a56dc1-out), [`extract-ft-source-b84e43-in`](mesh-assets-daff-models.md#extract-ft-source-b84e43-in)→[`extract-ft-source-b84e43-out`](mesh-assets-daff-models.md#extract-ft-source-b84e43-out)

#### 6. `podcast-list`

- **Suggested data product name:** `podcast-list`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/podcasts-source/demo/podcast_source.csv`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`podcast-list-bec0cd-in`](mesh-assets-daff-models.md#podcast-list-bec0cd-in)
- **Output data source:**
  - location: `daff_db.PODCASTS.PODCAST_LIST`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`podcast-list-bec0cd-out`](mesh-assets-daff-models.md#podcast-list-bec0cd-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['podcast', 'podcasts']
  - schema jaccard=1.00, shared distinctive cols=['author', 'episode_description', 'episode_duration', 'episode_id', 'episode_title', 'genre']

#### 7. `podcast-source`

- **Suggested data product name:** `podcast-source`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/podcasts-source/demo/podcast_source.csv`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`podcast-source-ae4f59-in`](mesh-assets-daff-models.md#podcast-source-ae4f59-in)
- **Output data source:**
  - location: `daff_db.PODCASTS_SOURCE_3.PODCAST_SOURCE`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`podcast-source-ae4f59-out`](mesh-assets-daff-models.md#podcast-source-ae4f59-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - asset name match: 'podcast_source'
  - name tokens shared: ['podcast', 'podcasts']
  - schema jaccard=1.00, shared distinctive cols=['author', 'episode_description', 'episode_duration', 'episode_id', 'episode_title', 'genre']

#### 8. `playlist`

- **Suggested data product name:** `playlist`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/iceberg/playlist/`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`playlist-227923-in`](mesh-assets-daff-models.md#playlist-227923-in)
- **Output data source:**
  - location: `daff_db.PLAYLISTS.PLAYLIST`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`playlist-227923-out`](mesh-assets-daff-models.md#playlist-227923-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - asset name match: 'playlist'
  - name tokens shared: ['playlist']
  - schema jaccard=0.64, shared distinctive cols=['collaborative', 'modified_at', 'num_albums', 'num_followers', 'num_tracks', 'pid']

#### 9. `extract-ft-source`  —  **ambiguous candidate** (2 inputs, 1 output, 2 pairs)

- **Suggested data product name:** `extract-ft-source`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Ambiguous-candidate id:** `extract-ft-source::extract_ft_runs:extract_ft_source` — variants are listed in the ambiguous-candidates sidecar; the skill prompts the user to pick the production input and output before this becomes a data product.
- **Model schemas (input → output, one per pair):** [`extract-ft-source-0e0fb0-in`](mesh-assets-daff-models.md#extract-ft-source-0e0fb0-in)→[`extract-ft-source-0e0fb0-out`](mesh-assets-daff-models.md#extract-ft-source-0e0fb0-out), [`extract-ft-source-d8db3e-in`](mesh-assets-daff-models.md#extract-ft-source-d8db3e-in)→[`extract-ft-source-d8db3e-out`](mesh-assets-daff-models.md#extract-ft-source-d8db3e-out)

#### 10. `product-catalog-all`

- **Suggested data product name:** `product-catalog-all`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/product-catalog-simple/demo/`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`product-catalog-all-2cbee4-in`](mesh-assets-daff-models.md#product-catalog-all-2cbee4-in)
- **Output data source:**
  - location: `daff_db.PRODUCT_CATALOG.PRODUCT_CATALOG_ALL`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`product-catalog-all-2cbee4-out`](mesh-assets-daff-models.md#product-catalog-all-2cbee4-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['catalog', 'product']

#### 11. `jira-issues`  —  **ambiguous candidate** (2 inputs, 1 output, 2 pairs)

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Ambiguous-candidate id:** `jira-issues::issues:jira_issues` — variants are listed in the ambiguous-candidates sidecar; the skill prompts the user to pick the production input and output before this becomes a data product.
- **Model schemas (input → output, one per pair):** [`jira-issues-3df33a-in`](mesh-assets-daff-models.md#jira-issues-3df33a-in)→[`jira-issues-3df33a-out`](mesh-assets-daff-models.md#jira-issues-3df33a-out), [`jira-issues-eebcd6-in`](mesh-assets-daff-models.md#jira-issues-eebcd6-in)→[`jira-issues-eebcd6-out`](mesh-assets-daff-models.md#jira-issues-eebcd6-out)

#### 12. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira/issues__changelog__histories/1754901860.686583.8243b0555f.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-803e45-in`](mesh-assets-daff-models.md#jira-issues-803e45-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-803e45-out`](mesh-assets-daff-models.md#jira-issues-803e45-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 13. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira/issues__changelog__histories__items/1754901860.686583.c5f7a14bc2.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-887b91-in`](mesh-assets-daff-models.md#jira-issues-887b91-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-887b91-out`](mesh-assets-daff-models.md#jira-issues-887b91-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 14. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira/issues__fields__customfield_10020/1754901860.686583.eab94ada68.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-4ab22c-in`](mesh-assets-daff-models.md#jira-issues-4ab22c-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-4ab22c-out`](mesh-assets-daff-models.md#jira-issues-4ab22c-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 15. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira/issues__operations__link_groups/1754901860.686583.4d5133987b.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-7e1256-in`](mesh-assets-daff-models.md#jira-issues-7e1256-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-7e1256-out`](mesh-assets-daff-models.md#jira-issues-7e1256-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 16. `jira-issues`  —  **ambiguous candidate** (2 inputs, 1 output, 2 pairs)

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Ambiguous-candidate id:** `jira-issues::issues__operations__link_groups__groups:jira_issues` — variants are listed in the ambiguous-candidates sidecar; the skill prompts the user to pick the production input and output before this becomes a data product.
- **Model schemas (input → output, one per pair):** [`jira-issues-a5fb38-in`](mesh-assets-daff-models.md#jira-issues-a5fb38-in)→[`jira-issues-a5fb38-out`](mesh-assets-daff-models.md#jira-issues-a5fb38-out), [`jira-issues-32d056-in`](mesh-assets-daff-models.md#jira-issues-32d056-in)→[`jira-issues-32d056-out`](mesh-assets-daff-models.md#jira-issues-32d056-out)

#### 17. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira/issues__operations__link_groups__links/1754901860.686583.13d57f8d0e.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-20f42a-in`](mesh-assets-daff-models.md#jira-issues-20f42a-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-20f42a-out`](mesh-assets-daff-models.md#jira-issues-20f42a-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 18. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira/issues__transitions/1754901860.686583.3e4acc9d40.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-06cec7-in`](mesh-assets-daff-models.md#jira-issues-06cec7-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-06cec7-out`](mesh-assets-daff-models.md#jira-issues-06cec7-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 19. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira_search/issues__changelog__histories/1754901879.244883.f5b4b675bb.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-e67d16-in`](mesh-assets-daff-models.md#jira-issues-e67d16-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-e67d16-out`](mesh-assets-daff-models.md#jira-issues-e67d16-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 20. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira_search/issues__changelog__histories__items/1754901879.244883.26aec2748d.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-221bc2-in`](mesh-assets-daff-models.md#jira-issues-221bc2-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-221bc2-out`](mesh-assets-daff-models.md#jira-issues-221bc2-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 21. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira_search/issues__fields__customfield_10020/1754901879.244883.83e56c091d.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-f12cbd-in`](mesh-assets-daff-models.md#jira-issues-f12cbd-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-f12cbd-out`](mesh-assets-daff-models.md#jira-issues-f12cbd-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 22. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira_search/issues__operations__link_groups/1754901879.244883.07bcae3030.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-6b3c2f-in`](mesh-assets-daff-models.md#jira-issues-6b3c2f-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-6b3c2f-out`](mesh-assets-daff-models.md#jira-issues-6b3c2f-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 23. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira_search/issues__operations__link_groups__links/1754901879.244883.975a0cde26.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-43325e-in`](mesh-assets-daff-models.md#jira-issues-43325e-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-43325e-out`](mesh-assets-daff-models.md#jira-issues-43325e-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 24. `jira-issues`

- **Suggested data product name:** `jira-issues`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/jira_search/issues__transitions/1754901879.244883.33127df69b.csv.gz`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`jira-issues-ec08de-in`](mesh-assets-daff-models.md#jira-issues-ec08de-in)
- **Output data source:**
  - location: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`jira-issues-ec08de-out`](mesh-assets-daff-models.md#jira-issues-ec08de-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['issues', 'jira']

#### 25. `product-catalog`

- **Suggested data product name:** `product-catalog`
- **Domain:** `product`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/product-catalog-simple/demo/`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`product-catalog-d94c20-in`](mesh-assets-daff-models.md#product-catalog-d94c20-in)
- **Output data source:**
  - location: `daff_db.PRODUCT_CATALOG.PRODUCT_CATALOG`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`product-catalog-d94c20-out`](mesh-assets-daff-models.md#product-catalog-d94c20-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['catalog', 'product']

### Domain: sales

#### 26. `amazon-sales`

- **Suggested data product name:** `amazon-sales`
- **Domain:** `sales`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/downstream-c/prod/amazon-sales.csv`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`amazon-sales-34138b-in`](mesh-assets-daff-models.md#amazon-sales-34138b-in)
- **Output data source:**
  - location: `daff_db.CHECK_POSTFIX.AMAZON_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`amazon-sales-34138b-out`](mesh-assets-daff-models.md#amazon-sales-34138b-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['amazon', 'sales']

#### 27. `multi-channel-sales-lock`

- **Suggested data product name:** `multi-channel-sales-lock`
- **Domain:** `sales`
- **Infra profile:** `daff-demo-infra-profile`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://output-data-product/multi-output-service/prod/amazon-sales.csv`
  - service: `daff-s3`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/daff-s3`
  - model schema: [`multi-channel-sales-lock-41776d-in`](mesh-assets-daff-models.md#multi-channel-sales-lock-41776d-in)
- **Output data source:**
  - location: `daff_db.MULTI_CHANNEL_SALES.MULTI_CHANNEL_SALES_LOCK`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/daff-demo-infra-profile#/services/nxd-snowflake`
  - model schema: [`multi-channel-sales-lock-41776d-out`](mesh-assets-daff-models.md#multi-channel-sales-lock-41776d-out)
- **Evidence:**
  - cross-service: daff-s3 -> nxd-snowflake
  - name tokens shared: ['multi', 'sales']

## Replicated Datasets (2)

_Each dataset below appears identically in 3+ locations across stores — a replica set, not separate data products. The skill asks the user which location is the canonical source (the input); the rest are replica targets. See SKILL.md Step 5._

### R1. 5 copies — schema: PRODUCT_CODE, GTIN, TITLE, SHORT_DESCRIPTION, PRODUCT_DESCRIPTION, IS_ACTIVE_PRODUCT, IRI_CATEGORY_NAME, IRI_SUBCATEGORY_NAME, PACK_SIZE, MANUFACTURER, BRAND, SUB_BRAND

- `nxd-snowflake` :: `daff_db.PRODUCT_CATALOG_SOURCE.PRODUCT_CATALOG_SOURCE`
- `daff-s3` :: `s3://output-data-product/product-catalog-source-facade-py/demo/product_catalog_source.csv`
- `daff-s3` :: `s3://output-data-product/product-catalog-source-sa-py/demo/product_catalog_source.csv`
- `daff-s3` :: `s3://output-data-product/product-catalog-source/demo/product_catalog_source.csv`
- `daff-s3` :: `s3://output-data-product/source-aligned-py/demo/product_catalog_source.csv`

### R2. 3 copies — schema: STORE_ID, NAME, STREET, CITY, STATE, ZIP, LATITUDE, LONGITUDE, PHONE, STATE_NAME, BRAND, UPDATED

- `nxd-snowflake` :: `daff_db.SEVEN_ELEVEN_SOURCE.STORES`
- `daff-s3` :: `s3://output-data-product/seven-eleven-store/demo/stores.csv`
- `daff-s3` :: `s3://output-data-product/seven-eleven-stores/demo/stores.csv`

## Unmatched Assets (5542)

_Data sources with no apparent counterpart — potential standalone inputs._

- `nxd-snowflake` :: `daff_db.ACCESS_CONTROL.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_ORDER_OTHER_BU` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_SALES_DRIVER_WEEKLY_INPUT_REFACTOR` (31 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_SALES_MANUFACTURING_DAILY_VIEW` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_AMAZON_FRESH_SALES_DAILY` (18 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.HSAT_AMAZON_PRODUCT_TITLE` (3 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_AMAZON_FRITO_CANADA` (27 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_AMAZON_FRITO_STS` (3 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_ADS_SPONSORED_PRODUCTS_PRODUCT_AD_PERFORMANCE_REPORT` (30 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BOTTLER_REPORTING.AMAZON_FRESH_BOTTLER_SALES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BOTTLER_REPORTING.MASTER_BOTTLER_REPORT` (14 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BOTTLER_REPORTING.PURE_PLAY_BOTTLER_ZIPCODE_MAPPING` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DP_NAME.INTEGERS` (1 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LATAM_ECOMMERCE.MEXICO_CASA_LEY_ECOM_MONTHLY_SALES` (6 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LATAM_ECOMMERCE.MEXICO_SCORPION_ECOM_MONTHLY_SALES` (6 cols, snowflake)
- `nxd-snowflake` :: `daff_db.RAW_MATERIAL_USAGE.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_AMAZON_MARKETING_PRODUCT_TRAFFIC_STS` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_EFFT_AMAZON_SHIPPED_COGS_MANUFACTURING_WEEKLY` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_ADS_PROFILES` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_ADS_SPONSORED_PRODUCTS_KEYWORD_PERFORMANCE_REPORT` (32 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_INVENTORY_DAILY.INVENTORY_DAILY` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_VENDOR_CENTRAL.AMAZON_VENDOR_CENTRAL_CHARGEBACKS_DELTA` (95 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BOTTLER_REPORTING.COSTCO_TO_BOTTLER_REPORT_AWS` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BOTTLER_REPORTING.PANTRYSHOP_DTC_BOTTLER_SALES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CRITEO.CRITEO_RETAIL_MEDIA_ACCOUNT_RETAILERS` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CRITEO.CRITEO_RETAIL_MEDIA_OPEN_AUCTION_LINE_ITEMS` (23 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DELIVERY.LRT_LSAT_SAP_DELIVERY_PRODUCT_GTIN_PRODUCT` (28 cols, snowflake)
- `nxd-snowflake` :: `daff_db.EFUNDAMENTALS.EFUN_PEPSI_GROWTH_SCORECARD` (17 cols, snowflake)
- `nxd-snowflake` :: `daff_db.HEB.HEB_SALES_V2` (9 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_COMPSHARE_L4` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_OOS_WAREHOUSE_RANGE_DAILY` (5 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_SHARES_SEGMENT_WEEKLY` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LATAM_ECOMMERCE.LATAM_EXCHANGE_RATES` (3 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LISTENER_PLAY_EVENTS_JAMES.LISTENER_PLAY_EVENTS` (3 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MEIJER_SALES.MEIJER_SALES` (10 cols, snowflake)
- `nxd-snowflake` :: `daff_db.ONLINE_SALES.SALES_TRANSACTIONS_RAW` (14 cols, snowflake)
- `nxd-snowflake` :: `daff_db.ORDERS.CHANNEL_ADVISOR_ORDER_DETAILS` (24 cols, snowflake)
- `nxd-snowflake` :: `daff_db.OUT_OF_STOCK.OUT_OF_STOCK_WEEKLY` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PLAYLISTS_JAMES.PLAYLIST` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PLAYLISTS_POLICY_JONATHON.PLAYLIST` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PRODUCTS.CHANNEL_ADVISOR_PRODUCT_BUFFERS` (6 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PRODUCT_CATALOG.PRODUCT_CATALOG_CUSTOMER_PRODUCT_TAGS` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PRODUCT_CATALOG.PRODUCT_CATALOG_RETAILER_SPECIFIC_MAPPING` (17 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PRODUCT_QUALITY.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SECRET_BAG.AMAZON_REVIEW` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SEVEN_ELEVEN_SALES.SALES` (9 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SNOWFLAKE_PRODUCER.INTEGERS` (1 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_VENDOR_CENTRAL.AMAZON_VENDOR_CENTRAL_CHARGEBACKS_PREV_YEAR` (95 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INNOVATION_COST.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_OOS_DAILY` (25 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART_ADS.INSTACART_ADS_DISPLAY_PRODUCTS_PERFORMANCE` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LATAM_ECOMMERCE.MEXICO_WALMART_ECOM_MONTHLY_SALES` (6 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MUSIC_TRACKS.TOP_ARTISTS_BY_COUNT` (4 cols, snowflake)
- `nxd-snowflake` :: `daff_db.NETWORK_PERFORMANCE_MONITORING.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PODCASTS_WITH_SUBDOMAIN.AUTHOR_POPULARITY` (5 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SA_SNOWFLAKE_SQL_NEW.LISTENER_PROFILES_NEW` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SEVEN_ELEVEN.SEVEN_ELEVEN_DAILY_DELIVERY_DATA` (11 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SONG_SIMILARITY.TOP_ARTISTS_MODEL` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.STRESS_013.LISTENER_PROFILES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.STRESS_024.LISTENER_PROFILES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WALMART_CONNECT.WALMART_CONNECT_PLACEMENT_PERFORMANCE` (21 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MARKET_SHARE.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PRODUCTS.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PRODUCT_CATALOG.PRODUCT_CATALOG_ASINS` (34 cols, snowflake)
- `nxd-snowflake` :: `daff_db.STRESS_028.LISTENER_PROFILES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.STRESS_082.LISTENER_PROFILES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.TARGET_AUDIENCE_PROFILES.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.UPS.UPS_SHIPPING_COST` (251 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WAREHOUSE_UTILIZATION.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.TBD_SRM_PRICING.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_GEO_SALES_INSIGHTS` (20 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_INVENTORY_MANUFACTURING_WEEKLY` (23 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_WEEKLY_SALES` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.ITEM_COMPARISON` (19 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_AMAZON_GEO_SALES` (17 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_DSP_REPORT_AUDIENCE` (95 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DOORDASH.DOORDASH_ADS_SPONSORED_PRODUCTS_PLACEMENT_PERFORMANCE` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.FULL_SALES.FULL_SALES` (3 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_SHIPPED_REVENUE_SOURCING_WEEKLY_VIEW` (34 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_AD_COM_CREATIVE_CAMPAIGNS.AMAZON_AD_COM_CREATIVE_CAMPAIGNS` (43 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_ADS_SPONSORED_BRANDS_ADS` (17 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_ADS_SP_AD_GROUPS` (14 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_DSP_ENTITY_ORDER` (27 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_DSP_REPORT_CAMPAIGN` (254 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_VENDOR_CENTRAL.AMAZON_VENDOR_CENTRAL_PURCHASE_ORDER_ITEMS_NON_CANADIAN_EXTENDED` (43 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BOTTLER_REPORTING.DEWSTORE_DTC_BOTTLER_SALES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BOTTLER_REPORTING.WALMART_BOTTLER_REPORT` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BOXED_B2B.BOXED_B2B_SALES` (15 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CASH_FLOW.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DOORDASH.DOOR_DASH_ADS_SPONSORED_PRODUCTS_AD_GROUPS` (11 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LATAM_ECOMMERCE.LATAM_MEXICO_PRODUCT_CATALOG` (9 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LISTENER_PROFILE_BDJ.LISTENER_PROFILES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_DSP_ENTITY_CREATIVE` (10 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_VENDOR_EVENTS_SOURCE.INVENTORY_EVENTS_INPUT` (9 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CAMPAIGN_PERFORMANCE.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CRITEO.CRITEO_RETAIL_MEDIA_ATTRIBUTED_TRANSACTIONS_PERFORMANCE` (16 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CRITEO.CRITEO_RETAIL_MEDIA_LINE_ITEM_KEYWORDS` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CUSTOMER_SEGMENTATION.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DOCUMENT_EMBEDDING.MUSIC_TRACKS` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DOORDASH.DOOR_DASH_ADS_SPONSORED_PRODUCTS_PLACEMENT_BIDS` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.EFUNDAMENTALS.EFUN_PEPSI_PRICING` (22 cols, snowflake)
- `nxd-snowflake` :: `daff_db.EFUNDAMENTALS.EFUN_PEPSI_REVIEWS` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.ENERGY_CONSUMPTION.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.HYVEE.HYVEE_SALES` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_DAILY_SALES` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_MONTHLY_BRAND_MARKET_SALES` (22 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_MONTHLY_PEP_REGIONAL_SALES` (10 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART_ADS.INSTACART_ADS_PROMOTION_PRODUCTS` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART_ADS.INSTACART_ADS_SPONSORED_PRODUCT_CAMPAIGNS_HISTORY` (20 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LATAM_ECOMMERCE.MEXICO_COSTCO_ECOM_MONTHLY_SALES` (6 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LOGISTICS_TRACKING.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MCP_LISTENER_PLAY_EVENTS.MCP_LISTENER_PLAY_EVENTS_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MULTI_CHANNEL_SALES.PRODUCTS` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MULTI_CHANNEL_SALES.SALES_UNIT_SELL_OUT` (10 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PLAYLISTS_CUSTOM_NAME.PLAYLIST` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PLAYLISTS_POLICY_JM.PLAYLIST` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SALES.SALES` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SAMS_CLUB.SAMS_CLUB_DOTCOM_SALES` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SEVEN_ELEVEN_INVENTORY.INVENTORY` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SEVEN_ELEVEN_INVENTORY_WEEKLY.INVENTORY_WEEKLY` (9 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SONG_SIMILARITY.SONG_SIMILARITY_EMBD` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CALL_CENTER_PERFORMANCE.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CONTRACT_SECRET.NYC_YELLOW_TAXI` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_RETAILER_DAILY_SALES` (18 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LATAM_ECOMMERCE.MEXICO_RETAILERS_MONTHLY_SALES_PROCESSED` (18 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MULTI_CHANNEL_SALES.EMERGING_PRODUCTS` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MUSIC_TRACKS.MUSIC_TRACKS` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PRODUCTS.CHANNEL_ADVISOR_PRODUCT_LABEL_HISTORY` (6 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PROMOTIONS_DEMAND.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SAMS_CLUB.SAMS_CLUB_PICKUP_SALES` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SAMS_DOTCOM.SAMS_DOTCOM_SALES` (22 cols, snowflake)
- `nxd-snowflake` :: `daff_db.STRESS_051.LISTENER_PROFILES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.STRESS_068.LISTENER_PROFILES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.TOP_ARTISTS_BD.TOP_ARTISTS_MODEL` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.TOP_ARTISTS_BDDEMO.USER_TOP_10_TRACKS` (1 cols, snowflake)
- `nxd-snowflake` :: `daff_db.USER_TOP_TRACKS.USER_TOP_10_TRACKS` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.VENDORS.IRI_ALBERTSONS_PRODUCT_SALES` (18 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WALMART_CONNECT.WALMART_CONNECT_AD_ITEM_PERFORMANCE` (39 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WALMART_CONNECT.WALMART_CONNECT_BRAND_PERFORMANCE` (20 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WALMART_CONNECT.WALMART_CONNECT_CATEGORIES` (11 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WALMART_CONNECT.WALMART_CONNECT_PLACEMENT_BID_MULTIPLIERS` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WALMART_CONNECT.WALMART_CONNECT_SBA_PROFILES` (14 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART_ADS.INSTACART_ADS_DISPLAY_KEYWORDS_PERFORMANCE` (14 cols, snowflake)
- `nxd-snowflake` :: `daff_db.SOFTWARE_LICENSE_COMPLIANCE.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.VENDORS.IRI_MEIJER_FACT_PERIOD_SALES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WALMART_CONNECT.WALMART_CONNECT_KEYWORD_PERFORMANCE` (27 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WALMART_CONNECT.WALMART_CONNECT_PAGE_TYPE_PERFORMANCE` (21 cols, snowflake)
- `nxd-snowflake` :: `daff_db.WALMART_CONNECT.WALMART_CONNECT_STATS_HOURLY` (9 cols, snowflake)
- `nxd-snowflake` :: `daff_db.ADUSA_BKP.ADUSA_OOS_DETAIL_V2` (28 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_NET_PPM_WEEKLY` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_ORDERED_REVENUE_MANUFACTURING_WEEKLY_VIEW` (31 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_SALES_SOURCING_WEEKLY_VIEW` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.AMAZON_VENDOR_CENTRAL_BRAND` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.HSAT_PRODUCT_AMAZON_WEEKLY_SALES` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_AMAZON_ADSP_TRAFFIC` (37 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_AMAZON_FRITO_CANADA_V2` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_ADS_SP_TARGETS` (18 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_VENDOR_CENTRAL.AMAZON_VENDOR_CENTRAL_PURCHASE_ORDER_GLOBAL` (14 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CUSTOMERS.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_PRODUCT` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_AMAZON_MARKETING_DISPLAY_TRAFFIC_STS` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_API.AMAZON_ADS_SP_CAMPAIGNS` (19 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_SALES_DAILY.SALES_DAILY` (18 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_VENDOR_CENTRAL.AMAZON_VENDOR_CENTRAL_AUTOMATION_FORECAST_INVENTORY` (132 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BOTTLER_REPORTING.KROGER_BOTTLER_SALES` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DASHMART.DASHMART_SALES_V2` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DDAS_EPOS_ECOMM.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DDAS_TPM.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART_ADS.INSTACART_ADS_PROMOTION_PRODUCTS_PERFORMANCE` (10 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART_ADS.INSTACART_ADS_SPONSORED_PRODUCT_CAMPAIGNS` (18 cols, snowflake)
- `nxd-snowflake` :: `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES_SOURCE_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.KNOWLEDGE_BASE_USAGE.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LATAM_ECOMMERCE.MEXICO_GLUP_ECOM_MONTHLY_SALES` (6 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MEIJER_SALES.MEIJER_WEEKLY_SALES` (9 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON.LSAT_AMAZON_MARKETING_BRANDS_CONVERSIONS` (16 cols, snowflake)
- `nxd-snowflake` :: `daff_db.AMAZON_VENDOR_EVENTS_SOURCE_3.SALES_EVENTS` (10 cols, snowflake)
- `nxd-snowflake` :: `daff_db.BRAND_SENTIMENT.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CONTRACTS_V2_SNOWFLAKE_GX.NYC_YELLOW_TAXI` (13 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CRITEO.CRITEO_RETAIL_MEDIA_ACCOUNTS` (12 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CRITEO.CRITEO_RETAIL_MEDIA_ADVERTISED_PRODUCT_PERFORMANCE` (19 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CRITEO.CRITEO_RETAIL_MEDIA_KEYWORD_PERFORMANCE` (18 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CRITEO.CRITEO_RETAIL_MEDIA_PROMOTED_PRODUCTS` (9 cols, snowflake)
- `nxd-snowflake` :: `daff_db.CSAT.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DELIVERY.LRT_LSAT_DELIVERY_PRODUCT_GTIN_PRODUCT_EFFECTIVITY` (6 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DISASTER_RECOVERY_READINESS.DATA` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DOCUMENT_EMBEDDING.DOCUMENT_EMBEDDING` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.DP_NAME.SOURCE_ALIGNED_USERS` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.EFUNDAMENTALS.EFUN_PEPSI_COMPLIANCE` (48 cols, snowflake)
- `nxd-snowflake` :: `daff_db.EFUNDAMENTALS.EFUN_PEPSI_SEARCH_RANKING` (17 cols, snowflake)
- `nxd-snowflake` :: `daff_db.FULFILLMENTS.CHANNEL_ADVISOR_DC_FULFILLMENTS_HISTORY` (4 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_RETAILER_SALES` (18 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART.INSTACART_ZIPCODE_MARKET_MAPPINGS` (2 cols, snowflake)
- `nxd-snowflake` :: `daff_db.INSTACART_ADS.INSTACART_ADS_SPONSORED_PRODUCT_KEYWORDS_HISTORY` (15 cols, snowflake)
- `nxd-snowflake` :: `daff_db.KROGER.M6_RETAIL_SALES_ARCHIVE` (19 cols, snowflake)
- `nxd-snowflake` :: `daff_db.LATAM_ECOMMERCE.MEXICO_HEB_ECOM_MONTHLY_SALES` (6 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY` (8 cols, snowflake)
- `nxd-snowflake` :: `daff_db.MULTI_CHANNEL_SALES.SALES` (9 cols, snowflake)
- `nxd-snowflake` :: `daff_db.NYC_TRIPS.TRIPS_CLONE` (45 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PLAYLISTS_POLICY_JMO.PLAYLIST` (7 cols, snowflake)
- `nxd-snowflake` :: `daff_db.PRODUCTS.CHANNEL_ADVISOR_PRODUCT_ATTRIBUTES` (4 cols, snowflake)
- _...and 5342 more_

## Failed Services

- `nxd-adls` — ClientAuthenticationError: Authentication failed: AADSTS7000222: The provided client secret keys for app '6b2d1d92-7018-4182-b70e-821127bec509' are expired. Visit the Azure portal to create new keys for your app: https://aka.ms/NewClientSecret, or consider using certificate credentials for added security: https://aka.ms/certCreds. Trace ID: 7d8fc6a9-2d93-4df0-99de-412c5a1d1700 Correlation ID: 4ee4cf07-6380-403e-bd20-593f20c20f82 Timestamp: 2026-05-20 23:27:57Z

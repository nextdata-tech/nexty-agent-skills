# Mesh Assets Report

_Generated 2026-05-18 from inv3.json_

- **Infra profile:** `ecommerce-demo`
- **Services inspected:** 5
- **Data assets considered:** 423 (294 excluded by rules)
- **Candidate data products:** 793
- **Duplicate services:** 0 | **Failed services:** 0

Model schemas for each candidate are in `/Users/bill/src/nexty-agent-skills/billg-temp/mesh-assets-ecommerce-demo-models.md`.

## Candidate Data Products

### Domain: customer

#### 1. `amazon-reviews`

- **Suggested data product name:** `amazon-reviews`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/amazon-reviews/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - asset name match: 'amazon-reviews'
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 2. `amazon-review`

- **Suggested data product name:** `amazon-review`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS_TEST.AMAZON_REVIEW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 3. `amazon-reviews`

- **Suggested data product name:** `amazon-reviews`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEWS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 4. `amazon-review`

- **Suggested data product name:** `amazon-review`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 5. `amazon-reviews`

- **Suggested data product name:** `amazon-reviews`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews-test/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `adls://yogeshdata/amazon-reviews/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Evidence:**
  - cross-service: adls -> nxd-adls
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 6. `amazon-review`

- **Suggested data product name:** `amazon-review`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews-test/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS_TEST.AMAZON_REVIEW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 7. `amazon-reviews`

- **Suggested data product name:** `amazon-reviews`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews-test/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEWS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 8. `amazon-review`

- **Suggested data product name:** `amazon-review`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews-test/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 9. `69bdd885-da4b-4708-ac31-40ba294165d2`

- **Suggested data product name:** `69bdd885-da4b-4708-ac31-40ba294165d2`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/amazon-reviews/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/69bdd885-da4b-4708-ac31-40ba294165d2/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 10. `amazon-review`

- **Suggested data product name:** `amazon-review`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/69bdd885-da4b-4708-ac31-40ba294165d2/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS_TEST.AMAZON_REVIEW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 11. `amazon-reviews`

- **Suggested data product name:** `amazon-reviews`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/69bdd885-da4b-4708-ac31-40ba294165d2/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEWS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 12. `amazon-review`

- **Suggested data product name:** `amazon-review`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/69bdd885-da4b-4708-ac31-40ba294165d2/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 13. `amazon-review`

- **Suggested data product name:** `amazon-review`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/amazon-reviews/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS_TEST.AMAZON_REVIEW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 14. `amazon-reviews`

- **Suggested data product name:** `amazon-reviews`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/amazon-reviews/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEWS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 15. `amazon-review`

- **Suggested data product name:** `amazon-review`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/amazon-reviews/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']

#### 16. `amazon-reviews`

- **Suggested data product name:** `amazon-reviews`
- **Domain:** `customer`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence low)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews-test/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/amazon-reviews/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - shared namespace: adls://lowerenvsdatanxd
  - schema jaccard=1.00, shared distinctive cols=['average_rating', 'brand', 'category', 'helpful_vote', 'item_id', 'main_category']
  - same-service pair — low confidence of being source-aligned

### Domain: market-intelligence

#### 17. `dividend-sustainability`

- **Suggested data product name:** `dividend-sustainability`
- **Domain:** `market-intelligence`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.COMPETITOR_GROWTH_ANALYSIS.DIVIDEND_SUSTAINABILITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['bank', 'dividend_growth_vs_ocf_growth', 'dividend_per_share', 'dividend_yield_trend', 'ocf_trend', 'operating_cash_flow_thousands']

#### 18. `growth`

- **Suggested data product name:** `growth`
- **Domain:** `market-intelligence`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/639ec880-0c84-41ef-b78c-954fe0027bd2/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.COMPETITOR_GROWTH_ANALYSIS.GROWTH`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['annual_return', 'close', 'net_income', 'net_income_growth', 'revenue_growth', 'symbol']

### Domain: product

#### 19. `57300a35-4bbf-4971-9008-43bd27fb8f90`

- **Suggested data product name:** `57300a35-4bbf-4971-9008-43bd27fb8f90`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-input-data-product/nxd-tutorials/`
  - service: `s3-input`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-input`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/57300a35-4bbf-4971-9008-43bd27fb8f90/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-input -> adls
  - schema jaccard=1.00, shared distinctive cols=['accounting_date', 'chargeback_cost_usd', 'collection_agent', 'country_code', 'creation_date', 'currency_code']

#### 20. `lowerenvs-output-data-product`

- **Suggested data product name:** `lowerenvs-output-data-product`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/15eaa801-5bc4-4100-ae22-c66cee7c1ad2/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Evidence:**
  - cross-service: adls -> s3-output
  - schema jaccard=1.00, shared distinctive cols=['price', 'product_name', 'quantity', 'sale_date', 'transaction_id']

#### 21. `lowerenvs-output-data-product`

- **Suggested data product name:** `lowerenvs-output-data-product`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Evidence:**
  - cross-service: adls -> s3-output
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 22. `lowerenvsdatanxd`

- **Suggested data product name:** `lowerenvsdatanxd`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd//`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-output -> adls
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 23. `tables`

- **Suggested data product name:** `tables`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/demo/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-output -> adls
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 24. `demo`

- **Suggested data product name:** `demo`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/sourcedata/SAPPM/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `s3://lowerenvs-output-data-product/demo/`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Evidence:**
  - cross-service: nxd-adls -> s3-output
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 25. `product-catalog`

- **Suggested data product name:** `product-catalog`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/demo/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.PRODUCT_CATALOG.PRODUCT_CATALOG`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 26. `nightly`

- **Suggested data product name:** `nightly`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Evidence:**
  - cross-service: adls -> s3-output
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 27. `delta-log`

- **Suggested data product name:** `delta-log`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/output/NEXT_DATA_OS/` — partitioned by `['part_seg2', 'part_seg3', 'part_seg4']`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - schema jaccard=1.00, shared distinctive cols=['add', 'domainmetadata', 'metadata', 'protocol', 'remove', 'txn']

#### 28. `tables`

- **Suggested data product name:** `tables`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/sourcedata/SAPPM/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 29. `product-catalog`

- **Suggested data product name:** `product-catalog`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/` — partitioned by `['part_seg6']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.PRODUCT_CATALOG.PRODUCT_CATALOG`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 30. `home-loan-rates`

- **Suggested data product name:** `home-loan-rates`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/547f2d92-8194-4972-b5ef-cf4357320dca/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.HOME_LOAN_RATES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['bank', 'loan_term', 'max_loan', 'max_lvr', 'min_loan', 'min_lvr']

#### 31. `tables`

- **Suggested data product name:** `tables`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/podcasts-source/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - schema jaccard=1.00, shared distinctive cols=['author', 'episode_description', 'episode_duration', 'episode_id', 'episode_title', 'genre']

#### 32. `emerging-products`

- **Suggested data product name:** `emerging-products`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/dd975e49-952e-42ae-8ff0-5a4d802f40ae/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.EMERGING_PRODUCTS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['attention_score', 'first_detected_date', 'lagging_channels', 'primary_channel', 'product_id', 'product_name']

#### 33. `term-deposits`

- **Suggested data product name:** `term-deposits`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/dea1e340-213d-4bf1-bc3a-9ae9b11a7219/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.TERM_DEPOSITS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['annual_rate', 'bank', 'maturity_rate', 'max_amount', 'max_term', 'min_amount']

#### 34. `product-catalog`

- **Suggested data product name:** `product-catalog`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/wholesale-sales/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.PRODUCT_CATALOG.PRODUCT_CATALOG`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 35. `product-catalog`

- **Suggested data product name:** `product-catalog`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/sourcedata/SAPPM/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.PRODUCT_CATALOG.PRODUCT_CATALOG`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 36. `fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc`

- **Suggested data product name:** `fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-input-data-product/nxd-tutorials/`
  - service: `s3-input`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-input`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-input -> adls
  - schema jaccard=0.97, shared distinctive cols=['accounting_date', 'chargeback_cost_usd', 'collection_agent', 'country_code', 'creation_date', 'currency_code']

#### 37. `17c1ac67-25f2-4d3c-8bf2-184d95b68bea`

- **Suggested data product name:** `17c1ac67-25f2-4d3c-8bf2-184d95b68bea`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-input-data-product/nxd-tutorials/`
  - service: `s3-input`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-input`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/17c1ac67-25f2-4d3c-8bf2-184d95b68bea/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-input -> adls
  - schema jaccard=0.91, shared distinctive cols=['accounting_date', 'chargeback_cost_usd', 'collection_agent', 'country_code', 'creation_date', 'currency_code']

#### 38. `fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc`

- **Suggested data product name:** `fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/17c1ac67-25f2-4d3c-8bf2-184d95b68bea/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - shared namespace: adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables
  - schema jaccard=0.89, shared distinctive cols=['accounting_date', 'chargeback_cost_usd', 'collection_agent', 'country_code', 'creation_date', 'currency_code']

#### 39. `7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b`

- **Suggested data product name:** `7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-output -> adls
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 40. `lowerenvsdatanxd`

- **Suggested data product name:** `lowerenvsdatanxd`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd//`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-output -> adls
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 41. `lowerenvs-output-data-product`

- **Suggested data product name:** `lowerenvs-output-data-product`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Evidence:**
  - cross-service: adls -> s3-output
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 42. `d68a1bdc-4b0f-425f-b589-d6b14369bda3`

- **Suggested data product name:** `d68a1bdc-4b0f-425f-b589-d6b14369bda3`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - shared namespace: adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 43. `ef7a79aa-9242-4434-a9ea-d2bc0c850fab`

- **Suggested data product name:** `ef7a79aa-9242-4434-a9ea-d2bc0c850fab`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/04cec544-2e5a-499c-bd06-6da592a21132/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/ef7a79aa-9242-4434-a9ea-d2bc0c850fab/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - shared namespace: adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables
  - schema jaccard=0.62, shared distinctive cols=['event_data', 'event_type', 'original_timestamp', 'processed_at', 'user_id']

#### 44. `d68a1bdc-4b0f-425f-b589-d6b14369bda3`

- **Suggested data product name:** `d68a1bdc-4b0f-425f-b589-d6b14369bda3`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-output -> adls
  - schema jaccard=0.62, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 45. `metadata`

- **Suggested data product name:** `metadata`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`
  - service: `s3-input`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-input`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/4da13333-0cfd-4567-8e0b-6dc56631aaf0/_iceberg/metadata/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-input -> adls
  - asset name match: 'metadata'

#### 46. `metadata`

- **Suggested data product name:** `metadata`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/playlists/dtest/metadata/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`
  - service: `s3-input`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-input`
- **Evidence:**
  - cross-service: nxd-adls -> s3-input
  - asset name match: 'metadata'

#### 47. `metadata`

- **Suggested data product name:** `metadata`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/playlists/dtest/metadata/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`
  - service: `s3-input`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-input`
- **Evidence:**
  - cross-service: nxd-adls -> s3-input
  - asset name match: 'metadata'

#### 48. `metadata`

- **Suggested data product name:** `metadata`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`
  - service: `s3-input`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-input`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/4da13333-0cfd-4567-8e0b-6dc56631aaf0/_iceberg/metadata/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-input -> adls
  - asset name match: 'metadata'

#### 49. `metadata`

- **Suggested data product name:** `metadata`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/playlists/dtest/metadata/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`
  - service: `s3-input`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-input`
- **Evidence:**
  - cross-service: nxd-adls -> s3-input
  - asset name match: 'metadata'

#### 50. `metadata`

- **Suggested data product name:** `metadata`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/playlists/dtest/metadata/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `s3://lowerenvs-input-data-product/iceberg/default/products/metadata/`
  - service: `s3-input`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-input`
- **Evidence:**
  - cross-service: nxd-adls -> s3-input
  - asset name match: 'metadata'

#### 51. `metadata`

- **Suggested data product name:** `metadata`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/playlists/dtest/metadata/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/4da13333-0cfd-4567-8e0b-6dc56631aaf0/_iceberg/metadata/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - asset name match: 'metadata'

#### 52. `metadata`

- **Suggested data product name:** `metadata`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/playlists/dtest/metadata/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/4da13333-0cfd-4567-8e0b-6dc56631aaf0/_iceberg/metadata/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - asset name match: 'metadata'

#### 53. `57300a35-4bbf-4971-9008-43bd27fb8f90`

- **Suggested data product name:** `57300a35-4bbf-4971-9008-43bd27fb8f90`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence low)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/fb7c4e52-a05c-4cd3-a6d7-50f732cb4ecc/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/57300a35-4bbf-4971-9008-43bd27fb8f90/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - shared namespace: adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables
  - schema jaccard=0.97, shared distinctive cols=['accounting_date', 'chargeback_cost_usd', 'collection_agent', 'country_code', 'creation_date', 'currency_code']
  - same-service pair — low confidence of being source-aligned

#### 54. `57300a35-4bbf-4971-9008-43bd27fb8f90`

- **Suggested data product name:** `57300a35-4bbf-4971-9008-43bd27fb8f90`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence low)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/17c1ac67-25f2-4d3c-8bf2-184d95b68bea/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/57300a35-4bbf-4971-9008-43bd27fb8f90/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - shared namespace: adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables
  - schema jaccard=0.91, shared distinctive cols=['accounting_date', 'chargeback_cost_usd', 'collection_agent', 'country_code', 'creation_date', 'currency_code']
  - same-service pair — low confidence of being source-aligned

#### 55. `westpac-term-deposits`

- **Suggested data product name:** `westpac-term-deposits`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence low)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/dea1e340-213d-4bf1-bc3a-9ae9b11a7219/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.WESTPAC_TERM_DEPOSITS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.40, shared distinctive cols=['maturity_rate', 'max_amount', 'max_term', 'min_amount', 'min_term', 'monthly_rate']

#### 56. `term-deposits`

- **Suggested data product name:** `term-deposits`
- **Domain:** `product`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence low)
- **Input data source:**
  - location: `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.WESTPAC_TERM_DEPOSITS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Output data source:**
  - location: `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.TERM_DEPOSITS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - shared namespace: lowerenvs_db.product_competitiveness
  - schema jaccard=0.40, shared distinctive cols=['maturity_rate', 'max_amount', 'max_term', 'min_amount', 'min_term', 'monthly_rate']

### Domain: sales

#### 57. `lowerenvs-output-data-product`

- **Suggested data product name:** `lowerenvs-output-data-product`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Evidence:**
  - cross-service: nxd-adls -> s3-output
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 58. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 59. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 60. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 61. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 62. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 63. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 64. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 65. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 66. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 67. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 68. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 69. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 70. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 71. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 72. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 73. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 74. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 75. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 76. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 77. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 78. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 79. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 80. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 81. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 82. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 83. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 84. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 85. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 86. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 87. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 88. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 89. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 90. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 91. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 92. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 93. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 94. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 95. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 96. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 97. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 98. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 99. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 100. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 101. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 102. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 103. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 104. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 105. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 106. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 107. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 108. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 109. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 110. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 111. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 112. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 113. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 114. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 115. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 116. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 117. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 118. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 119. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 120. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 121. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 122. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 123. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 124. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 125. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 126. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 127. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 128. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 129. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 130. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 131. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 132. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 133. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 134. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 135. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 136. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 137. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 138. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 139. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 140. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 141. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 142. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 143. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 144. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 145. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 146. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 147. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 148. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 149. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 150. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 151. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 152. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 153. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 154. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 155. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 156. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 157. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 158. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 159. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 160. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 161. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 162. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 163. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 164. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 165. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 166. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 167. `demo`

- **Suggested data product name:** `demo`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/online-sales/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `s3://lowerenvs-output-data-product/demo/`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Evidence:**
  - cross-service: adls -> s3-output
  - schema jaccard=1.00, shared distinctive cols=['cashier_id', 'discount_applied', 'payment_method', 'quantity_sold', 'revenue', 'store_id']

#### 168. `point-of-sale-revenue`

- **Suggested data product name:** `point-of-sale-revenue`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/demo/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.ONLINE_SALES_RAW.POINT_OF_SALE_REVENUE`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['cashier_id', 'discount_applied', 'payment_method', 'quantity_sold', 'revenue', 'store_id']

#### 169. `point-of-sale-revenue`

- **Suggested data product name:** `point-of-sale-revenue`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/demo/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.ONLINE_SALES.POINT_OF_SALE_REVENUE`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['cashier_id', 'discount_applied', 'payment_method', 'quantity_sold', 'revenue', 'store_id']

#### 170. `wholesale-sales`

- **Suggested data product name:** `wholesale-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/demo/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/wholesale-sales/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: s3-output -> adls
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 171. `walmart-sales`

- **Suggested data product name:** `walmart-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/demo/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.WHOLESALE_SALES.WALMART_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 172. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778853104117_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 173. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778845290894_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 174. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1779064486604_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 175. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1779064674157_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 176. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778625638347_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 177. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778978258451_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 178. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1779064664782_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 179. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778840139465_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 180. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778854475570_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 181. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778891653436_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 182. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778967166355_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 183. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778835953765_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 184. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778855374903_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 185. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778846193858_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 186. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778852205480_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 187. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product/nightly/` — partitioned by `['part_seg0']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778978235793_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 188. `walmart-sales`

- **Suggested data product name:** `walmart-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/` — partitioned by `['part_seg6']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.WHOLESALE_SALES.WALMART_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 189. `7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b`

- **Suggested data product name:** `7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 190. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 191. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 192. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 193. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 194. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 195. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 196. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 197. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 198. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 199. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 200. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 201. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 202. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 203. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 204. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 205. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 206. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 207. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 208. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 209. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 210. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 211. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 212. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 213. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 214. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 215. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 216. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 217. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 218. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 219. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 220. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 221. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 222. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 223. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 224. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 225. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 226. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 227. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 228. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 229. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 230. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 231. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 232. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 233. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 234. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 235. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 236. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 237. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 238. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 239. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 240. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 241. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 242. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 243. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 244. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 245. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 246. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 247. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 248. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 249. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 250. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 251. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 252. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 253. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 254. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 255. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 256. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 257. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 258. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 259. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 260. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 261. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 262. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 263. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 264. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 265. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 266. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 267. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 268. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 269. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 270. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 271. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 272. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 273. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 274. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 275. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 276. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 277. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 278. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 279. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 280. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 281. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 282. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 283. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 284. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 285. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 286. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 287. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 288. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 289. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 290. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 291. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 292. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 293. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 294. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 295. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 296. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 297. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 298. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 299. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778853104117_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 300. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778845290894_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 301. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1779064486604_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 302. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1779064674157_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 303. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778625638347_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 304. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778978258451_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 305. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1779064664782_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 306. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778840139465_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 307. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778854475570_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 308. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778891653436_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 309. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778967166355_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 310. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778835953765_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 311. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778855374903_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 312. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778846193858_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 313. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778852205480_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 314. `sales-summary`

- **Suggested data product name:** `sales-summary`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/cfbbf77f-cc28-427a-859a-5593ce74f820/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_REPORT_1778978235793_CLI_SF_SEQ.SALES_SUMMARY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_name', 'total_quantity', 'total_revenue']

#### 315. `trending-sales`

- **Suggested data product name:** `trending-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['momentum_score', 'product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend']

#### 316. `lowerenvsdatanxd`

- **Suggested data product name:** `lowerenvsdatanxd`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd//`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 317. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 318. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 319. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 320. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 321. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 322. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 323. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 324. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 325. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 326. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 327. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 328. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 329. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 330. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 331. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 332. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 333. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 334. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 335. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 336. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 337. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 338. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 339. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 340. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 341. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 342. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 343. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 344. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 345. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 346. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 347. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 348. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 349. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 350. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 351. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 352. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 353. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 354. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 355. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 356. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 357. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 358. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 359. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 360. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 361. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 362. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 363. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 364. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 365. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 366. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 367. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 368. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 369. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 370. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 371. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 372. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 373. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 374. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 375. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 376. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 377. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 378. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 379. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 380. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 381. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 382. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 383. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 384. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 385. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 386. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 387. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 388. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 389. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 390. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 391. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 392. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 393. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 394. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 395. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 396. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 397. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 398. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 399. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 400. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 401. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 402. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 403. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 404. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 405. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 406. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 407. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 408. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 409. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 410. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 411. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 412. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 413. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 414. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 415. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 416. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 417. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 418. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 419. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 420. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 421. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 422. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 423. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 424. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 425. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 426. `point-of-sale-revenue`

- **Suggested data product name:** `point-of-sale-revenue`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/online-sales/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.ONLINE_SALES_RAW.POINT_OF_SALE_REVENUE`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['cashier_id', 'discount_applied', 'payment_method', 'quantity_sold', 'revenue', 'store_id']

#### 427. `point-of-sale-revenue`

- **Suggested data product name:** `point-of-sale-revenue`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/online-sales/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.ONLINE_SALES.POINT_OF_SALE_REVENUE`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['cashier_id', 'discount_applied', 'payment_method', 'quantity_sold', 'revenue', 'store_id']

#### 428. `sales-value`

- **Suggested data product name:** `sales-value`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata//` — partitioned by `['part_seg0']`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/sales-value/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - schema jaccard=1.00, shared distinctive cols=['processed_at', 'product_id', 'quantity', 'region', 'transaction_date', 'unit_price']

#### 429. `gross-sales`

- **Suggested data product name:** `gross-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/sales-value/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_VALUE.GROSS_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['processed_at', 'product_id', 'quantity', 'region', 'transaction_date', 'unit_price']

#### 430. `wholesale-sales`

- **Suggested data product name:** `wholesale-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/sourcedata/SAPPM/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/wholesale-sales/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 431. `walmart-sales`

- **Suggested data product name:** `walmart-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/wholesale-sales/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.WHOLESALE_SALES.WALMART_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 432. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 433. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 434. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 435. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 436. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 437. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 438. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 439. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 440. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 441. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 442. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 443. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 444. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 445. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 446. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 447. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 448. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 449. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 450. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 451. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 452. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 453. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 454. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 455. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 456. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 457. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 458. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 459. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 460. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 461. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 462. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 463. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 464. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 465. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 466. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 467. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 468. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 469. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 470. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 471. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 472. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 473. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 474. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 475. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 476. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 477. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 478. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 479. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 480. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 481. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 482. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 483. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 484. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 485. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 486. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 487. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 488. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 489. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 490. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 491. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 492. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 493. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 494. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 495. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 496. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 497. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 498. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 499. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 500. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 501. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 502. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 503. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 504. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 505. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 506. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 507. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 508. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 509. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 510. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 511. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 512. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 513. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 514. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 515. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 516. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 517. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 518. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 519. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 520. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 521. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 522. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 523. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 524. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 525. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 526. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 527. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 528. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 529. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 530. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 531. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 532. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 533. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 534. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 535. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 536. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 537. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 538. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 539. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 540. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 541. `gross-sales`

- **Suggested data product name:** `gross-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata//` — partitioned by `['part_seg0']`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_VALUE.GROSS_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['processed_at', 'product_id', 'quantity', 'region', 'transaction_date', 'unit_price']

#### 542. `walmart-sales`

- **Suggested data product name:** `walmart-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/sourcedata/SAPPM/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.WHOLESALE_SALES.WALMART_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['brand', 'gtin', 'iri_category_name', 'iri_subcategory_name', 'is_active_product', 'manufacturer']

#### 543. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.89, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 544. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.89, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 545. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.89, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 546. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=0.89, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 547. `walmart`

- **Suggested data product name:** `walmart`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/storesales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://yogeshdata/walmart/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Evidence:**
  - shared namespace: adls://yogeshdata
  - schema jaccard=0.83, shared distinctive cols=['bus_dt', 'store_nbr', 'vendor_name', 'vendor_nbr', '\ufeffwm_item_nbr']

#### 548. `lowerenvs-output-data-product`

- **Suggested data product name:** `lowerenvs-output-data-product`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Evidence:**
  - cross-service: nxd-adls -> s3-output
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 549. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 550. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 551. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 552. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 553. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 554. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 555. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 556. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 557. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 558. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 559. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 560. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 561. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 562. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 563. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 564. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 565. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 566. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 567. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 568. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 569. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 570. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 571. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 572. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 573. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 574. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 575. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 576. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 577. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 578. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 579. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 580. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 581. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 582. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 583. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 584. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 585. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 586. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 587. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 588. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 589. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 590. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 591. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 592. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 593. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 594. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 595. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 596. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 597. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 598. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 599. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 600. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 601. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 602. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 603. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 604. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 605. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 606. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 607. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 608. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 609. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 610. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 611. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 612. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 613. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 614. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 615. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 616. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 617. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 618. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 619. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 620. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 621. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 622. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 623. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 624. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 625. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 626. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 627. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 628. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 629. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 630. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 631. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 632. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 633. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 634. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 635. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 636. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 637. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 638. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 639. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 640. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 641. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 642. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 643. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 644. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 645. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 646. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 647. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 648. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 649. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 650. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 651. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 652. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 653. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 654. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 655. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 656. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 657. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.80, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 658. `sf-product-momentum`

- **Suggested data product name:** `sf-product-momentum`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `LOWERENVS_DB.SALES_INFLUENCE_INSIGHTS_SF.SF_CHANNEL_PERFORMANCE`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_INFLUENCE_INSIGHTS_SF.SF_PRODUCT_MOMENTUM`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - shared namespace: lowerenvs_db.sales_influence_insights_sf
  - schema jaccard=0.77, shared distinctive cols=['performance_index', 'period_end_date', 'product_id', 'region', 'revenue', 'revenue_change_pct']

#### 659. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 660. `trending-sales`

- **Suggested data product name:** `trending-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//` — partitioned by `['part_seg0', 'part_seg1']`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 661. `trending-sales`

- **Suggested data product name:** `trending-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/7c3c24a6-ee76-4bdf-b3a7-dcddd6544d2b/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 662. `d68a1bdc-4b0f-425f-b589-d6b14369bda3`

- **Suggested data product name:** `d68a1bdc-4b0f-425f-b589-d6b14369bda3`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 663. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 664. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 665. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 666. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 667. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 668. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 669. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539007772_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 670. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 671. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 672. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 673. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 674. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 675. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 676. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 677. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 678. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 679. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 680. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778540273936_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 681. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 682. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 683. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 684. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621956485_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 685. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 686. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778624269080_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 687. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 688. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 689. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 690. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 691. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_TESTUSER.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 692. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 693. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 694. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 695. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 696. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 697. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778838025841_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 698. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778536068796_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 699. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622819068_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 700. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 701. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 702. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 703. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 704. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 705. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778841330065_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 706. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778845290894_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 707. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 708. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 709. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 710. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 711. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 712. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 713. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 714. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 715. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 716. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 717. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538237273_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 718. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 719. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 720. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 721. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 722. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778846193858_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 723. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778666281717_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 724. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 725. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891653436_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 726. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 727. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 728. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978235793_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 729. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 730. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 731. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 732. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 733. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 734. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778622073773_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 735. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978244270_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 736. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 737. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 738. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621806620_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 739. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 740. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 741. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 742. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 743. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891460242_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 744. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778891706294_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 745. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778964357348_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 746. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 747. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778539589576_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 748. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541795188_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 749. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778583670017_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 750. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778621330624_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 751. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 752. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778538360347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 753. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778541433635_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 754. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 755. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 756. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 757. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064486604_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 758. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064664782_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 759. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778840139465_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 760. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1779064674157_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 761. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 762. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 763. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778625638347_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 764. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778671336516_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 765. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778852205480_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 766. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778854475570_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 767. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778855374903_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 768. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778967166355_03P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 769. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778835953765_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 770. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778853104117_01P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 771. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_1778978258451_02P.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 772. `trending-sales`

- **Suggested data product name:** `trending-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd//` — partitioned by `['part_seg0']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 773. `trending-sales`

- **Suggested data product name:** `trending-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/multi-channel-sales/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 774. `trending-sales`

- **Suggested data product name:** `trending-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - shared namespace: lowerenvs_db.multi_channel_sales
  - schema jaccard=0.73, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 775. `channel-sales-velocity`

- **Suggested data product name:** `channel-sales-velocity`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/d68a1bdc-4b0f-425f-b589-d6b14369bda3/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.CHANNEL_SALES_VELOCITY`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.67, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 776. `amazonspapivendorsalesevent`

- **Suggested data product name:** `amazonspapivendorsalesevent`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/sourcedata/AmazonSpApiVendorInventoryEvent/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://yogeshdata/sourcedata/AmazonSpApiVendorSalesEvent/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Evidence:**
  - shared namespace: adls://yogeshdata/sourcedata
  - schema jaccard=0.67, shared distinctive cols=['account_id', 'asin', 'end_time', 'event_time', 'event_type', 'marketplace_id']

#### 777. `net-sales`

- **Suggested data product name:** `net-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/sales-value/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_VALUE.NET_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=0.64, shared distinctive cols=['processed_at', 'product_id', 'quantity', 'region', 'transaction_date', 'unit_price']

#### 778. `net-sales`

- **Suggested data product name:** `net-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata//` — partitioned by `['part_seg0']`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_VALUE.NET_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: nxd-adls -> nxd-snowflake
  - schema jaccard=0.64, shared distinctive cols=['processed_at', 'product_id', 'quantity', 'region', 'transaction_date', 'unit_price']

#### 779. `net-sales`

- **Suggested data product name:** `net-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `LOWERENVS_DB.SALES_VALUE.GROSS_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Output data source:**
  - location: `LOWERENVS_DB.SALES_VALUE.NET_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - shared namespace: lowerenvs_db.sales_value
  - schema jaccard=0.64, shared distinctive cols=['processed_at', 'product_id', 'quantity', 'region', 'transaction_date', 'unit_price']

#### 780. `trending-sales`

- **Suggested data product name:** `trending-sales`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `s3://lowerenvs-output-data-product//`
  - service: `s3-output`
  - service URL: `infra-profile/ecommerce-demo#/services/s3-output`
- **Output data source:**
  - location: `LOWERENVS_DB.MULTI_CHANNEL_SALES.TRENDING_SALES`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: s3-output -> nxd-snowflake
  - schema jaccard=0.62, shared distinctive cols=['product_id', 'region', 'sales_change_percent', 'sales_channel', 'sales_trend', 'units_sold_last_7_days']

#### 781. `delta-log`

- **Suggested data product name:** `delta-log`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/_delta_log/` — partitioned by `['part_seg6', 'part_seg7']`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - asset name match: '_delta_log'

#### 782. `delta-log`

- **Suggested data product name:** `delta-log`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/_delta_log/` — partitioned by `['part_seg6', 'part_seg7']`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - asset name match: '_delta_log'

#### 783. `delta-log`

- **Suggested data product name:** `delta-log`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/_delta_log/` — partitioned by `['part_seg6', 'part_seg7']`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - asset name match: '_delta_log'

#### 784. `delta-log`

- **Suggested data product name:** `delta-log`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/_delta_log/` — partitioned by `['part_seg6', 'part_seg7']`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/_delta_log/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - asset name match: '_delta_log'

#### 785. `sales-transactions`

- **Suggested data product name:** `sales-transactions`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence low)
- **Input data source:**
  - location: `LOWERENVS_DB.ONLINE_SALES.SALES_TRANSACTIONS_RAW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Output data source:**
  - location: `LOWERENVS_DB.ONLINE_SALES.SALES_TRANSACTIONS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: 'raw' dataset is the input
  - shared namespace: lowerenvs_db.online_sales
  - schema jaccard=1.00, shared distinctive cols=['channel_id', 'customer_id', 'discount_applied', 'payment_method', 'product_id', 'quantity']
  - same-service pair — low confidence of being source-aligned

#### 786. `sales-transactions`

- **Suggested data product name:** `sales-transactions`
- **Domain:** `sales`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence low)
- **Input data source:**
  - location: `LOWERENVS_DB.ONLINE_SALES_RAW.SALES_TRANSACTIONS_RAW`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Output data source:**
  - location: `LOWERENVS_DB.ONLINE_SALES_RAW.SALES_TRANSACTIONS`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: 'raw' dataset is the input
  - shared namespace: lowerenvs_db.online_sales_raw
  - schema jaccard=1.00, shared distinctive cols=['channel_id', 'customer_id', 'discount_applied', 'payment_method', 'product_id', 'quantity']
  - same-service pair — low confidence of being source-aligned

### Domain: other

#### 787. `company-info`

- **Suggested data product name:** `company-info`
- **Domain:** `other`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/sec-openfigi/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SEC_OPENFIGI.COMPANY_INFO`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['cik', 'company_id', 'company_name', 'ein', 'entity_level', 'global_tickers']

#### 788. `company-info`

- **Suggested data product name:** `company-info`
- **Domain:** `other`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/sec-openfigi/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `LOWERENVS_DB.SEC_FILINGS.COMPANY_INFO`
  - service: `nxd-snowflake`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-snowflake`
- **Evidence:**
  - direction: file storage (input) -> database (output)
  - cross-service: adls -> nxd-snowflake
  - schema jaccard=1.00, shared distinctive cols=['cik', 'company_id', 'company_name', 'ein', 'entity_level', 'global_tickers']

#### 789. `testing`

- **Suggested data product name:** `testing`
- **Domain:** `other`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/testing/` — partitioned by `['part_seg1']`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://lowerenvsdatanxd/testing/`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Evidence:**
  - cross-service: nxd-adls -> adls
  - asset name match: 'testing'

#### 790. `playlist-listens`

- **Suggested data product name:** `playlist-listens`
- **Domain:** `other`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/playlists-compute-policy-test/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://yogeshdata/playlist-listens/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Evidence:**
  - shared namespace: adls://yogeshdata
  - schema jaccard=0.83, shared distinctive cols=['collaborative', 'duration_ms', 'modified_at', 'num_albums', 'num_artists', 'num_edits']

#### 791. `dremio-demo`

- **Suggested data product name:** `dremio-demo`
- **Domain:** `other`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://yogeshdata/dremio-transformed/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://yogeshdata/dremio-demo/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Evidence:**
  - shared namespace: adls://yogeshdata
  - schema jaccard=0.60, shared distinctive cols=['author', 'matches', 'title']

#### 792. `testing`

- **Suggested data product name:** `testing`
- **Domain:** `other`
- **Infra profile:** `ecommerce-demo`
- **Classification:** transformed (confidence medium)
- **Input data source:**
  - location: `adls://lowerenvsdatanxd/testing/` — partitioned by `['part_seg1']`
  - service: `adls`
  - service URL: `infra-profile/ecommerce-demo#/services/adls`
- **Output data source:**
  - location: `adls://yogeshdata/testing/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Evidence:**
  - cross-service: adls -> nxd-adls
  - asset name match: 'testing'

#### 793. `playlists`

- **Suggested data product name:** `playlists`
- **Domain:** `other`
- **Infra profile:** `ecommerce-demo`
- **Classification:** source-aligned (confidence low)
- **Input data source:**
  - location: `adls://yogeshdata/playlistshello/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Output data source:**
  - location: `adls://yogeshdata/playlists/`
  - service: `nxd-adls`
  - service URL: `infra-profile/ecommerce-demo#/services/nxd-adls`
- **Evidence:**
  - shared namespace: adls://yogeshdata
  - schema jaccard=1.00, shared distinctive cols=['album_name', 'album_uri', 'artist_name', 'artist_uri', 'duration_ms', 'pid']
  - same-service pair — low confidence of being source-aligned

## Unmatched Assets (189)

_Data sources with no apparent counterpart — potential standalone inputs._

- `s3-input` :: `s3://lowerenvs-input-data-product/iceberg/default/products/data/` (5 cols, parquet)
- `s3-input` :: `s3://lowerenvs-input-data-product/lattice-sample-data/` (9 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/mcp-minimal/` (2 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/veeva-sample/_metadata/` (8 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/veeva-sample/audit/` (8 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/veeva-sample/documents/` (14 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/veeva-sample/143501/objects/` (19 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/veeva-sample/documents/` (18 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/veeva-sample/143502/objects/` (15 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/veeva-sample/143503/objects/` (15 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/veeva-sample/143504/objects/` (14 cols, csv)
- `s3-input` :: `s3://lowerenvs-input-data-product/veeva-sample/143505/objects/` (15 cols, csv)
- `s3-output` :: `s3://lowerenvs-output-data-product/market-fraud-density/demo/` (10 cols, csv)
- `s3-output` :: `s3://lowerenvs-output-data-product/payments-testing/demo/` (8 cols, csv)
- `adls` :: `adls://lowerenvsdatanxd/credit-card-tx/` (2 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/` (0 cols, tmp)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/0bc49de9-f462-4e98-a89e-09bbf97e0cf0/` (3 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/1892fa12-5d8c-4b6f-aef3-32f0a545012d/` (41 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/1e8a8008-3477-42e0-91c7-5ce34b2531c6/` (8 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/4da13333-0cfd-4567-8e0b-6dc56631aaf0/` (1 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/509c5932-671c-4178-965e-eb8bc5ba4f70/` (1 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/71fec831-65fb-4abe-aa02-3bbf008f06a0/` (4 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/827aa703-33e8-4ffe-962f-f2481533b622/` (5 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/884c9171-4ae9-4d11-a316-67a25c095250/` (4 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/c098ea75-273b-4be6-9022-cde75d4e5560/` (4 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/daf14edd-c2bc-4da6-bab3-ad6f26ac9cc7/` (6 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/lowerenvsdata/uc/__unitystorage/catalogs/93b2d875-f5a9-4bf1-9b37-958da65bec62/tables/fb424730-ee0d-4363-bf21-ffdb5bd29a45/` (0 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/market-announcements/` (13 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/out-of-stock-insights/` (4 cols, csv)
- `adls` :: `adls://lowerenvsdatanxd/public-disclosures/` (12 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/sales-value/output/` (6 cols, csv)
- `adls` :: `adls://lowerenvsdatanxd/stock-history/` (9 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/store-sales/` (10 cols, csv)
- `adls` :: `adls://lowerenvsdatanxd/suspicious-tx/` (4 cols, parquet)
- `adls` :: `adls://lowerenvsdatanxd/testing/k8s-basic/` (2 cols, csv)
- `nxd-adls` :: `adls://yogeshdata/adls-databricks/combined/` (1 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/adls-trigger-demo/` (7 cols, csv)
- `nxd-adls` :: `adls://yogeshdata/adls-trigger-demo/multi/` (0 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/adlsdemo/` (6 cols, csv)
- `nxd-adls` :: `adls://yogeshdata/airflowbase/dags/nxd/dp/dags/` (0 cols, py)
- `nxd-adls` :: `adls://yogeshdata/airflowbase/dags/nxd/dp/airflow-example/dags/` (0 cols, txt)
- `nxd-adls` :: `adls://yogeshdata/amazon-sales-near-real-time/checkpoints/sales_hourly_aggregated/state/0/` (0 cols, snapshot)
- `nxd-adls` :: `adls://yogeshdata/amazon-sales-near-real-time/output/_spark_metadata/` (0 cols, compact)
- `nxd-adls` :: `adls://yogeshdata/amazon-sales-near-real-time/output/` (18 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/apple-sec-10ks/` (0 cols, pdf)
- `nxd-adls` :: `adls://yogeshdata/calendar-synthetic/` (7 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/ci-test-results/` (0 cols, log)
- `nxd-adls` :: `adls://yogeshdata/felipe-testing-parquet/output/` (2 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/SYNDICATED_MARKET_DATA/PET/dim_customer/` (24 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/SYNDICATED_MARKET_DATA/PET/dim_measure/country_code=AU/` (9 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/SYNDICATED_MARKET_DATA/PET/` (7 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/SYNDICATED_MARKET_DATA/PET/fact_external_data/` (30 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/` (34 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/TPM/dim_cust_sales/` (153 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/TPM/` (151 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/TPM/dim_promotion/` (221 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/TPM/dim_target_flat_file/` (40 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/TPM/fact_internal_product/` (128 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/TPM/fact_internal_product_week/` (350 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/SFDF_ONECPL/` (5 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/SFDF_ONECPL/MASTER_DATA/PRODUCT/` (39 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/SFDF_ONECPL/MASTER_DATA/REPORTING_LINE/` (11 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/SFDF_ONECPL/MASTER_DATA/UNIT/` (8 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/SFDF_ONECPL/MASTER_DATA/CUSTOMER_UNIT_LOCAL_DATA/` (26 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/SUPPLY_CHAIN_ANALYTICS/SAP/APP/DELTA/list_price_history/` (35 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/data/SUPPLY_CHAIN_ANALYTICS/SAP/APP/DELTA/vdhdr_history/` (53 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/SUPPLY_CHAIN_ANALYTICS/SAP/DELTA/` (172 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/output/currency/` (1 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/mars-parquet/wheels/` (0 cols, whl)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/DIM/DIM_GEO/` (6 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/BUSINESS/STRATEGIC_REVENUE_MANAGEMENT/SEMANTIC_AND_REPORTING/UK/conjoint/q4_2024/own_elasticity/` (7 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/BUSINESS/STRATEGIC_REVENUE_MANAGEMENT/SEMANTIC_AND_REPORTING/UK/conjoint/q4_2024/volume_flow/` (8 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/BUSINESS/STRATEGIC_REVENUE_MANAGEMENT/SILVER_BUISNESS_LAYER/DIM/DIM_GEO/country_code=UK/` (5 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/PROMOTION/Promo_Calendar/` (32 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/PROMOTION/Promo_Customers/country_code=UK/` (34 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/PROMOTION/Promo_Event_Transactions/country_code=UK/` (48 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/PROMOTION/Promo_Events/country_code=UK/` (45 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/PROMOTION/Promo_Mechanism/country_code=UK/` (2 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/PROMOTION/Promo_Tactic/country_code=UK/` (9 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/PROMOTION/Promotions/country_code=UK/` (35 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/SALES/Customer_POS/geo_cd=UK/` (58 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/SALES/Customer_Sales_Unit/country_code=UK/` (25 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/SALES/Global_Products/country_code=UK/` (39 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/SALES/Local_Products/country_code=UK/` (57 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/HARMONISED/SALES/Products/country_code=UK/` (34 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/MASTER_DATA/GEOGRAPHY/Geography/` (23 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/Currency/currency/` (7 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/PRODUCT/local_manufacturers_product_counts/` (2 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/` (0 cols, delta/_delta_log)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/Sales/sales.delta/` (14 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/Sales/sell_out.delta/` (46 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/DEMAND/STRATEGIC_REVENUE_MANAGEMENT/HARMONIZED_LAYER_ADHOC/SalesPerformance/sales_performance.delta/` (28 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/FINANCE/HARMONISED/COSTEXPPROFITABILITY/Financial_Reporting_Line/country_code=UK/` (25 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/FINANCE/HARMONISED/COSTEXPPROFITABILITY/Financial_Reporting_Line_SIMPEL/` (26 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/FINANCE/HARMONISED/COSTEXPPROFITABILITY/Financial_Transactions_Period/` (8 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL/FINANCE/HARMONISED/TAXANDTREASURY/Currency/geo_cd=UK/` (6 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/ECOMMERCE/dim_retailer_pos/CountryID=GB/RetailerID=PETBARN/` (33 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/ECOMMERCE/dim_retailer_product/CountryID=GB/RetailerID=AMAZON/` (68 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/ECOMMERCE/fact_sales/CountryID=GB/RetailerID=PETBARN/` (45 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/PHYSICAL_STORE/dim_retailer_pos/CountryID=GB/RetailerID=PETBARN/` (76 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/PHYSICAL_STORE/dim_retailer_product/CountryID=GB/RetailerID=PETSATHOME/` (54 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/PHYSICAL_STORE/fact_epos/CountryID=GB/RetailerID=PETBARN/` (38 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/SYNDICATED_MARKET_DATA/PET/dim_product/country_code=UK/db_code=AUCIRPTBRN/` (199 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/GLOBAL_XSEG_SRM_DATA_FOUNDATION/DATA_ASSET/TPM/dim_customer_tpm/0COUNTRY_pt=GB/` (21 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/SALES/Products/` (30 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/SFDF_ONECPL/EXTERNAL_ACCESS_TRANSACTIONAL_DATA/Segment_ID=11872/Original_Unit_ID=14092/Submission_Type=ACTUALS/Forecast_Version_ID=-1/Year=2024/Period=1/` (16 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/SFDF_ONECPL/MASTER_DATA/DATE/` (5 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/SFDF_ONECPL/MASTER_DATA/WEB_INTEGRATION/CUSTOMER_CFIN/` (3 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/SRM/STATIC_DATA/mars_calendar/` (7 cols, csv)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/SUPPLY_CHAIN_ANALYTICS/SAP/DELTA/list_price_history/` (19 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/SUPPLY_CHAIN_ANALYTICS/SAP/AEP/DELTA/material_attr_history/expiry_dt=2025-01-15/` (199 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/SUPPLY_CHAIN_ANALYTICS/SAP/APP/DELTA/material_attr_history/` (200 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/SUPPLY_CHAIN_ANALYTICS/SAP/APP/DELTA/vditm_history/` (173 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/output/NEXT_DATA_OS/data-product-metadata/` (6 cols, csv)
- `nxd-adls` :: `adls://yogeshdata/sinkdata/staged_sink/` (5 cols, csv)
- `nxd-adls` :: `adls://yogeshdata/sourcedata/AmazonMarketplaces/` (6 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/sourcedata/SevenElevenInventoryEvent/` (8 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/sourcedata/SevenElevenSalesEvent/` (9 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/sourcedata/SevenElevenStores/` (12 cols, parquet)
- `nxd-adls` :: `adls://yogeshdata/top-10-playlists/` (3 cols, csv)
- `nxd-adls` :: `adls://yogeshdata/walmart/synapsetest/` (5 cols, parquet)
- `nxd-snowflake` :: `LOWERENVS_DB.MULTI_CHANNEL_SALES.MULTI_CHANNEL_SALES_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.WESTPAC_HOME_LOANS` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778855374903.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SNOWFLAKE_INTEGRATION_TEST_RESTART.SNOWFLAKE_INTEGRATION_TEST_RESTART_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1779064664782.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SNOWFLAKE_INTEGRATION_TEST_V1_DRIVER.SNOWFLAKE_INTEGRATION_TEST_V1_DRIVER_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.AMAZON_REVIEWS.AMAZON_REVIEWS_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778621956485.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778541795188.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778666281717.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778671336516.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778835953765.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778978244270.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.MACQUARIE_HOME_LOANS` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.MACQUARIE_TERM_DEPOSITS` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778891653436.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_ROOT.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.COMPETITOR_GROWTH_ANALYSIS.DOCUMENTS` (3 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_SANDER_LEUNG.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.NESTED_PROMISES_DEMO.INVENTORY_LEVELS` (3 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SALES_VALUE.SALES_VALUE_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SNOWFLAKE_INTEGRATION_TEST_V1_DRIVER.TEST_OUTPUT_MODEL` (3 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.WHOLESALE_SALES.WHOLESALE_SALES_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778621806620.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778978258451.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SNOWFLAKE_OUTPUT_TEST.TEST_DATA` (3 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.COMPETITOR_GROWTH_ANALYSIS.COMPETITOR_GROWTH_ANALYSIS_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778621330624.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778891706294.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.MULTI_CHANNEL_SALES_INTERVIEW.MULTI_CHANNEL_SALES_INTERVIEW_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.ONLINE_SALES_RAW.ONLINE_SALES_RAW_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778838025841.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778853104117.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778967166355.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1779064486604.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.PRODUCT_COMPETITIVENESS.ANZ_PRODUCTS` (10 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778964357348.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_DIEGO_VALVERDE.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SEC_FILINGS.FILINGS` (6 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.MCP_MINIMAL.UPPERCASED_ITEMS` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.NESTED_PROMISES_DEMO.GROSS_PROFIT` (5 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.ONLINE_SALES.ONLINE_SALES_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778624269080.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778625638347.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778840139465.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_DIEGO_VALVERDE.REVENUE_INTELLIGENCE_DIEGO_VALVERDE_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_ROOT.REVENUE_INTELLIGENCE_ROOT_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_TESTUSER.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SEC_FILINGS_SOURCE.SEC_FILINGS_SOURCE_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778583670017.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.RAW_OPS.USERS_RAW` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778978235793.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SALES_INFLUENCE_INSIGHTS_SF.SF_BREAKOUT_PRODUCTS` (8 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SNOWFLAKE_INTEGRATION_TEST_RESTART.TEST_OUTPUT_MODEL` (3 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778841330065.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.PRODUCT_CATALOG.PRODUCT_CATALOG_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SEC_FILINGS_SOURCE.FILINGS` (9 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778622073773.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1779064674157.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778541433635.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778622819068.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.AMAZON_REVIEWS_TEST.AMAZON_REVIEWS_TEST_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778540273936.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778854475570.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778891460242.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SEC_FILINGS.SEC_FILINGS_LOCK` (2 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.REVENUE_INTELLIGENCE_1778852205480.REVENUE_INTELLIGENCE` (4 cols, snowflake)
- `nxd-snowflake` :: `LOWERENVS_DB.SEC_OPENFIGI.SEC_OPENFIGI_LOCK` (2 cols, snowflake)

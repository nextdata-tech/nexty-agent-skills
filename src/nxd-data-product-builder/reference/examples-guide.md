# Public Examples Guide

Use `https://github.com/nextdata-tech/nextdata-public-examples` as the reference repository for draft product structure and idioms.

## How to Use Examples

Do not embed the whole examples repo in the skill. Clone or browse it on demand:

```bash
git clone https://github.com/nextdata-tech/nextdata-public-examples.git .context/dp-build/<timestamp>/nextdata-public-examples
```

Use `data_products/feature_matrix_table.md` to pick the closest example by infrastructure and capability.

## Example Selection

- ADLS JSON or Parquet source-aligned products: inspect `company_dividends`, `income_statements`, `credit_card_tx`, `stock_history`, or `public_disclosures`.
- Snowflake plus Databricks: inspect `loans_products`.
- ADLS to Snowflake plus MCP exposure: inspect `product_competitiveness`.
- S3 or CSV patterns: inspect `market_fraud_density` and `customer_purchases`.
- Databricks/Spark batch: inspect `taxi-trip-metrics`, `financial_statements`, or `competitor_growth_analysis`.
- MCP serving products: inspect `example_mcp`, `financial_statements`, or `product_competitiveness`.
- Document/context style products: inspect `public_disclosures` and any examples with document parsing.

## Drafting Rules

- Match file layout and imports to the closest current example, then adapt names, domains, infra profiles, and services.
- Keep draft products local under `.context/dp-build/<timestamp>/draft-products/`.
- Do not launch. Validation is local only.
- Preserve source shape for source-aligned products.
- Add explicit TODOs where examples assume an infra service, credential, schema, or contract that has not been confirmed in the user's environment.

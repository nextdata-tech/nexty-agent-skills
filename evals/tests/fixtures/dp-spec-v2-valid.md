---
dp_spec_version: 2
name: monthly_revenue
workflow: monthly-revenue
status: proposed
---

## Intent

Provide an auditable monthly revenue relation for finance review.

## Questions

### Question `monthly_revenue_by_customer`

What was monthly revenue for each customer?

## Scope

Includes paid orders only and excludes refunds until a separately declared model adds them.

## Inputs

### Input `orders_csv`
- Type: `csv`
- Location: `data/orders.csv`
- Description: Order rows supplied by finance.

## Models

### Model `orders`
- Kind: `base`
- Input: `orders_csv`
- Description: Pristine order relation.
- Grain: one row per order
- Key: `order_id`
- Fields: `order_id, customer_id, month, amount_usd`

### Model `monthly_customer_revenue`
- Kind: `derived`
- Description: Monthly revenue per customer.
- Grain: one row per customer and month
- Key: `customer_id, month`
- Fields: `customer_id, month, revenue`
- Produced by: `aggregate_monthly_revenue`

## Transform

### Step `aggregate_monthly_revenue`
- Operation: `aggregate`
- Inputs: `orders`
- Output: `monthly_customer_revenue`
- Group by: `orders.customer_id, orders.month`
- Measures: `revenue=sum(orders.amount_usd)`
- Null handling: `ignore`

## Outputs

### Output `monthly_revenue_port`
- Model: `monthly_customer_revenue`
- Questions: `monthly_revenue_by_customer`
- Projection: `customer_id, month, revenue`
- Order by: `month desc, customer_id asc`
- Delivery refs: `finance_semantic_port`

## Delivery

### Delivery `finance_semantic_port`
- Kind: `semantic_port`
- Target: `finance/monthly-revenue`
- Description: Governed finance semantic port.

## Decisions

### Decision `aggregate_definition`
- Target: `model:monthly_customer_revenue`
- Status: `proposed`
- Provenance: `agent_authored`
- Ruling: Revenue is the sum of order amount_usd grouped by customer and month.

## Open Questions

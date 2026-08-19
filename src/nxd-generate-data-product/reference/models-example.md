# `models.py` and `spec.py` worked examples

## Contents

- [`models.py`](#modelspy)
- [`spec.py`](#specpy)

## `models.py`

Matches the proven closure referenced by `SKILL.md` Step 2 — a full
`models.py` showing base models with placed roles plus one semantic view with
a metric. Use it as the concrete shape to match; do not deviate from the
`primary_key()` / `dimension(...)` / `join(...)` / `metric_field(metric(...))`
DSL calls shown here.

```python
"""Base models and query-time metrics for the desktop DP."""

from nxd.spec import Agg, semantic_model, semantic_view
from nxd.spec.data_types import number, string
from nxd.spec import dimension, field, join, metric, metric_field, primary_key

customers = (
    semantic_model("customers")
    .description("One row per customer account.")
    .schema(
        {
            # Type IDs from observed values, not habit: numeric-looking is not
            # numeric, and these keys are "C0417"-style strings.
            # primary_key() AND dimension(): a key with only the key role is
            # not groupable, so `describe_models` offers no way to ask WHICH
            # customer a row belongs to — every answer comes back as a count
            # with no identity. Roles compose; keys nearly always need both.
            "customer_id": field(
                string(),
                primary_key(),
                dimension(
                    name="customer_id",
                    description="Account key, e.g. C0417. Group by this to name a customer.",
                ),
            ),
            "country_id": field(
                string(),
                dimension(
                    name="customer_country",
                    # The description goes INSIDE dimension(). A description=
                    # on the enclosing field() never reaches describe_models.
                    description="ISO-3166 alpha-2 country of the billing address.",
                ),
            ),
            # No question named this column, and it is annotated anyway: the
            # questions decide the ROLE, not whether to annotate. Bare-typing
            # it would drop it from describe_models entirely.
            "country": field(
                string(),
                dimension(
                    name="customer_country_name",
                    description=(
                        "Country display name. Duplicates country_id — prefer "
                        "customer_country for grouping."
                    ),
                ),
            ),
            "email": field(
                string(),
                dimension(
                    name="customer_email",
                    description="Primary contact email.",
                    # Flagged from the DATA — the samples are addresses — not
                    # because a question asked for it.
                    pii=True,
                ),
            ),
        }
    )
)

orders = (
    semantic_model("orders")
    .description("One row per placed order.")
    .schema(
        {
            # order_id is number() here because its observed values are numeric —
            # the two ID shapes sit side by side deliberately.
            "order_id": field(number(), primary_key()),
            "customer_id": field(
                # Matches the customers.customer_id type; join endpoints must agree.
                string(),
                # join() has no description parameter — a join is not a concept
                # an agent selects.
                join(to="customers", to_column="customer_id"),
            ),
            # Bare is correct HERE and only here: a declared metric aggregates
            # this column, so its meaning travels on total_order_amount. A
            # numeric NO metric names would take a number dimension instead.
            "amount": number(),
        }
    )
)

order_metrics = semantic_view("order_metrics", orders).schema(
    {
        "total_order_amount": metric_field(
            number(),
            metric(
                Agg.SUM,
                of=orders.field("amount"),
                name="total_order_amount",
                description=(
                    "Gross order amount across ALL statuses. The role grammar "
                    "has no filtered metrics, so this is unconditional — "
                    "consumers filter at query time."
                ),
            ),
        ),
    }
)
```

## `spec.py`

The paired `spec.py` for SKILL.md Step 4 — the same closure, promising base and
derived models alike on the `duckdb` port and registering the metric view. The
contract facts that must survive any edit to this shape are listed in Step 4;
this is the shape they produce.

```python
"""A desktop data product authored entirely in Python. The supervisor compiles
this to the kernel definition YAML at create time."""

from nxd.spec import data_product, data_product_output, script, storage

from models import customers, orders, monthly_spend, order_metrics

_csv = "/infra-profile/desktop-local#/services/csv-source"
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"

_output = (
    data_product_output()
    .promise(customers)
    .promise(orders)
    .promise(monthly_spend)      # derived — promised identically to a base model
    .model(order_metrics)
    .port("duckdb", storage(_duckdb))
)

spec = (
    data_product(
        name="<dp-name>",
        domain="desktop.local",
        version="0.0.1",
        infra_profile="desktop-local",
    )
    .transform(script("transform/main.py").compute(_compute).secrets([_csv]))
    .output(_output)
)
```

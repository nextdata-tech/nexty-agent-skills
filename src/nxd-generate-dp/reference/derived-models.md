# Authoring derived models and their asserts

Worked code for Step 3a / Step 3b of nxd-generate-dp. The mandatory contract
clauses live in SKILL.md; this file is the shape they produce.

## Contents

- [The source-checkout shim](#the-source-checkout-shim)
- [`models.py`: base and derived side by side](#modelspy-base-and-derived-side-by-side)
- [Naming the ruling on the dimension it created](#naming-the-ruling-on-the-dimension-it-created)
- [The resource template](#the-resource-template)
- [Reading the sources yourself](#reading-the-sources-yourself)
- [Flat dicts, and why](#flat-dicts-and-why)
- [The assert template](#the-assert-template)
- [Choosing the invariant](#choosing-the-invariant)
- [Chained derivations stay in memory](#chained-derivations-stay-in-memory)
- [Worked example: enrichment via a reference-data join](#worked-example-enrichment-via-a-reference-data-join)
- [A complete ingest with both kinds of model](#a-complete-ingest-with-both-kinds-of-model)

## The source-checkout shim

The Step-3 transform template opens with this shim. Copy it verbatim, directly
below the stdlib imports and **above** `import dlt`.

The shim exists for a developer running against a source checkout whose bindings
are built locally. **Installed wheels always win.** The supervisor exports
`NXD_DESKTOP_REPO_ROOT` on every run — including runs whose interpreter has
perfectly good wheels installed — so the presence of that variable says nothing
about whether the checkout should be used.

```python
import importlib.util
import sys


def _configure_nxd_imports() -> None:
    """Prefer installed nxd wheels; fall back to a source checkout only if it
    carries COMPILED bindings.

    Two guards, both load-bearing:

    * If ``nxd.core`` / ``nxd.drivers`` / ``nxd.data_product`` already resolve,
      the wheels are installed and this is a no-op. Prepending the checkout here
      would SHADOW a healthy runtime with a source tree.
    * A checkout is only usable when its compiled extension modules are present.
      A tree with just ``_bindings.pyi`` (the type stub) is not a runtime: the
      child dies with ``ModuleNotFoundError: No module named
      'nxd.core._bindings'`` the instant it imports nxd.
    """
    try:
        installed = all(
            importlib.util.find_spec(module) is not None
            for module in ("nxd.core", "nxd.drivers", "nxd.data_product")
        )
    except (ImportError, ValueError):
        installed = False
    if installed:
        return

    repo_root = os.environ.get("NXD_DESKTOP_REPO_ROOT")
    if not repo_root:
        return
    root = Path(repo_root)
    sources = (
        root / "components/nxd_py/data_product",
        root / "components/nxd_py/core",
        root / "components/nxd_py/drivers",
    )
    # Compiled bindings must exist for BOTH core and drivers, or the fallback
    # produces a tree that imports halfway and then fails. A ".pyi" stub next to
    # a missing ".so" is exactly the trap this guards.
    compiled = (
        root / "components/nxd_py/core/nxd/core",
        root / "components/nxd_py/drivers/nxd/drivers",
    )
    if not all(any(directory.glob("_bindings*.so")) for directory in compiled):
        return
    for source in reversed(sources):
        sys.path.insert(0, str(source))


_configure_nxd_imports()
```

`reversed(...)` matters: each `insert(0, ...)` pushes onto the front of
`sys.path`, so iterating in reverse leaves the three source roots in the listed
order once the loop finishes.

Never replace this with a bare `if os.environ.get("NXD_DESKTOP_REPO_ROOT"):`
prepend. That shape shipped once and broke every generated closure on a machine
whose desktop runtime pointed at a checkout without built bindings: the
transform crashed instantly, and — because the kernel host only waits for a
staging file that never appears — it surfaced as an opaque ~170s
"did not materialize staging output" timeout rather than an import error.

## `models.py`: base and derived side by side

Nothing in `models.py` marks a model as derived — the DSL, the role vocabulary
and the `.schema({...})` shape are identical. The difference is only in where
the schema keys come from (yielded dict keys, not CSV headers) and that the
primary key may be the grain-derived composite.

```python
"""Base models, a derived model, and query-time metrics for the desktop DP."""

from nxd.spec import Agg, semantic_model, semantic_view
from nxd.spec.data_types import number, string
from nxd.spec import dimension, field, join, metric, metric_field, primary_key

# BASE — landed 1:1 from data/invoices/*.csv. Key is an existing source column.
invoices = semantic_model("invoices").schema(
    {
        # number() because every observed invoice_id is numeric. Check the
        # source first: a "T1257"-style ID is string(), not number().
        "invoice_id": field(number(), primary_key()),
        "customer": field(string(), dimension(name="customer")),
        "start_month": field(string(), dimension(name="start_month")),
        "term_months": number(),
        "amount": number(),
    }
)

# DERIVED — row-EXPANDING, one row per (invoice, month) of its term. No
# data/amortization_schedule/ directory backs it. Its key is the synthetic
# composite the invoice x month grain implies, which is exactly why it is a
# derived model and not a view.
amortization_schedule = semantic_model("amortization_schedule").schema(
    {
        "schedule_id": field(string(), primary_key()),
        "invoice_id": field(
            number(),
            join(to="invoices", to_column="invoice_id"),
        ),
        "customer": field(string(), dimension(name="schedule_customer")),
        "period_month": field(string(), dimension(name="period_month")),
        "period_index": number(),
        "recognized_amount": number(),
    }
)

amortization_metrics = semantic_view(
    "amortization_metrics", amortization_schedule
).schema(
    {
        "recognized_revenue": metric_field(
            number(),
            metric(
                Agg.SUM,
                of=amortization_schedule.field("recognized_amount"),
                name="recognized_revenue",
            ),
        ),
    }
)
```

In `spec.py`, both are promised the same way — that is what puts the derived
model in `model_tables`:

```python
_output = (
    data_product_output()
    .promise(invoices)
    .promise(amortization_schedule)     # derived, promised identically
    .model(amortization_metrics)
    .port("duckdb", storage(_duckdb))
)
```

A derived model that keeps its source key (a dedupe) declares that source
column as `primary_key()` — only a regrain introduces a synthetic composite.

## Naming the ruling on the dimension it created

A derived column that exists because of a **ruling** — a classification, a
reclassification, an exclusion — must say so in `description=`. This is not
documentation polish. `describe_models` is the entire surface a later consumer
sees: a `category` dimension with no description looks like it came from the
source, and the ruling behind it becomes invisible exactly when someone is
about to trust a number built on it.

```python
# DERIVED — classification. `category` exists ONLY because of the confirmed
# merchant_categories ruling; the source carries no such column.
classified_spend = semantic_model("classified_spend").schema(
    {
        "transaction_id": field(number(), primary_key()),
        "merchant": field(string(), dimension(name="merchant")),
        "category": field(
            string(),
            dimension(
                name="category",
                description=(
                    "COGS/opex classification from the confirmed "
                    "merchant_categories mapping. Merchants the mapping does "
                    "not cover land in 'needs_review', not in a real category."
                ),
            ),
        ),
        "amount": number(),
    }
)
```

Two rules the example encodes:

- **State the basis, not just the meaning.** "Category of the transaction" is
  useless; naming the mapping tells the reader the number is only as good as
  that ruling — and where to go to correct it.
- **Name the review bucket in the description.** A consumer who groups by
  `category` and sees `needs_review` must be able to learn what it means from
  the catalog alone. The bucket is the honest edge of the classification;
  hiding it in transform code is how an unmapped merchant silently becomes a
  rounding error in someone's total.

The same applies to a dimension whose values were **narrowed** by a ruling
(rows reclassified or excluded upstream): say what was excluded and why, since
the default read of the measure now silently reflects that decision.

## The resource template

```python
@dlt.resource(name=duckdb.model_tables["<derived_model>"])
def <derived_model>_resource() -> Iterator[dict[str, Any]]:
    yield from derived_rows          # flat scalar dicts only


resources.append(<derived_model>_resource())
```

The rows are computed **before** the resource is defined, so the assert
(below) can run over the complete set before dlt pulls the first row. A
generator that computes lazily while dlt consumes it cannot be asserted as a
whole, and a violation would surface only after partial rows were written.

## Reading the sources yourself

dlt's `read_csv` transformer streams straight to the destination; it cannot
hand rows back to Python. Derived logic therefore needs its own read of the
base export. Use the standard library — no new dependency:

```python
import csv


def _read_source_rows(source_root: Path, model: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted((source_root / model).glob("*.csv")):
        with path.open(newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows
```

`sorted(...)` is not cosmetic: glob order is filesystem-dependent, and an
unsorted read makes a derivation whose output depends on file arrival order.

`csv.DictReader` yields strings for every column. Convert **measures, not
identifiers**: `Decimal(row["amount"])` (`from decimal import Decimal`) — while
an ID stays the string `csv.DictReader` gave you unless you have checked that
every observed value is numeric. Look at the actual source values before typing
or casting an ID column: `int()` on a `"T1257"`-style key raises
`ValueError: invalid literal for int() with base 10: 'T1257'`. Use `Decimal` for
money so cent-level reconciliation asserts hold. Cast to `float` only in the final dict, since dlt
has no `Decimal` mapping here; do the reconciliation in `Decimal` **before**
that cast.

## Flat dicts, and why

The pinned desktop runtime venv has **no pyarrow**. dlt requires pyarrow to
route a pandas or polars frame to a destination, so yielding a DataFrame raises
at run time. If pandas is convenient for the computation, convert at the
boundary:

```python
yield from frame.to_dict(orient="records")
```

Every value must be a scalar. A nested dict or list makes dlt emit a child
table named `<parent>__<field>`, which appears in
`pipeline.default_schema.data_table_names()` and fails the read-back assert —
correctly, because the promised model's shape is then not what landed.

## The assert template

```python
def _assert_<derived_model>_reconciles(
    source: list[dict[str, str]], derived: list[dict[str, Any]]
) -> None:
    """<one sentence naming the invariant, not the implementation>."""
    expected_rows = sum(int(row["<term_column>"]) for row in source)
    if len(derived) != expected_rows:
        raise RuntimeError(
            f"<derived_model> produced {len(derived)} rows, expected "
            f"{expected_rows} (one per <grain unit>)"
        )
    keys = [row["<key_column>"] for row in derived]
    if len(set(keys)) != len(keys):
        raise RuntimeError("<derived_model> has duplicate <key_column> keys")
```

Raise `RuntimeError` carrying the actual-vs-expected numbers. The failure is
read from the supervisor's run log, so the message is the entire diagnostic —
`assert` with no message, or a bare boolean, wastes the one signal available.

## Choosing the invariant

An assert earns its place by being **falsifiable if the derivation is wrong**.
Restating the transform's own arithmetic (`sum(outputs) == sum(outputs)`)
proves nothing and gives false confidence.

**This is not a menu.** The table below is a floor, not a set of options to
pick the most convenient one from. Picking the invariant that is easiest to
satisfy is how a wrong derivation ships green.

### Tier 1 — mandatory for EVERY derived model, no exceptions

1. **Declared-key uniqueness.** `len(set(keys)) == len(keys)` over the
   complete derived set. This is what upgrades the derived-model key gate from
   a claim to a proof: the grain-derived composite is *asserted* unique, never
   assumed.
2. **Row count computed from the grain**, checked against source rows you
   **read independently** from the base CSVs — not against a count the
   derivation itself produced. State the grain in one sentence, turn it into an
   arithmetic expectation over the source rows, and compare.

### Tier 2 — additionally mandatory when the model carries a MEASURE column

If the derived model has any column a metric will aggregate — an amount, a
quantity, a duration, anything summable — you MUST also reconcile the measure:

- **The signed measure total of the derived rows must equal the signed total
  read independently from the base CSVs**, with **every intentional divergence
  itemized as its own named term**. Not "approximately", not "within
  tolerance" — an equation whose terms you can name:

  ```
  derived_total == source_total
                   - refund_pairs_total      # 18 pairs, each an exact negative
                   - transfer_rows_total     # internal transfers, not expenses
  ```

- **Signed, not absolute.** Sum the values with their sign. A refund that is
  the exact negative of a charge nets to zero only if you never took
  `abs()`; an unsigned total hides exactly the error this catches.
- **Use `Decimal`, not `float`.** Cent-level reconciliation does not survive
  binary floating point.
- **Reconcile per source currency, BEFORE any FX conversion.** Converting
  first folds the rate into the comparison and makes a wrong rate
  unfalsifiable. Reconcile each currency against its own source total, then
  convert.

An unreconciled measure is the failure mode this rule exists for: a
classification-totality assert can pass — every row bucketed, counts summing
perfectly — while every monetary answer is silently overstated, because
totality says nothing about magnitude.

### An itemized exclusion means you have a REMOVAL

If the reconciliation needs a `- something_total` term, the derivation is
**removing rows or value**, not merely enriching. Say so out loud:
**reclassify it as a removal** and apply the removal invariants below **in
addition** to the ones you already have. A derivation described as an
"enrichment" whose totals only balance after subtracting some rows is a removal
wearing the wrong label — and it will carry an enrichment's asserts, which
cannot test the thing it actually does.

### Per-shape invariants (on top of Tier 1 and Tier 2)

| Derivation shape | Invariant that actually tests it |
|---|---|
| **Row-preserving enrichment** (adds columns, same rows) | output count **==** independently-read source count, AND the signed measure total is preserved exactly — no row lost, no value changed |
| **Expansion** (one row → N) | row count equals the summed term; each parent's parts sum back to the parent's exact total |
| **Removal** (dedupe, pair cancel) | the dropped count matches the removal rule's arity (pairs drop an even count); a net-zero removal leaves the source total unchanged; no row the rule should have removed survives |
| **Collapse** (regrain) | every source row is accounted for in exactly one output group; the measure total is preserved across the regrain |
| **Classification** | every source row lands in exactly one bucket, `needs_review` included; the per-bucket counts sum to the source count. **Never sufficient on its own** — pair it with the Tier-2 measure reconciliation |

## Chained derivations stay in memory

A derivation chain — enrich, then collapse — shares the **in-memory Python row
lists**: the collapse consumes the enrichment's list directly, as a plain
`list[dict]` argument. **Never read a derived model back from the output port
mid-run.** The rows are not queryable until `pipeline.run(...)` completes and
the supervisor promotes the artifact, so a mid-run read either fails or reads a
stale prior run's table.

## Worked example: enrichment via a reference-data join

The most common real shape: the same entities, with columns added from a
landed reference model. Every source row survives; nothing is aggregated.

```python
def _classify_spend(
    txns: list[dict[str, str]], rulings: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """One output row per source transaction, plus category / month."""
    by_merchant = {r["merchant"]: r["category"] for r in rulings}
    return [
        {
            # ID passes through as the source string — no int() cast. These
            # keys are "T1257"-style; casting would raise.
            "txn_id": t["txn_id"],
            "merchant": t["merchant"],
            # Uncovered merchants get an explicit bucket, never a silent drop.
            "category": by_merchant.get(t["merchant"], "needs_review"),
            "month": t["txn_date"][:7],           # derived column, not DATE_TRUNC
            "currency": t["currency"],
            "amount": float(Decimal(t["amount"])),  # signed; refunds stay negative
        }
        for t in txns
    ]


def _assert_classified_spend(
    txns: list[dict[str, str]], derived: list[dict[str, Any]]
) -> None:
    """Row-preserving enrichment: same rows, same signed money, one bucket each."""
    if len(derived) != len(txns):                       # Tier 1: grain row count
        raise RuntimeError(
            f"classified_spend produced {len(derived)} rows, expected "
            f"{len(txns)} (enrichment is row-preserving)"
        )
    keys = [row["txn_id"] for row in derived]           # Tier 1: key uniqueness
    if len(set(keys)) != len(keys):
        raise RuntimeError("classified_spend has duplicate txn_id keys")

    # Tier 2: signed measure reconciliation, per currency, pre-FX, in Decimal.
    for currency in {t["currency"] for t in txns}:
        source_total = sum(
            Decimal(t["amount"]) for t in txns if t["currency"] == currency
        )
        derived_total = sum(
            Decimal(str(r["amount"])) for r in derived if r["currency"] == currency
        )
        if derived_total != source_total:               # no exclusion terms:
            raise RuntimeError(                          # nothing is removed here
                f"classified_spend {currency} total {derived_total} != "
                f"source {source_total}"
            )

    unbucketed = [r for r in derived if not r["category"]]
    if unbucketed:
        raise RuntimeError(f"{len(unbucketed)} rows landed in no category bucket")
```

Note what the reconciliation says here: **zero exclusion terms**, because this
derivation removes nothing. The moment a real requirement adds one — "net out
refund pairs" — the equation grows a named `- refund_pairs_total` term, and
per the rule above the model is reclassified as a **removal** and gets the
removal invariants too.

## A complete ingest with both kinds of model

Take the Step-3 template in SKILL.md and insert the derived block between the
base-reader loop and `pipeline.run(...)` — that is the whole change:

```python
    # Base models: one dlt CSV reader per data/<model>/ directory.
    for model in BASE_MODELS:
        reader = filesystem(
            bucket_url=str(source_root / model), file_glob="*.csv"
        ) | read_csv()
        resources.append(reader.with_name(duckdb.model_tables[model]))

    # Derived models: computed here, yielded into the SAME run.
    invoice_rows = _read_source_rows(source_root, "invoices")
    schedule = _amortize_invoices(invoice_rows)       # pure, deterministic
    _assert_schedule_reconciles(invoice_rows, schedule)

    @dlt.resource(name=duckdb.model_tables["amortization_schedule"])
    def amortization_schedule_resource() -> Iterator[dict[str, Any]]:
        yield from schedule

    resources.append(amortization_schedule_resource())

    pipeline.run(resources, write_disposition="replace")
```

One pipeline, one `pipeline.run(...)`, one `write_disposition="replace"`. Base
readers and derived resources are peers in the same list — that is what keeps
every write on the port path and the DDL ban intact. The unchanged read-back
assert then covers base and derived tables alike, and catches a stray
`parent__field` child table from a nested value.

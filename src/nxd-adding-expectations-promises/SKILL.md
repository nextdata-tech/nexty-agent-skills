---
name: nxd-adding-expectations-promises
description: Add, repair, or explain Nextdata OS input expectations and output promises. Use when adding data-quality contracts, schema checks, custom verifier scripts, promise files, expectation files, or resolving input-side versus output-port quality guarantees.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.27.0
---

# NXD Expectations and Promises

Use expectations to protect inputs before transform execution, and promises to
verify outputs after writes. Keep inferred schema constraints as ordinary model
checks. A named custom contract represents only an explicit user-stated
guarantee: must/must-not, cross-field, aggregate, reconciliation, freshness, or
accepted-set rule.

## Platform/API setup and validation

Use this section **only for the connected platform/API branch**. Pocket/Desktop
uses the closure self-check and focused fixture in the workflow below; it does
not require a mesh session configuration.

- Confirm `nxd-setup` selected the mesh and produced `<session_config>`.
- Resolve `<app_url>` from the active mesh registry and consult:
  - `<app_url>/docs/#/tutorials/guides/05-expectations`
  - `<app_url>/docs/#/tutorials/guides/03-promises`
  - `<app_url>/docs/#/tutorials/cli/data_quality`
  - `<app_url>/docs/#/basics/transactional_guarantees`

## Decision rule

- Input quality before transform: attach an expectation to the input.
- Output guarantee after a write: attach a promise to the output port.
- A type/key/nullability/enum inferred from profiling: keep it in `models.py`
  and ordinary model checks, even if it resembles a user guarantee.
- An explicit guarantee overlapping inferred schema: keep both; name and
  execute the explicit contract rather than silently collapsing it into schema.
- Select the runtime before choosing the verifier API: Pocket/Desktop uses the
  script contract below; a connected platform/API runtime keeps the normal
  `code(...)` verifier path.
- A computational policy that needs a contract is activated afterward through
  `nxd-adding-policy` or `nxd-policies`; a missing contract never authorizes
  disabling that policy.

Record each custom contract's name, wording, model, phase, source of authority,
executable rule, and diagnostic in `CONTEXT.md`. Ask for a missing tolerance,
population, time basis, or accepted values whenever it changes pass/fail.

## Platform/API `code(...)` contract shape

For a connected platform runtime, use a custom Python function when the
context supports an API, database, or output inspection. This is not the
Pocket CSV limitation: do not tell a platform/API user to export a CSV merely
because their contract is custom.

```python
# spec.py — platform/API input
from contracts import jira_input_format

.input(
    "jira-api",
    source_aligned_input().source(JIRA_API_URL).model(jira_issue).expectation(
        custom("jira-input-format").description("User-stated Jira input format.")
        .model(jira_issue).verify(code(jira_input_format.verify))
    ),
)
```

```python
# contracts/jira_input_format.py
from nxd.data_product.context import API, Model, VerifyResult, VerifyResultEnum

def verify(jira_api: API, models: dict[str, Model]) -> VerifyResult:
    failures = []  # inspect the supplied context; never echo its credentials
    if failures:
        return VerifyResult(VerifyResultEnum.FAILED, {"failures": failures})
    return VerifyResult(VerifyResultEnum.PASS, {"checked": True})
```

Attach a platform output check to its output port and keep its ordinary model
declaration/promise according to that runtime's API:

```python
.output(
    data_product_output()
    .port("pgvector", storage(PGVECTOR_URL).config(pg_vector_config()))
    .promise(custom("row-count").model(jira_embeddings).verify(code(row_count.verify)))
    .model(jira_embeddings)
)
```

Use `VerifyResultEnum.FAILED` for a broken blocking guarantee; `WARNING` is
only for an explicitly non-blocking policy. Keep diagnostics redacted and
side-effect-free. Confirm the installed platform context type and API from the
active documentation before writing a verifier.

## Pocket/Desktop script contract shape

Pocket supports executable custom **input** expectations only for a declared
CSV source-aligned input. Every Pocket source-aligned input — custom or not —
uses `.source(_csv)`, with `_csv` bound exactly to
`/infra-profile/desktop-local#/services/csv-source`; that service uses
`nxd:local/file/storage:0.1.0`. Labeled CSV services are transform-only on this
runtime. Multiple source-aligned inputs may share the same `_csv` and one
`csv-source-path`.

The input verifier receives `LocalFileInput` **before** DLT runs and reads only
its declared relative `model_paths`. DLT then loads the export during the
transform through `.secrets([_csv])`; the verifier does not receive a DLT
loading context. For a true DB/API input, obtain a CSV export or explain that
custom input verification is unsupported on this runtime path; never ship a
decorative script. An output promise is possible only where its real output
storage and contract context support it.

Declare the local-file context's exact relative paths with
`.config({"model_paths": {"model": "model/model.csv"}})` on the
source-aligned input. Do not make a verifier scan the export root or embed a
host path.

Keep ordinary `.promise(model)` schema checks. A custom output promise
supplements, never replaces, it. `compute()` belongs to the `script(...)`
verifier spec, inside `verify(...)`; a chain ending
`custom(...).verify(...).compute(...)` is invalid. The transform uses
`simple_sensor(startup=False, when="any")` so the Desktop host owns one run.

```python
# spec.py
_csv = "/infra-profile/desktop-local#/services/csv-source"
_compute = "/infra-profile/desktop-local#/services/python-compute"

.transform(
    script("transform/main.py")
    .compute(_compute)
    .secrets([_csv])
    .when(simple_sensor(startup=False, when="any"))
)
.input(
    "orders-source",
    source_aligned_input()
    .source(_csv)
    .config({"model_paths": {"orders": "orders/orders.csv"}})
    .expectation(
        custom("accepted-currency")
        .description("User-stated: currency must be EUR or USD.")
        .model(orders)
        .verify(script("contracts/expectations/accepted-currency.py").compute(_compute))
    ),
)
.output(
    data_product_output()
    .promise(orders)  # ordinary schema promise stays
    .promise(
        custom("order-total-reconciles")
        .description("User-stated: output line totals reconcile to order totals.")
        .model(orders)
        .verify(script("contracts/promises/order-total-reconciles.py").compute(_compute))
    )
    .port("duckdb", storage(_duckdb))
)
```

```python
# contracts/expectations/accepted-currency.py
import csv
from nxd import data_product
from nxd.core.context import LocalFileInput, VerifyResult, VerifyResultEnum


@data_product.on_verify()
def verify(orders_source: LocalFileInput) -> VerifyResult:
    bad = []
    with open(orders_source.path_for("orders"), newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            if row["currency"] not in {"EUR", "USD"}:
                bad.append({"row": row_number, "currency": row["currency"]})
    if bad:
        return VerifyResult(VerifyResultEnum.FAILED, {"contract": "accepted-currency", "violations": bad[:20]})
    return VerifyResult(VerifyResultEnum.PASS, {"contract": "accepted-currency"})


if __name__ == "__main__":
    data_product.verify()
```

```python
# contracts/promises/order-total-reconciles.py
import duckdb
from nxd import data_product
from nxd.core.context import DuckDbOutput, VerifyResult, VerifyResultEnum


@data_product.on_verify()
def verify(duckdb_output: DuckDbOutput) -> VerifyResult:
    table = duckdb_output.full_table_name("orders")
    with duckdb.connect(duckdb_output.path, read_only=True) as conn:
        mismatches = conn.execute(
            f"""SELECT order_id FROM {table}
                GROUP BY order_id
                HAVING COUNT(DISTINCT order_total) != 1
                   OR MIN(order_total) != SUM(line_total)
                LIMIT 20"""
        ).fetchall()
    if mismatches:
        return VerifyResult(VerifyResultEnum.FAILED, {"contract": "order-total-reconciles", "order_ids": [r[0] for r in mismatches]})
    return VerifyResult(VerifyResultEnum.PASS, {"contract": "order-total-reconciles"})


if __name__ == "__main__":
    data_product.verify()
```

## Workflow

1. Inspect `spec.py`, `models.py`, `CONTEXT.md`, and existing `contracts/`.
2. Identify input-side, output-side, or both; distinguish inferred from stated.
3. For Pocket, add exactly one script under `contracts/expectations/<name>.py`
   or `contracts/promises/<name>.py` for each wired custom contract. For the
   platform/API branch, add the `code(...)` module/function required by its
   runtime instead.
4. Attach CSV input expectations before the transform and DuckDB output
   promises after it; retain `.promise(model)`.
5. Keep contract code deterministic, side-effect-free, secret-free, and scoped
   to its supplied context. Return only redacted diagnostics/counts.
6. For Pocket, run the closure self-check plus a focused contract fixture when
   available. For the connected platform/API branch, also run:

```bash
nxd --config <session_config> whoami
nxd validate --config <session_config> <data_product_directory> --debug
```

On the platform/API branch, `nxd validate` imports and validates the spec but
does not execute a custom verifier against live data. The verifier runs in its
expectation or promise phase. If a computational policy needs this contract,
hand off to `nxd-adding-policy` or `nxd-policies` after wiring it.

## Guardrails

- Do not attach output promises to input declarations or input expectations to
  output ports.
- Do not rename an inferred schema constraint as a custom guarantee, or drop an
  explicit guarantee because a type/key partly overlaps it.
- Do not disable a policy because a contract is missing; add the required
  contract or explain the missing artifact.
- Do not leave decorative `contracts/*.py` files, duplicate names,
  absolute/escaping script paths, or secrets in a verifier.
- A `script(...)` executes its complete file: one script registers exactly one
  `@data_product.on_verify()` function and calls `data_product.verify()` under
  the `__main__` guard. Do not share one phase-wide script across named
  contracts, because the contract name does not select a function inside it.
- A structural check proves the closure is parseable and wired; it does not
  prove a live contract execution succeeded.

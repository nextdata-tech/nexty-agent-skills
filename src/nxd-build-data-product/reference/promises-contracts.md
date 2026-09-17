# Promises and Contracts

Copy-paste reference for wiring output promises and input expectations into an NXD data product.

## Contents

- [Overview](#overview)
- [requirements.txt extras](#requirementstxt-extras)
- [Spec wiring — all three promises](#spec-wiring--all-three-promises)
- [nxd_spec.py additions](#nxd_specpy-additions)
- [Verify function signatures](#verify-function-signatures)
- [Contract file templates](#contract-file-templates)
- [Input expectations (pre-checks on source data)](#input-expectations-pre-checks-on-source-data)

---

## Overview

| Type | Tool | Attachment point | Contract file |
|------|------|-----------------|---------------|
| Great Expectations | `quality(gx, "path")` | Port-level: `storage(...).promise(quality(...))` | Python with `configure() -> list` |
| Soda | `quality(soda, "path")` | Port-level: `storage(...).promise(quality(...))` | YAML with `checks for TABLE_NAME:` |
| Custom | `custom("name").verify(code(fn))` | Output-level: `data_product_output().promise(custom(...))` | Python with `verify(...) -> VerifyResult` |

**Why two attachment points?** `quality(gx/soda, ...)` produces a `DataQualityVerificationSpec`
which only `OutputPortSpec.promise()` accepts. `custom(...)` produces a `CustomVerificationSpec`
which both `OutputPortSpec.promise()` and `DataProductOutputSpec.promise()` accept — attach it
at the output level so it is not tied to a single port.

**Model scoping:** `.model(model)` on a `quality(...)` promise scopes the check to that one
semantic model. Without it, the check runs against all canonical models defined at the output
level. Use `.model(model)` whenever the contract file targets a specific table.

---

## requirements.txt extras

Both extras are on `nxd_data_product`, not `nxd_core`:

```
nxd_data_product[gx]     # Great Expectations
nxd_data_product[soda]   # Soda
```

Two failure modes, both silent until runtime:
1. **Wrong package** — `nxd_core[gx]` installs without error but the right modules are never loaded.
2. **Missing extra** — plain `nxd_data_product` passes `nxd validate` and spec import; crashes only when the promise actually runs.

Add the extra at the same time you wire the promise — never rely on validate to catch it.

---

## Spec wiring — all three promises

```python
from contracts.accounts_row_count import verify as accounts_row_count_verify
from nxd.spec import code, custom, data_product_output, quality, snowflake_config, storage
from nxd.spec.validations import gx, soda

.output(
    data_product_output()
    .model(accounts)
    # Custom promise — output-level, scoped to a specific model
    .promise(
        custom("accounts-row-count")
        .description("Verify accounts table has at least one row after each load")
        .model(accounts)
        .verify(code(accounts_row_count_verify))
    )
    .port(
        "snowflake",
        storage("https://<app_url>/infra-profile/<profile>#/services/<snowflake-service>")
        .config(
            snowflake_config(schema="SCHEMA")
            .target_table("TABLE_NAME", accounts)
        )
        # GE promise — port-level, scoped to one model
        .promise(
            quality(gx, "contracts/accounts_gx.py")
            .name("AccountsGXCheck")
            .description("Great Expectations column checks on TABLE_NAME")
            .model(accounts)          # omit to run against all canonical output models
        )
        # Soda promise — port-level, scoped to one model
        .promise(
            quality(soda, "contracts/accounts_soda_checks.yml")
            .name("AccountsSodaCheck")
            .description("Soda quality checks on TABLE_NAME")
            .model(accounts)          # omit to run against all canonical output models
        ),
    )
)
```

---

## nxd_spec.py additions

Add to imports and `__all__`:

```python
from contracts.accounts_row_count import verify as accounts_row_count_verify
from nxd.spec import code, custom, quality
from nxd.spec.validations import gx, soda

__all__ = [
    ...,
    "accounts_row_count_verify",
    "code",
    "custom",
    "gx",
    "quality",
    "soda",
]
```

---

## Contract file templates

### Great Expectations — `contracts/<name>_gx.py`

```python
from great_expectations.expectations import (
    ExpectColumnValueLengthsToBeBetween,
    ExpectColumnValuesToNotBeNull,
)


def configure():
    return [
        ExpectColumnValuesToNotBeNull(column="COL_A"),
        ExpectColumnValuesToNotBeNull(column="COL_B"),
        ExpectColumnValueLengthsToBeBetween(column="COL_A", max_value=255),
    ]
```

The function name must be `configure`. It receives no arguments. Return a list of
`great_expectations.expectations.*` objects. The platform runs GX against the model's
output table and fails the promise if any expectation is not met.

Add `.model(model)` in the spec to scope this check to one model; omit it to run against
all canonical output models.

---

### Soda — `contracts/<name>_soda_checks.yml`

```yaml
checks for TABLE_NAME:          # must match the DB table name, not the model name
  - missing_count(COL_A) = 0:
      name: "COL_A is not null"
  - missing_count(COL_B) = 0:
      name: "COL_B is not null"
  - row_count > 0:
      name: "Table is not empty"
  - invalid_count(STATUS):
      valid values: [active, inactive]
      fail: when > 0
```

The `checks for` key must match the physical database table name (e.g., `SALESFORCE_ACCOUNTS`),
not the NXD model name (e.g., `accounts`). Reference the soda-core documentation for the full
check syntax.

Add `.model(model)` in the spec to scope this check to one model; omit it to run against
all canonical output models.

---

## Verify function signatures

Two rules decide whether a contract runs at all and whether it is worth running.
Neither is checked by `nxd validate`, which imports the bundle but never executes
a contract. A contract that breaks either one validates clean and fails, or lies,
at verification time.

### Parameters bind by name, after the service

Verify arguments bind by name, not position, the same rule that governs
`transform(...)`. The service context parameter must be named after the service
the contract is wired to:

```python
# spec.py
custom("POS_CHANNEL_VALIDATION")
    .script("contracts/pos_channel_validation.py")
    .service(service_name="adls", driver="nxd:adls:2.0.0")

# contracts/pos_channel_validation.py
def verify(adls: AzureDataLakeStorage, models: dict[str, Model]) -> VerifyResult:
    ...
```

`adls` is correct because the service is named `adls`. Generic names — `input`,
`ctx_in`, `storage`, `source`, `context` — match no declared service or port and
fail at runtime with an invalid-argument-name error. The type annotation does not
rescue a wrong name; annotations document the context, names bind it.

Hyphens in a service or port name normalise to underscores in the signature, just
as they do for the transform (`"s3-source"` → `s3_source`).

### `driver=` names the storage service, never the contract executor

`.service(service_name=..., driver=...)` declares which infra-profile service the
contract receives a context for, and `driver=` selects the context *class*. Pass
the driver the profile declares for that service:

```python
.service(service_name="adls", driver="nxd:adls:2.0.0")        # -> AzureDataLakeStorage
.service(service_name="adls", driver="nxd:kubernetes/contract:1.0.0")  # -> bare Context
```

`nxd:kubernetes/contract:1.0.0` is the **contract executor**, which the platform
selects on its own; the package excludes it from service resolution precisely
because "it is not an infra-profile service" (`nxd/spec/_spec.py`). Passing it
here resolves to a bare `Context`, exactly as a fabricated driver does, so every
`adls.model_paths`, `adls.container` and `adls.tenant_id` in the contract raises
at verification time. Confirm the mapping against the installed package when in
doubt:

```python
from nxd.spec._spec import storage_context_type_for_driver
storage_context_type_for_driver("nxd:adls:2.0.0")   # (AzureDataLakeStorage, AzureDataLakeStorage)
```

This one hides well. A contract that returns `PASS` without touching the context
never dereferences anything, so a wrong driver is invisible until the body starts
doing real work. Bundled examples that carry both faults look like working
precedent and are not.

### A verify that cannot fail is a defect

Every contract must read the data it is asserting over and be capable of returning
`VerifyResultEnum.FAILED`. A body that returns `PASS` unconditionally passes
review, passes validation, and passes at runtime while asserting nothing — worse
than no contract at all, because the mesh now advertises a guarantee nobody
checks.

```python
# WRONG — asserts nothing, can never fail
@data_product.on_verify()
def verify(adls: AzureDataLakeStorage) -> VerifyResult:
    return VerifyResult(VerifyResultEnum.PASS, {"result": "Looks good"})
```

A correct body reads the published data, evaluates the stated rule, and reports
the offending values and row counts on failure so the owner can act:

```python
observed = frame[CHANNEL_COLUMN].astype(str)
unexpected = sorted(set(observed) - set(ACCEPTED_CHANNELS))
if unexpected:
    return VerifyResult(
        VerifyResultEnum.FAILED,
        {
            "result": f"{int(observed.isin(unexpected).sum())} row(s) outside the accepted set.",
            "unexpected_values": unexpected[:20],
            "rows_checked": int(len(frame)),
        },
    )
```

`VerifyResultEnum` carries `PASS`, `WARNING` and `FAILED`. Reach for `WARNING`
when the data is usable but degraded; do not use it to soften a real violation.

**Some bundled public examples ship unconditional-`PASS` contracts.** They are
seeding fixtures, not a pattern to copy. When an example's contract body cannot
fail, write a real one rather than mirroring it.

---

### Custom verify — `contracts/<name>_verify.py` (Snowflake)

```python
import logging
from typing import Optional

import snowflake.connector as sf_connector   # module-level alias avoids name clash with param
from nxd.core.context import ContractContext, TriggerContext
from nxd.data_product.context import Model, Snowflake, VerifyResult, VerifyResultEnum

_logger = logging.getLogger("contracts.<name>_verify")


def verify(
    snowflake: Snowflake,
    ctx: ContractContext,
    models: dict[str, Model],
    triggered_by: Optional[TriggerContext],
) -> VerifyResult:
    table = snowflake.model_tables["model_name"]   # physical table name
    # Alternative: table = snowflake.full_table_name("model_name")

    conn = sf_connector.connect(
        user=snowflake.user,
        password=snowflake.password,
        account=snowflake.account,
        warehouse=snowflake.warehouse,
        role=snowflake.role,
        database=snowflake.database,
        schema=snowflake.schema,
        ocsp_fail_open=True,
    )
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        row_count = cursor.fetchone()[0]
    finally:
        cursor.close()
        conn.close()

    if row_count == 0:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {"error": "table is empty", "row_count": row_count},
        )

    _logger.info(f"row count: {row_count}")
    return VerifyResult(VerifyResultEnum.PASS, {"row_count": row_count, "table": table})
```

**Snowflake context API:**
- `snowflake.model_tables["model_name"]` — dict keyed by model name, value is the physical table name string
- `snowflake.full_table_name("model_name")` — equivalent method form
- No `.model_paths`, no `.connection` — always build the connector from params
- Connection params: `.user`, `.password`, `.account`, `.warehouse`, `.role`, `.database`, `.schema`

**Import name clash:** The verify function's first parameter is conventionally named `snowflake`.
If you also need `from snowflake import connector` in the same file, the local `import snowflake`
statement will resolve to the parameter, not the package — causing an `ImportError` at runtime.
Always import the package at module level under an alias: `import snowflake.connector as sf_connector`.

---

## Input expectations (pre-checks on source data)

Input expectations attach to `source_aligned_input()` via `.expectation()`. They run before the
transform against the source data.

```python
from nxd.spec import quality, source_aligned_input
from nxd.spec.validations import gx, soda

source_aligned_input()
.source("https://<app_url>/infra-profile/<profile>#/services/<service>")
.config(...)
.expectation(users_model)                      # model schema check
.expectation(
    quality(soda, "./contracts/checks.yml")
    .name("SodaInputCheck")
    .description("Soda checks on source table before transform")
)
.expectation(
    quality(gx, "./contracts/configure_expectation.py")
    .name("GXInputCheck")
    .description("GX column checks on source before transform")
)
```

Expectations and promises share the same contract file formats. The distinction is where they
run: expectations guard the input, promises guard the output.

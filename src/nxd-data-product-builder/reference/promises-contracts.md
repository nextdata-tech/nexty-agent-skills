# Promises and Contracts

Copy-paste reference for wiring output promises and input expectations into an NXD data product.

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
            snowflake_config("SCHEMA")
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

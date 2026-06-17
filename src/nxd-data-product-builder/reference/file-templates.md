# File Templates and Generated Layout

## Contents
- Generated files
- spec.py
- transform.py example: S3 (CSV) to Snowflake via external table
- imports_spec.py
- imports_models.py
- inputs/input_models.py
- outputs/output_models.py
- requirements.txt
- Driver Classification Reference

Concrete scaffolding for a new Data Product. Use these as starting points
during the **Implementation** phase, then adapt names, models, and drivers to
the user's plan. Prefer matching the closest public example
([examples-guide.md](examples-guide.md)) for file layout and imports; these
templates cover the common shapes when no example fits exactly.

> Note on shim modules: this builder uses project-local `nxd_spec.py` /
> `nxd_models.py` shim modules (see [best_practices.md](best_practices.md)).
> The `imports_spec.py` / `imports_models.py` form shown below is an
> equivalent centralized-imports pattern carried over from the former wizard —
> either works, but do not mix both in one product. Whichever you pick, every
> name used in `spec.py` / `models.py` must be re-exported by the shim it
> wildcard-imports.

## Generated files

Create these in `<data-product-name>/`:

| File | Purpose |
|------|---------|
| `spec.py` | Main data product definition using the fluent DSL |
| `transform.py` | Transform function with read/write skeleton |
| `imports_spec.py` (or `nxd_spec.py`) | Centralized DSL imports for `spec.py` |
| `imports_models.py` (or `nxd_models.py`) | Centralized model imports |
| `inputs/input_models.py` | Input semantic model definitions |
| `outputs/output_models.py` | Output semantic model definitions |
| `requirements.txt` | Python dependencies |
| `contracts/` | Quality check files (if requested) |

Set up the environment in the `<data-product-name>` folder before generating
files (Python 3.10 + `uv`, install `nxd-data-product` — see the skill's
Prerequisites).

## spec.py

The `{...}` fields are filled from discovery. In particular `{infra_profile}` is the profile **name chosen/derived in discovery** (local profile YAML, or `nxd ls infra-profiles` against the active mesh — see SKILL.md "Infra Profile Lookup"), and any service URLs use `https://<app_url>/infra-profile/<profile>#/services/<service>` where `<app_url>` is the active mesh's app host from mesh config. None of these are hardcoded demo values.

```python
# ruff: noqa: F403, F405
from imports_spec import *

spec = (
    data_product(
        name="{name}",
        domain="{domain}",
        description="{description}",
        version="{version}",
        infra_profile="{infra_profile}",
        source_repo_url="{source_repo_url}",
    )
    .transform(
        code(transform)
        .when(
            any_of(
                # Add triggers: updated("my-input"), scheduled("0 */8 * * *")
                # "my-input" is the name passed to .input() — NOT the upstream DP name
            ),
            startup=True,
        )
        .compute("{compute_url}")
    )
    .input(
        "{input_port_name}",
        source_aligned_input()  # or data_product_input() when sourcing from an upstream DP
        .source("{input_url}")
        .model({input_model_var}),
    )
    # repeat .input(...) for each input (source, model, etc.)
    .output(
        data_product_output()
        .port(
            "{output_port_name}",
            storage("{output_url}"),
        )
        .model({output_model_var})
    )
    # repeat .output(...) for each output (port, model, etc.)
    # .link("field", Predicate.GlossaryTerm, "glossary-full-name#/terms/term-id")
    # .control(...) for access
)
```

## transform.py — example: S3 (CSV) → Snowflake via external table

**When to use this pattern:** input is CSV files in S3, output is Snowflake.
Common shape for source-aligned data products that publish raw drops into the
warehouse.

**Snowflake-side prerequisites (one-time, set up outside the transform):**
- A `STORAGE INTEGRATION` with access to the input S3 bucket
- A `STAGE` wrapping that integration (e.g. `<DB>.RAW.S3_STAGE` over the bucket root)

The transform creates its own external table each run, derived from the input
semantic model — so when the user adds or renames a column in
`inputs/input_models.py`, the external table picks it up on the next run with
no DDL edits.

```python
import logging

from nxd.data_product.context import S3Input, Snowflake
from snowflake.connector import connect

# Substitute with the actual model variable names defined during planning.
from inputs.input_models import input_model_name
from outputs.output_models import output_model_name

_logger = logging.getLogger("transform.data_product_name")
_logger.setLevel(logging.INFO)

# Snowflake-side leaf names. The stage is admin-managed and pre-provisioned in
# STAGE_SCHEMA (typically a shared "raw" schema). The target table and the
# external table live in the per-DP schema the platform creates at runtime —
# that schema name comes from nxd_snowflake.schema and does NOT need to appear
# as a literal here. Only `STAGE_SCHEMA` is hardcoded because the stage sits
# outside the per-DP namespace.
STAGE_SCHEMA   = "RAW"                       # admin schema housing the stage
STAGE_NAME     = "S3_STAGE"                  # pre-provisioned stage in STAGE_SCHEMA
STAGE_PREFIX   = "s3_prefix"                 # sub-path under the stage
EXT_TABLE_NAME = "EXT_DATA_PRODUCT_UPPER"    # external table created by this transform

CSV_FORMAT = (
    "TYPE = CSV "
    "SKIP_HEADER = 1 "
    "FIELD_OPTIONALLY_ENCLOSED_BY = '\"' "
    "NULL_IF = ('', 'NULL') "
    "EMPTY_FIELD_AS_NULL = TRUE"
)

# Parameter names must match the input/output port names with hyphens → underscores.
# `s3_input` / `nxd_snowflake` shown here are illustrative.
def transform(s3_input: S3Input, nxd_snowflake: Snowflake) -> None:
    # DB and per-DP schema come from the platform-injected Snowflake context
    # (set from the infra-profile's Snowflake service config). Never hardcode them.
    db = nxd_snowflake.database
    dp_schema = nxd_snowflake.schema

    ext_table_fqn = f"{db}.{dp_schema}.{EXT_TABLE_NAME}"
    stage_path = f"@{db}.{STAGE_SCHEMA}.{STAGE_NAME}/{STAGE_PREFIX}"
    target_table = nxd_snowflake.model_tables[output_model_name.name]
    target_fqn = f"{db}.{dp_schema}.{target_table}"

    conn = _get_snowflake_conn(nxd_snowflake)
    try:
        with conn.cursor() as cur:
            # 1. (Re)build the external table from the input semantic model.
            #    Columns come from input_model_name._attributes — the single
            #    source of truth in inputs/input_models.py.
            cur.execute(_external_table_ddl(input_model_name, ext_table_fqn, stage_path))

            # 2. Full-refresh semantics for scheduled runs.
            cur.execute(f"TRUNCATE TABLE {target_fqn}")

            # 3. Load. For pass-through products (input schema == output schema),
            #    SELECT * is safe. External cols are VARCHAR; Snowflake casts
            #    them to the output model's typed columns on INSERT.
            cur.execute(f"INSERT INTO {target_fqn} SELECT * FROM {ext_table_fqn}")
            _logger.info("Inserted %s rows into %s", cur.rowcount, target_fqn)
    finally:
        conn.close()


def _external_table_ddl(model, ext_table_fqn: str, stage_path: str) -> str:
    """Derive CREATE OR REPLACE EXTERNAL TABLE DDL from a semantic model.

    All columns declared VARCHAR at the external layer (tolerant of malformed
    CSV); type casting happens implicitly on INSERT … SELECT into the typed
    target table.
    """
    column_names = list(model._attributes.keys())  # noqa: SLF001
    col_defs = ",\n            ".join(
        f"{name} VARCHAR AS (VALUE:c{i}::VARCHAR)"
        for i, name in enumerate(column_names, start=1)
    )
    return f"""
        CREATE OR REPLACE EXTERNAL TABLE {ext_table_fqn} (
            {col_defs}
        )
            LOCATION = {stage_path}
            PATTERN  = '.*[.]csv'
            FILE_FORMAT = ({CSV_FORMAT})
            AUTO_REFRESH = FALSE
    """

def _get_snowflake_conn(ctx: Snowflake):
    return connect(
        user=ctx.user, password=ctx.password, account=ctx.account,
        warehouse=ctx.warehouse, database=ctx.database,
        schema=ctx.schema,
    )
```

**What to substitute per build:**

| In the template | Replace with | Source |
|---|---|---|
| `input_model_name` | The input semantic model variable name | Planning |
| `output_model_name` | The output semantic model variable name | Planning |
| `s3_input`, `nxd_snowflake` | Transform parameter names (port names, hyphens → underscores) | Output ports |
| `data_product_name` (logger) | snake_case data product name | DP metadata |
| `STAGE_SCHEMA` | Admin schema housing the pre-provisioned stage (e.g. `RAW`) | Snowflake infra |
| `STAGE_NAME` | Pre-provisioned stage name inside STAGE_SCHEMA (e.g. `S3_STAGE`) | Snowflake infra |
| `STAGE_PREFIX` (`s3_prefix`) | Sub-path under the stage where this product's files land | User input |
| `EXT_TABLE_NAME` (`EXT_DATA_PRODUCT_UPPER`) | External-table name. Convention: `EXT_<DATA_PRODUCT_UPPER>`. Lives in the per-DP DB/schema at runtime — no DB/schema hardcoding needed. | Naming convention |
| `PATTERN` in DDL | `.*[.]csv` for CSV-only prefixes; tighten if other file types share the prefix | User input |

**Why this pattern (principles to preserve when adapting):**
- **Schemas live in `inputs/input_models.py` / `outputs/output_models.py`** — never duplicated as a `COLUMNS = [...]` list inside the transform.
- **Privileged DDL stays out of the transform.** `CREATE STORAGE INTEGRATION` and `CREATE STAGE` are Snowflake-side, one-time, human-operated. Only the `CREATE OR REPLACE EXTERNAL TABLE` belongs in the transform.
- **DB and per-DP schema come from the runtime Snowflake context, not literals.** `nxd_snowflake.database` and `nxd_snowflake.schema` are platform-injected from the infra-profile's Snowflake service config; the per-DP schema is provisioned automatically based on the DP name. Hardcoding either breaks portability across envs. Only the **stage's** schema needs hardcoding (it lives in an admin-managed schema outside the per-DP namespace).

For other driver shapes (PGVector, API, ADLS, ADLS+Spark), see
[driver_examples.md](driver_examples.md) and
[storage-configs.md](storage-configs.md).

## imports_spec.py

```python
from inputs.input_models import *  # noqa: F403
from outputs.output_models import *  # noqa: F403
from nxd.spec import Predicate, code, custom, data_product, data_product_access
from nxd.spec import data_product_input, data_product_output, owner, quality
from nxd.spec import source_aligned_input, storage
from nxd.spec.conditions import any_of, scheduled, updated
from nxd.spec.validations import gx, soda
from transform import transform
```

## imports_models.py

```python
from nxd.spec import Predicate, SamplingMethod, all_of, semantic_model
from nxd.spec.data_types import boolean, date32, date64, float64, int32, int64, number, string
```

## inputs/input_models.py

One `semantic_model(...).schema({...})` block per input model. Schema dict
values are `(type, description)` tuples — type constructors take zero args.

```python
from imports_models import *

{model_name} = semantic_model(
    name="{model_name}",
    description="{model_description}",
).schema({
    "{field_name}": ({type}(), "{field_description}"),
    # repeat per field
})
```

## outputs/output_models.py

Same shape as input models, optionally chained with `.sampling(...)`.

```python
from imports_models import *

{model_name} = semantic_model(
    name="{model_name}",
    description="{model_description}",
).schema({
    "{field_name}": ({type}(), "{field_description}"),
    # repeat per field
}).sampling(SamplingMethod.Random)
```

## requirements.txt

The base requirements always apply. Add per-driver dependencies based on the
input and output context types used in `transform.py`.

**Always include:**

```
nxd_core>=0.0.1
nxd_data_product>=0.0.1
pandas
```

Both packages are always required — missing either causes `ModuleNotFoundError`
at runtime. Package names use underscores, not dots.

**Add per context type used in transform.py:**

| Context type | Add to requirements.txt |
|---|---|
| `S3Input` | `requests` |
| `S3Output` | `boto3` |
| `Snowflake` (read or write) | `snowflake-connector-python[pandas]` |
| `DatabricksRead` / `DatabricksWrite` via `dbsql.connect()` | `databricks-sql-connector` |

See [common-pitfalls.md](common-pitfalls.md) for `nxd_core[soda]` / `nxd_core[gx]`
extras and other packaging gotchas.

## Driver Classification Reference

When classifying services discovered from an infra profile, parse the `driver`
field (format `nxd:<driver-name>:<version>`) and extract the middle segment
between the first `:` and the version number. Either `nxd:` or `nxd-test:` is a
valid scheme prefix.

| Category | Driver patterns |
|---|---|
| **Compute** | `kubernetes/compute`, `kubernetes/compute/streaming`, `local-python` (without `/rpc`), `databricks/compute`, `databricks/compute/streaming` |
| **Storage** | `s3`, `adls`, `snowflake`, `databricks/storage`, `postgres`, `kafka`, `pinecone`, `minio`, `dremio`, `duckdb`, `redshift`, `bigquery`, `postgres-vector` |
| **RPC** | `local-python/rpc`, `kubernetes/rpc` |
| **API** | `api` (external API connectors) |
| **Governance** | `servicenow`, `databricks/access-control`, `databricks-contract`, or anything not matching above |

Examples:
- `nxd:s3:1.0.0` → `s3` → **Storage**
- `nxd:kubernetes/compute:1.0.0` → `kubernetes/compute` → **Compute**
- `nxd:databricks/storage:1.0.0` → `databricks/storage` → **Storage**
- `nxd:local-python/rpc:1.0.0` → `local-python/rpc` → **RPC**
- `nxd:api:0.1.0` → `api` → **API**
- `nxd:servicenow:1.0.0` → `servicenow` → **Governance**

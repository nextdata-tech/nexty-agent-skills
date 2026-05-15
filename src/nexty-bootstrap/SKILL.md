---
name: nexty-bootstrap
description: Interactive wizard to bootstrap a new nextdata data product. Walks through inputs, semantic models, transformations, outputs, glossary links, and contracts, then generates Python spec files.
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
metadata:
  author: nextdata
  version: 0.1.0
---

# Nexty Bootstrap

You are a data product bootstrapping wizard for the nextdata platform. Walk the user through creating a new data product step by step, then generate the Python spec files.

## Prerequisites

This skill requires a working nxd CLI installation with an active mesh. Before starting the wizard, verify by running:

```bash
nxd --config /tmp/nxd-<mesh_name>.yaml ls data-products
```

If nxd-setup was run earlier in this session, use the `--config /tmp/nxd-<mesh_name>.yaml` flag it established. If no mesh is configured or the CLI isn't installed, run the **nxd-setup** skill first.

**Do not proceed to the wizard until `nxd ls data-products` succeeds.**

**Important**: All `nxd` commands in this wizard must include `--config /tmp/nxd-<mesh_name>.yaml` to target the correct mesh.

---

## Wizard Flow

Run these steps in order. Ask questions conversationally — one step at a time. After each step, confirm the user's answers before moving on.

### Step 1: Where do you want to start?

Ask: "Where is the data for this product coming from?" and present three options:

#### Option A: Existing data

The user has data they want to turn into a data product.

Ask: "Is the data available locally, or is it in a remote service?"

**Local data**: Ask for the file path (relative or absolute). Read the file (CSV, Parquet, JSON, etc.) and infer the schema — column names, types, and sample values. Use this to auto-generate input semantic models. Confirm with the user.

**Remote data (S3, Snowflake, ADLS, Databricks)**: For v1, help the user manually download a sample or get metadata so we can understand the data shape. Walk them through it:

- **S3**: Ask for the bucket name and folder/key path. Guide them:
  ```bash
  aws s3 cp s3://<bucket>/<path>/sample.csv ./sample-data/
  ```
  Then read the downloaded file to infer the schema.

- **Snowflake**: Ask for the database, schema, and table name. Guide them:
  ```bash
  # Using snowsql or the Snowflake CLI
  snowsql -q "DESCRIBE TABLE <database>.<schema>.<table>"
  # Or to get a sample:
  snowsql -q "SELECT * FROM <database>.<schema>.<table> LIMIT 10" -o output_format=csv -o output_file=sample-data/sample.csv
  ```
  Then use the DESCRIBE output or sample to infer the schema.

- **ADLS**: Ask for the storage account, container, and blob path. Guide them:
  ```bash
  az storage blob download --account-name <account> --container-name <container> --name <path> --file ./sample-data/sample.csv
  ```

- **Databricks**: Ask for the catalog, schema, and table name. Guide them:
  ```bash
  databricks sql execute --statement "DESCRIBE TABLE <catalog>.<schema>.<table>"
  # Or for a sample:
  databricks sql execute --statement "SELECT * FROM <catalog>.<schema>.<table> LIMIT 10"
  ```

After obtaining the data or metadata, infer the schema and auto-generate input semantic models. Confirm with the user.

#### Option B: Existing source code

The user has transformation code they want to wrap as a data product.

Ask for the relative path to the codebase. Read the source code to understand:
- What data it reads (inputs) and from where
- What transformations it performs
- What data it produces (outputs)
- Any existing schema definitions

Use this analysis to pre-populate items for step 2.

#### Option C: Other data products

The user wants to build on top of existing nextdata data products.

Run:
```bash
nxd --config /tmp/nxd-<mesh_name>.yaml ls data-products
```

Show the list and ask the user to select which data products to use as inputs. For each selected product, the generated `spec.py` will use `data_product_input().source(...)` pointing to that product's output port.

If the product has published semantic models, use those as the input model definitions. Otherwise, ask the user to describe the expected schema.

---

The user must pick exactly one option. Do not allow combining options.

### Step 2: Domain, Infra Profile & Data Product Basics

This step has four sub-steps that validate the user's access before collecting metadata. After this step you must know: which domain the user can launch in, which infra profile to use, what compute and storage services are available, which compute service will run transforms, which storage service(s) will hold outputs, and the DP metadata.

#### Step 2a: Domain Selection

> **CLI limitation**: There is NO `nxd ls domains` command. The `nxd ls` subcommands are: data-products, data-product-images, data-product-templates, infra-profiles, users, personal-access-tokens, role-assignments, contracts, policies. Do not attempt to list domains directly via the CLI.

**Identify the user:**

1. Run `nxd --config /tmp/nxd-<mesh_name>.yaml whoami` to get the current user's email.

**Determine access level (short-circuit on first match):**

2. Run `nxd --config /tmp/nxd-<mesh_name>.yaml ls role-assignments --role system:admin --format json`. Parse the JSON — each entry has `role`, optional `scope` (with `domain`), and `subjects` (with `user` emails). If the current user's email appears in any entry, they are a **system admin** with mesh-wide access. Skip to "Discover domains" below.

3. Only if NOT a system:admin — run `nxd --config /tmp/nxd-<mesh_name>.yaml ls role-assignments --role domain:admin --format json`. If the user appears in an entry with no `scope` (mesh-wide domain admin), skip to "Discover domains" below. If they appear in entries with specific `scope.domain` values, collect those domain names.

4. Only if NOT any admin — run `nxd --config /tmp/nxd-<mesh_name>.yaml ls role-assignments --role data-product:producer --format json`. Collect all `scope.domain` values from entries matching the user's email. If no domains are found across steps 2-4, the user cannot launch a data product anywhere — tell them to contact a domain admin for `data-product:producer` access and **stop here**.

**Discover domains:**

5. Retrieve the list of domains that exist on the mesh via the REST API:

```bash
API_URL=$(grep 'url:' /tmp/nxd-<mesh_name>.yaml | head -1 | awk '{print $2}')
TOKEN=$(grep 'personal_access_token:' /tmp/nxd-<mesh_name>.yaml | awk '{print $2}')
curl -s -H "x-nextdata-token: $TOKEN" "$API_URL/api/v1/data-products" | \
  python3 -c "import json,sys; dps=json.load(sys.stdin)['dataProducts']; \
  domains=sorted(set(dp['domain'] for dp in dps if dp.get('domain'))); \
  [print(d) for d in domains]"
```

This returns every domain that has at least one data product. Domains cannot exist without data products.

**Select a domain:**

6. **If the user has scoped domains** (from steps 3-4): Present those as a numbered list. Also show the full domain list from step 5 for reference, noting which ones the user has access to.

7. **If the user has mesh-wide access** (system:admin or unscoped domain:admin): Present the domain list from step 5 as a numbered list and ask the user to pick one. Also allow manual entry for new domains that don't have data products yet.

8. After selection, run `nxd --config /tmp/nxd-<mesh_name>.yaml describe domain <selected_domain> --format json` to confirm the domain exists. Show the domain details (name, propagation, producers) for confirmation.

**Edge cases:**
- **No roles found at all** (steps 2-4 yield nothing): The user cannot launch a data product. Tell them to contact a domain admin for `data-product:producer` access. Do not proceed.
- **User knows a domain not in the list** (permissions may be inherited from a parent domain): Allow manual entry. Validate with `nxd --config /tmp/nxd-<mesh_name>.yaml describe domain <name> --format json`.
- **REST API call fails**: Fall back to `nxd --config /tmp/nxd-<mesh_name>.yaml ls infra-profiles | sed 's/\x1B\[[0-9;]*m//g'` and extract unique values from the DOMAIN column.

#### Step 2b: Infra Profile & Service Discovery

1. Run `nxd --config /tmp/nxd-<mesh_name>.yaml ls infra-profiles --domain <selected_domain> | sed 's/\x1B\[[0-9;]*m//g'` to list profiles in the chosen domain. The `sed` strips ANSI color codes from the CLI output. The result is a text table with DOMAIN, NAME, CREATED_AT, CREATED_BY columns.
2. If no profiles are found, also try without `--domain` (root-level profiles may be shared): `nxd --config /tmp/nxd-<mesh_name>.yaml ls infra-profiles | sed 's/\x1B\[[0-9;]*m//g'`
3. Present the available profiles as a numbered list and ask the user to pick one.

**Discover services** — the CLI has no `describe infra-profile` command, so use the REST API directly:

```bash
# Extract API URL from the session config
API_URL=$(grep 'url:' /tmp/nxd-<mesh_name>.yaml | head -1 | awk '{print $2}')
# Read the PAT from the mesh registry
TOKEN=$(python3 -c "
import json, pathlib
meshes = json.loads(pathlib.Path.home().joinpath('.nxd/meshes.json').read_text())
for name, m in meshes.items():
    if '<mesh_name>' in name:
        print(m['token']); break
")

curl -s -H "x-nextdata-token: $TOKEN" \
  "$API_URL/api/v1/infraprofiles/<PROFILE_NAME>/services?domain=<DOMAIN>"
```

**API**: `GET /api/v1/infraprofiles/{profile}/services?domain={domain}` returns a JSON array of `{name, driver, attributes}`.
**Auth header**: `x-nextdata-token` (not `Authorization: Bearer`).
**Permission**: requires `can_see_infra_profile_secrets`, which domain producers have.

**Do not display `attributes`** — they contain credentials. Only use `name` and `driver`.

**Classify each service** by parsing the `driver` field (format `nxd:<driver-name>:<version>`, extract the middle segment) using the Driver Classification Reference at the bottom of this document.

Present the categorized services:

```
Infra profile "ecommerce-demo" services:

COMPUTE:
  - k8s-compute (kubernetes/compute)
  - nxd-databricks (databricks/compute)

STORAGE:
  - s3-input (s3)
  - s3-output (s3)
  - nxd-snowflake (snowflake)
  - adls (adls)
  - nxd-databricks-storage (databricks/storage)

RPC:
  - mcp-api-service (local-python/rpc)

GOVERNANCE:
  - servicenow-user-approval (servicenow)
```

**Validate completeness:**
- Must have at least 1 compute service. If missing, warn the user — they won't be able to run transforms.
- Should have at least 1 storage service. If missing, note it — the user might rely solely on `data_product_input` from other DPs.

**Fallback**: If the `curl` call fails (auth mismatch, network error), ask the user to list the services their infra profile contains. Most platform teams document this for their developers.

**Record the service inventory** for use in later steps. For each service, track:
- Service name (e.g. `nxd-s3`)
- Driver name (e.g. `s3`)
- Category (`compute` / `storage` / `rpc` / `governance`)
- Service URL: `https://<api_url>/infra-profile/<PROFILE_NAME>#/services/<SERVICE_NAME>`

#### Step 2c: Data Product Metadata

Domain and infra profile are already confirmed — display them as locked values. Collect the remaining metadata with smart defaults from Steps 1, 2a, 2b:

- **Name** (kebab-case, e.g. `sales-influence-insights`) — suggest from the data source or code analyzed in Step 1
- **Domain** — already selected in 2a, display only
- **Description** (1-2 sentences) — suggest from Step 1 context
- **Version** (default: `0.1.0-dev`)
- **Infra profile** — already selected in 2b, display only
- **Source repo URL** — detect from `git remote get-url origin` if in a git repo, otherwise ask

Have the user confirm or edit name, description, version, and source repo URL.

#### Step 2d: Transform Compute & Output Storage Selection

Using the service inventory from Step 2b, pin two decisions that all later steps depend on:

**Transform compute**: If only one compute service exists, auto-select it and confirm with the user. If multiple exist, present them as a numbered list and ask the user to choose. Record the selected compute service name and URL.

**Output storage destination**: Present the available storage services as a numbered list and ask: "Where should the output data land?" If the user picks multiple destinations (e.g. S3 and Snowflake), record all of them. Record each selected storage service name, driver, and URL.

After this step, summarize the locked choices:

```
Locked configuration:
  - Input format: <from Step 1, e.g. "CSV files from S3", "Snowflake table", "Parquet on ADLS">
  - Transform compute: <selected compute service> (<driver>)
  - Output storage: <selected storage service(s)> (<driver(s)>)
```

These selections are final — later steps reference them, not re-ask.

### Step 3: Input Sources & Semantic Models

> See [references/storage-configs.md](references/storage-configs.md) for all storage config helpers, source URL patterns, and context types per driver.

**Use the service inventory from Step 2b.** When asking for the source URL, present the available storage services as options rather than asking for a raw URL. Construct the URL automatically: `https://<api_url>/infra-profile/<PROFILE>#/services/<SERVICE_NAME>`.

Based on Step 1, you should already have a good understanding of the input data shape.

For each input source, finalize:
- **Input name** (kebab-case identifier, e.g. `store-sales-adls`)
- **Input type**: `data_product_input` (from another data product) or `source_aligned_input` (raw/external source)
- **Source URL** — select from the storage services discovered in Step 2b
- **Semantic model**: `semantic_model()` with name (snake_case), description, and schema with field names, data types, and descriptions
- Available types: `string()`, `number()`, `int32()`, `int64()`, `float64()`, `boolean()`, `date32()`, `date64()`

If you inferred models from data/code in Step 1, present them for confirmation. Let the user adjust field names, types, or descriptions.

### Step 4: Output Semantic Models

Reference the locked configuration from Step 2d to frame output models concretely. The user already knows:
- **Input data format**: from Step 1 (e.g. CSV, Parquet, JSON, Snowflake table, ADLS blob, Databricks table)
- **Output storage**: from Step 2d (e.g. S3, Snowflake, ADLS)

Ask: "What data does this product produce?" Frame the question using the actual technologies — for example: "Given your [Parquet files from ADLS] inputs and [Snowflake] output destination, what models should this product expose?"

For each output model, collect the same as input models (name, description, schema with field names, types, descriptions).

Additionally:

#### Glossary Term Matching (Required)

This step is mandatory — always fetch glossaries and attempt matching, regardless of whether matches are expected.

Fetch available glossary terms from the platform API using the same auth pattern as Step 2b:

```bash
curl -s -H "x-nextdata-token: $TOKEN" "$API_URL/api/v1/data-products/glossaries"
```

This returns a JSON array of `{name, fullName, domain, glossary}` objects, where `glossary` contains the actual terms and definitions.

For each glossary in the response:
1. Compare the glossary terms against the output model field names and descriptions
2. Propose matches where a glossary term aligns with a field (by name similarity or semantic meaning)
3. Present proposed matches to the user for confirmation

For each confirmed match, record the link using:
```python
.link("field_name", Predicate.GlossaryTerm, "<glossary-dp-full-name>#/terms/<term-id>")
```

If no glossary terms match any fields, explicitly state: "No glossary term matches found for these output models" and move on. Do not skip this step.

#### Upstream Links (Options B & C only)

**Skip this section entirely if the user chose Option A (existing data / source-aligned) in Step 1.** For source-aligned products, outputs mirror inputs 1:1 — every field traces back to itself, making SameAs links redundant.

**For Option B (existing source code) or Option C (other data products)**: Ask if any output fields trace back to specific input model fields. For each such relationship, record:
```python
.link("output_field", Predicate.SameAs, "<input-model>#/schema/<input-field>")
```

#### Other Output Model Properties

- **Dependencies**: Does this model depend on other output models? (use `.when(all_of(...))`)
- **Sampling method**: `SamplingMethod.Random` (default) or `SamplingMethod.Head`

### Step 5: Transform Logic

> See [references/data-types.md](references/data-types.md) for complex types (timestamp, decimal, vector_embeddings, struct, list, map).

The compute service was selected in Step 2d — use it for `.compute(...)` in spec.py. Do not re-ask.

Ask: "Describe what the transformation does — how do inputs become outputs?"

Generate a `transform.py` skeleton with:
- Function signature matching input/output port names
- Read from each input using the appropriate context type (`AzureDataLakeStorage`, `Snowflake`, `S3Input`, etc.)
- Write to each output port (`S3Output`, `Snowflake`, etc.)
- TODO comments for the actual transformation logic
- Support for both full execution and subtransform (per-model) execution

### Step 6: Output Ports (Confirmation)

The output storage destination(s) were selected in Step 2d. This step maps output models to ports.

Present the proposed port configuration:
- **Port name** — auto-generate from the storage driver (e.g. `nxd_snowflake`, `iceberg_on_s3`) using the storage service(s) selected in Step 2d
- **Storage URL** — constructed automatically: `https://<api_url>/infra-profile/<PROFILE>#/services/<SERVICE_NAME>`
- **Model mapping** — if only one storage destination, all models go to one port; if multiple, ask which models go to which port

Ask: "Here is the proposed output port configuration. Does this look right?" Let the user adjust port names or model routing if needed.

### Step 7: Data Quality (Optional)

Ask: "Do you want data quality checks?"

If yes, offer these options:
- **Completeness** — verify null rates below a threshold
- **PII detection** — scan for personal data patterns
- **Soda checks** — YAML-based quality rules (generates a `.yaml` file in `contracts/`)
- **Great Expectations** — Python-based expectations (generates a `.py` file in `contracts/`)
- **Custom** — user-defined verify function

### Step 8: Access Controls (Optional)

Ask: "Who should have access?"

Collect:
- **Owner** email(s)
- **Data steward** email(s)
- **Consumer access** email(s)

### Step 9: References

Ask: Should I check for references ?

For API documentation and real-world examples, clone or browse the public examples repo:

```bash
git clone https://github.com/nextdata-tech/nextdata-public-examples.git
```

Each directory under `data_products/` is a complete data product (spec.py, transform.py, models, etc.). Use these as reference when generating files — pick the example closest to what the user is building.

### Step 10: Generate Files

Ask: In Spec file do you want the Data Product to run when updated("upstream-product") or scheduled("0 */8 * * *")?

If the user chooses any 1 then the format for when() in spec file under transform would be when(updated("upstream-product")) or when(scheduled("0 */8 * * *")) based on what user chooses. If they choose both, then the current format is correct in the template using any_of().

Confirm the full configuration, then generate all files in a new directory named after the data product.

## Generated Files

Create these files in `<data-product-name>/`:

Before Generating the files, set up the environment in the <data-product-name> folder. Do **not** proceed until this is complete.


- **Runtime:** Python **3.10** with **`uv`** as the dependency manager.
    - *There is no need to check for a given Python version since `uv` will manage this for us.*
- **Dependencies:** Install the `nxd-data-product` Python package ([registry](https://registry.trynxd.com/index/)):

```bash
uv init --bare --python 3.10
uv venv --python 3.10
uv add nxd-data-product --index nxd=https://registry.trynxd.com/index/
```

| File | Purpose |
|------|---------|
| `spec.py` | Main data product definition using fluent DSL |
| `transform.py` | Transform function with read/write skeleton |
| `imports_spec.py` | Centralized DSL imports for spec.py |
| `imports_models.py` | Centralized model imports for input and output models |
| `inputs/input_models.py` | Input semantic model definitions |
| `outputs/output_models.py` | Output semantic model definitions |
| `requirements.txt` | Python dependencies |
| `contracts/` | Quality check files (if requested) |

## File Templates

### spec.py

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
    # repeat .input(...) format for each input that includes source, model etc
    .output(
        data_product_output()
        .port(
            "{output_port_name}",
            storage("{output_url}"),
        )
        .model({output_model_var})
    )
    # repeat .output(...) format for each output that includes port, model etc
    # .link("field", Predicate.GlossaryTerm, "glossary-full-name#/terms/term-id") from Step 4
    # .control(...) for access
)
```

### transform.py — example: S3 (CSV) → Snowflake via external table

**When to use this pattern:** input is CSV files in S3, output is Snowflake. Common shape for source-aligned data products that publish raw drops into the warehouse.

**Snowflake-side prerequisites (one-time, set up outside the transform):**
- A `STORAGE INTEGRATION` with access to the input S3 bucket
- A `STAGE` wrapping that integration (e.g. `<DB>.RAW.S3_STAGE` over the bucket root)

The transform creates its own external table each run, derived from the input semantic model — so when the user adds or renames a column in `inputs/input_models.py`, the external table picks it up on the next run with no DDL edits.

```python
import logging

from nxd.data_product.context import S3Input, Snowflake
from snowflake.connector import connect

# Substitute with the actual model variable names defined in Steps 3 and 4.
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

# Parameter names must match the input/output port names with hyphens → underscores
# (see Gotchas section). `s3_input` / `nxd_snowflake` shown here are illustrative.
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

**What to substitute per bootstrap session:**

| In the template | Replace with | Source |
|---|---|---|
| `input_model_name` | The input semantic model variable name | Step 3 |
| `output_model_name` | The output semantic model variable name | Step 4 |
| `s3_input`, `nxd_snowflake` | Transform parameter names (port names, hyphens → underscores) | Step 6 |
| `data_product_name` (logger) | snake_case data product name | Step 2c |
| `STAGE_SCHEMA` | Admin schema housing the pre-provisioned stage (e.g. `RAW`) | Snowflake infra |
| `STAGE_NAME` | Pre-provisioned stage name inside STAGE_SCHEMA (e.g. `S3_STAGE`) | Snowflake infra |
| `STAGE_PREFIX` (`s3_prefix`) | Sub-path under the stage where this product's files land | User input |
| `EXT_TABLE_NAME` (`EXT_DATA_PRODUCT_UPPER`) | External-table name. Suggested convention: `EXT_<DATA_PRODUCT_UPPER>`. Lives in `nxd_snowflake.database.nxd_snowflake.schema` at runtime — no DB/schema hardcoding needed. | Naming convention |
| `PATTERN` in DDL | `.*[.]csv` for CSV-only prefixes; tighten if other file types share the prefix | User input |

**Why this pattern (principles to preserve when adapting):**
- **Schemas live in `inputs/input_models.py` / `outputs/output_models.py`** — never duplicated as a `COLUMNS = [...]` list inside the transform.
- **Privileged DDL stays out of the transform.** `CREATE STORAGE INTEGRATION` and `CREATE STAGE` are Snowflake-side, one-time, human-operated. Only the `CREATE OR REPLACE EXTERNAL TABLE` belongs in the transform.
- **DB and per-DP schema come from the runtime Snowflake context, not literals.** `nxd_snowflake.database` and `nxd_snowflake.schema` are platform-injected from the infra-profile's Snowflake service config; the per-DP schema is provisioned automatically based on the DP name. Hardcoding either breaks portability across envs and means dev/prod can't share the same code. Only the **stage's** schema needs hardcoding (it lives in an admin-managed schema outside the per-DP namespace).

### imports_spec.py

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

### imports_models.py

```python
from nxd.spec import Predicate, SamplingMethod, all_of, semantic_model
from nxd.spec.data_types import boolean, date32, date64, float64, int32, int64, number, string
```

### inputs/input_models.py

One `semantic_model(...).schema({...})` block per input model. Schema dict values are `(type, description)` tuples — type constructors take zero args.

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

### outputs/output_models.py

Same shape as input models, optionally chained with `.sample(...)`.

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

### requirements.txt

The base requirements always apply. Add per-driver dependencies based on
the input and output context types selected in Step 2d.

**Always include:**

```
nxd_core>=0.0.1
nxd_data_product>=0.0.1
pandas
```
Both packages are always required — missing either causes `ModuleNotFoundError` at runtime. Package names use underscores, not dots.

**Add per context type used in transform.py:**

| Context type | Add to requirements.txt |
|---|---|
| `S3Input` | `requests` |
| `S3Output` | `boto3` |
| `Snowflake` (read or write) | `snowflake-connector-python[pandas]` |

## Gotchas

- **Naming**: Data product names are kebab-case (`my-product`). Python identifiers are snake_case (`my_model`).
- **Model names in schema**: Use snake_case for semantic model names (e.g. `channel_sales_velocity`).
- **Type constructors take zero args**: `string()`, `int64()`, `boolean()`, etc. accept no positional arguments. Descriptions attach via `.schema({name: (type(), "desc")})` tuple form, never `string("desc")` — that raises `TypeError` at import time.
- **Import structure**: `spec.py` imports everything from `imports_spec.py` via wildcard. `imports_spec.py` imports from `nxd.spec` and local modules. `imports_models.py` imports types used in model definitions.
- **Transform function signature**: Parameter names must match input/output port names with hyphens converted to underscores (e.g. port `iceberg-on-s3` becomes parameter `iceberg_on_s3`).
- **Context types**: Use `AzureDataLakeStorage`, `Snowflake`, `S3Input`, `S3Output` from `nxd.data_product.context` for transform function type hints.
- **Glossary links**: Can be at model level (`.link("field", Predicate.GlossaryTerm, url)`) or product level (`.link(Predicate.GlossaryTerm, url)`).
- **Quality promises**: Attach to output ports via `.promise()`. Can use `soda` (YAML), `gx` (Python), or `custom` (verify function returning `VerifyResult`).
- **`updated()` takes input name**: `updated("my-input")` matches the name from `.input("my-input", ...)`, not the upstream DP name. Passing the upstream DP name will never trigger.
- **`source_aligned_input()` vs `data_product_input()`**: Use `source_aligned_input()` for external storage (S3, Databricks, Snowflake, ADLS, Kafka); `data_product_input()` for DP-to-DP dependencies. They have different `.source()` URL patterns.
- **Contract compute driver**: `nxd:local-python:1.0.0` is deprecated. Soda/GX checks use `nxd:kubernetes/contract:1.0.0`. No `.compute()` call needed — it auto-selects.
- **Full pitfalls list**: [references/common-pitfalls.md](references/common-pitfalls.md)

## Driver Classification Reference

When classifying services discovered from an infra profile, parse the driver field (format `nxd:<driver-name>:<version>`) and extract the middle segment. Use this table to categorize:

| Category | Driver patterns |
|---|---|
| **Compute** | `kubernetes/compute`, `kubernetes/compute/streaming`, `local-python` (without `/rpc`), `databricks/compute`, `databricks/compute/streaming` |
| **Storage** | `s3`, `adls`, `snowflake`, `databricks/storage`, `postgres`, `kafka`, `pinecone`, `minio`, `dremio`, `duckdb`, `redshift`, `bigquery`, `postgres-vector` |
| **RPC** | `local-python/rpc`, `kubernetes/rpc` |
| **API** | `api` (external API connectors) |
| **Governance** | `servicenow`, `databricks/access-control`, `databricks-contract`, or anything not matching above |

The driver field format may use either `nxd:` or `nxd-test:` as the scheme prefix — both are valid. Extract the middle segment between the first `:` and the version number.

Examples:
- `nxd:s3:1.0.0` → driver name `s3` → **Storage**
- `nxd:kubernetes/compute:1.0.0` → driver name `kubernetes/compute` → **Compute**
- `nxd:databricks/compute:1.0.0` → driver name `databricks/compute` → **Compute**
- `nxd:databricks/storage:1.0.0` → driver name `databricks/storage` → **Storage**
- `nxd:local-python/rpc:1.0.0` → driver name `local-python/rpc` → **RPC**
- `nxd:api:0.1.0` → driver name `api` → **API**
- `nxd:servicenow:1.0.0` → driver name `servicenow` → **Governance**

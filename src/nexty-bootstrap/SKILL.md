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

This step has three sub-steps that validate the user's access before collecting metadata. After this step you must know: which domain the user can launch in, which infra profile to use, what compute and storage services are available, and the DP metadata.

#### Step 2a: Domain Selection

1. Run `nxd --config /tmp/nxd-<mesh_name>.yaml whoami` to get the current user's email.
2. Check what roles the user has. Run these three commands and collect domain names from each:
   - `nxd --config /tmp/nxd-<mesh_name>.yaml ls role-assignments --role data-product:producer --format json` — direct producer access (can launch DPs)
   - `nxd --config /tmp/nxd-<mesh_name>.yaml ls role-assignments --role domain:admin --format json` — domain admin (can launch in administered domains)
   - `nxd --config /tmp/nxd-<mesh_name>.yaml ls role-assignments --role system:admin --format json` — system admin (can launch in any domain)
3. Parse each JSON output. Each entry has `role`, `scope` (containing `domain` — may be null for mesh-wide roles), and `subjects` (containing `user` emails). Filter to entries matching the current user's email.
4. Merge the domains from all three queries. If the user is a `system:admin` or a `domain:admin` with no scope, they can launch in any domain — note this and ask which domain they want to use.
5. Present the domains as a numbered list and ask the user to pick one.

**Edge cases:**
- **No roles found at all**: The user cannot launch a data product anywhere. Tell them to contact a domain admin for `data-product:producer` access. Do not proceed.
- **User is system/domain admin with no scoped domains**: They have broad access. Ask them to type the domain name they want to use.
- **User knows a domain not in the list** (permissions may be inherited from a parent domain): Allow manual entry. Validate with `nxd --config /tmp/nxd-<mesh_name>.yaml describe domain <name> --format json` and check the user appears in the `producers` or `admins` list.

After selection, run `nxd --config /tmp/nxd-<mesh_name>.yaml describe domain <selected_domain> --format json` to confirm access. Show the domain details (name, propagation, producers) for confirmation.

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

### Step 3: Input Sources & Semantic Models

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

Ask: "What data does this product produce?"

For each output model, collect the same as input models plus:
- **Glossary links**: Ask if any fields should link to glossary terms (use `Predicate.GlossaryTerm`)
- **Upstream links**: Ask if any fields trace back to input model fields (use `Predicate.SameAs`)
- **Dependencies**: Does this model depend on other output models? (use `.when(all_of(...))`)
- **Sampling method**: `SamplingMethod.Random` (default) or `SamplingMethod.Head`

### Step 5: Transform Logic

**Use the service inventory from Step 2b.** Auto-select the compute service for `.compute(...)` in spec.py. If the profile has multiple compute services, let the user choose.

Ask: "Describe what the transformation does — how do inputs become outputs?"

Generate a `transform.py` skeleton with:
- Function signature matching input/output port names
- Read from each input using the appropriate context type (`AzureDataLakeStorage`, `Snowflake`, `S3Input`, etc.)
- Write to each output port (`S3Output`, `Snowflake`, etc.)
- TODO comments for the actual transformation logic
- Support for both full execution and subtransform (per-model) execution

### Step 6: Output Ports

**Use the service inventory from Step 2b.** Present the available storage services as destination options rather than asking for a raw URL. Construct the URL automatically.

Ask: "Where should the output data be stored?"

For each output port, collect:
- **Port name** (e.g. `iceberg_on_s3`, `nxd_snowflake`)
- **Storage URL** — select from the storage services discovered in Step 2b
- **Which models** go to this port

### Step 7: Data Quality (Optional)

Ask: "Do you want data quality checks?"

If yes, offer these options:
- **Completeness** — verify null rates below a threshold
- **PII detection** — scan for personal data patterns
- **Soda checks** — YAML-based quality rules (generates a `.yaml` file in `contracts/`)
- **Great Expectations** — Python-based expectations (generates a `.py` file in `contracts/`)
- **Custom** — user-defined verify function

### Step 8: Glossary Links (Optional)

Ask: "Should this data product link to any glossary terms?"

Collect glossary term URLs for product-level links.

### Step 9: Access Controls (Optional)

Ask: "Who should have access?"

Collect:
- **Owner** email(s)
- **Data steward** email(s)
- **Consumer access** email(s)

### Step 10: Generate Files

Confirm the full configuration, then generate all files in a new directory named after the data product.

## Generated Files

Create these files in `<data-product-name>/`:

| File | Purpose |
|------|---------|
| `spec.py` | Main data product definition using fluent DSL |
| `transform.py` | Transform function with read/write skeleton |
| `imports_spec.py` | Centralized DSL imports for spec.py |
| `imports_models.py` | Centralized model imports for output_models |
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
                # Add triggers: updated("upstream-product"), scheduled("0 */8 * * *")
            ),
            startup=True,
        )
        .compute("{compute_url}")
    )
    # .input(...) for each input
    # .output(...) for each output
    # .link(...) for glossary terms
    # .control(...) for access
)
```

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

### requirements.txt

```
nxd.core
nxd.data_product[spec]
pandas<=2.1.4
```

## Gotchas

- **Naming**: Data product names are kebab-case (`my-product`). Python identifiers are snake_case (`my_model`).
- **Model names in schema**: Use snake_case for semantic model names (e.g. `channel_sales_velocity`).
- **Import structure**: `spec.py` imports everything from `imports_spec.py` via wildcard. `imports_spec.py` imports from `nxd.spec` and local modules. `imports_models.py` imports types used in model definitions.
- **Transform function signature**: Parameter names must match input/output port names with hyphens converted to underscores (e.g. port `iceberg-on-s3` becomes parameter `iceberg_on_s3`).
- **Context types**: Use `AzureDataLakeStorage`, `Snowflake`, `S3Input`, `S3Output` from `nxd.data_product.context` for transform function type hints.
- **Glossary links**: Can be at model level (`.link("field", Predicate.GlossaryTerm, url)`) or product level (`.link(Predicate.GlossaryTerm, url)`).
- **Quality promises**: Attach to output ports via `.promise()`. Can use `soda` (YAML), `gx` (Python), or `custom` (verify function returning `VerifyResult`).

## References

For API documentation and real-world examples, clone or browse the public examples repo:

```bash
git clone https://github.com/nextdata-tech/nextdata-public-examples.git
```

Each directory under `data_products/` is a complete data product (spec.py, transform.py, models, etc.). Use these as reference when generating files — pick the example closest to what the user is building.

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

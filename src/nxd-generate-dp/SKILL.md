---
name: nxd-generate-dp
description: Generates the COMPLETE runnable Python-only data-product closure for lean-desktop Nextdata OS (the desktop supervisor) from a natural-language intent, an inferred semantic model, and a connector config — spec.py + models.py + infra-profile.yaml + transform/main.py + requirements + the connector artifact (a local file export, a live database connection, or an off-mesh REST API), ready to boot locally and produce a queryable DuckDB result. The supervisor compiles spec.py into the kernel definition YAML at create time, so the author never hand-writes deployment-spec / manifest / models YAML. Use when the task is to "generate a data product", "build a DP from intent", "assemble a runnable data product around an inferred semantic model", or to turn a connector config plus stakeholder questions into a local desktop DP. Pairs with nxd-semantic-data-product, which INFERS the semantic model this skill PLACES. Not for the k8s/Snowflake topology — use nxd-data-product-builder there.
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
  version: 0.13.0
---

# nxd-generate-dp skill

## Overview

This skill assembles the **complete Python-only definition closure** for a
local (desktop) data product from these inputs:

1. **Intent** — the user's natural-language description of what the DP is for.
2. **Inferred semantic model** — the per-column semantic roles produced by the
   **nxd-semantic-data-product** skill's inference mode (its `schema.json`
   profile + role declarations). That skill designs the roles; this skill
   places them. Do not redesign them.
3. **Connector config(s)** — one or more, each naming where the source data
   lives and its **connector type**. Never invent connection details or
   credentials for a database or API connector.

**Connector types at a glance** — the canonical mapping; every other mention below points back here instead of restating it:

| Type | Service | `secrets[...]` key | Companion artifact |
|---|---|---|---|
| CSV (proven, fully-inlined default below) | `csv-source` | `csv_source` | `csv-source-path` + `data/` |
| Other file (JSON/JSONL/Parquet) — `reference/file-source.md` | `file-source` | `file_source` | `file-source-path` + `data/` |
| Database — `reference/database-source.md` | `db-source` | `db_source` | `db-source-tables`, no `data/` |
| REST API — `reference/api-source.md` | `api-source` | `api_source` | `api-source-endpoints`, no `data/` |

Names above are for exactly one instance of a type — for 2+, label each per `reference/multi-source.md`.

The output is a directory the **desktop supervisor** compiles, pins, boots, and
publishes: it **compiles `spec.py` into the kernel definition YAML at create
time**, then runs the transform, verifies staging, and stands up the semantic
MCP endpoint over it.

## The closure layout

The author emits **Python and prerequisite config only**:

```
<dp-root>/
├── spec.py                # author-facing definition: promises + transform + output port
├── models.py              # semantic models + placed semantic roles
├── infra-profile.yaml     # the desktop-local profile: duckdb + python-compute + csv-source
├── transform/
│   └── main.py            # the dlt-through-port ingest (standalone entrypoint)
├── requirements.txt       # proven pins (below)
├── csv-source-path        # one line: relative path to the CSV export root
└── data/                  # the connector export: data/<base_model>/*.csv
    └── <base_model>/…     # base models only — derived models have no data dir
```

> CSV layout (the proven default); other types swap the companion artifact per the connector-types table (Overview).

**The author NEVER writes `deployment-spec.yaml`, `manifest.yaml`, or
`models.yaml`.** The supervisor compiles those three from `spec.py` +
`models.py` when it pins the DP — including the `model_tables` identity map, the
staging-path placeholder, and the compiled semantic roles the semantic child
reads. It owns their shape and will overwrite them; your source of truth is the
Python.

> Layout note: unlike the k8s `.semantic_tools()` topology (modules flat at
> the DP root, no subdir), the desktop closure keeps the transform at
> `transform/main.py` — the directory the snapshot pins and the local Python
> compute driver executes. `models.py`/`spec.py` sit at the root, imported by the compiler.

---

## THE NAMING INVARIANT (the correctness spine — protect it everywhere)

One lowercase, unquoted, snake_case name per model, agreed on by the **authored
surfaces** below (the supervisor derives the compiled-YAML `models.yaml` name
and the `model_tables` identity map from these — you do not author them):

| Surface | Where the name appears | Base | Derived |
|---|---|---|---|
| `models.py` | `semantic_model("<name>")` | yes | yes |
| `spec.py` | `.promise(<name>)` — imported from `models` | yes | yes |
| `transform/main.py` | listed in `PHYSICAL_MODELS` | yes | yes |
| the physical table | what dlt writes: `main.<name>` | yes | yes |
| the connector's per-model reference | `data/<name>/` for a file connector (CSV/JSON/JSONL/Parquet); a `db-source-tables` entry for a database connector; an `api-source-endpoints` entry for a REST API connector | yes | **no** |

`PHYSICAL_MODELS` is the set of **landed tables**, not the set of data
directories: base models (backed by `data/<name>/`) **plus** derived models
(computed in the transform, no data directory — Step 3a). Both are promised in
`spec.py` and both appear in `model_tables`. Semantic views are `.model(...)`
only: no `PHYSICAL_MODELS` entry, no data directory, no physical table — so
assert dlt's output against the promised physical models, not the whole
`model_tables` map. Base attribute names are byte-exact source headers (post-dlt
snake_case); derived attribute names are the keys of the dicts your resource
yields. Separately, the **storage output port MUST be named `duckdb`**, matched
by the transform param (Step 4) — the local DuckDB driver requires it.

---

## Workflow

### Step 1 — Collect the inputs

- The intent tells you the DP `name`, description, and which questions the
  semantic layer must answer.
- The inferred model gives each base model's primary key, dimensions, joins,
  PII flags, metrics, and column types. Base roles and metric views are
  different authored objects — see Step 2.
- Each connector config names a **connector type** (CSV / other local file /
  database / REST API) plus its type-specific location. For the non-CSV types,
  follow `reference/file-source.md` / `database-source.md` / `api-source.md` —
  for database/API, confirm the user supplied real connection details; never
  invent them.
- **Read the export's shape, then land it unchanged.** For a file connector
  (CSV/JSON/JSONL/Parquet), two shapes are both NORMAL and neither is an
  anomaly:
  - **One subdirectory per model** (`<root>/<model>/*.csv`) — land each
    directory as `data/<model>/`.
  - **Flat `*.csv` files sitting at the export root** — this is one base model
    per file. The model name is the snake_cased filename without its
    extension (`Card Txns 2024.csv` → `card_txns_2024`), and the file lands at
    `data/<model>/<file>.csv` as an **EXACT BYTE COPY**. Never merge files,
    rename headers, add a column, or reshape rows to fit a tidier model set.

  Read the headers either way. Reserve **stop and surface it** for genuinely
  ambiguous shapes: nested directories more than one level deep, a directory
  mixing formats, or two files that snake_case to the same model name.
- Every data directory MUST have a base model; a promised model with **no**
  data directory is a **derived** model, computed in the transform (Step 3a) —
  not a missing export. Never invent or drop models.

### Step 1a — Plan the derivation before authoring anything

The semantic layer cannot express derivation — no expression surface on
dimensions, one aggregate over one column for metrics, no row generation or
removal. **Every business ruling therefore has to be materialized as a physical
column or row by the transform**, before the semantic layer sees it. So plan the
models by backward-chaining from the user's QUESTIONS, not forward from the
source headers. [reference/derivation-plan.md](reference/derivation-plan.md) has
the worked method, the base-vs-derived decision test, and the mandatory handling
of reference data (FX rates, category rulings — see the Invariants).

### Gate — validate primary keys before authoring

Every promised physical model, base **and** derived, needs one or more
`primary_key()` fields. The rule differs by kind:

**Base models — use an existing source column; never synthesize.** Validate
existing columns whose non-null value tuple is unique **across the complete
supplied export** (all files together). Prefer one source column; use a
composite only when it is the defensible entity key. Never use row numbers,
measures, or altered source data. If the evidence is absent, stop and ask for
the source entity/event key; a unique sample is not proof for a future export.
(This replace-only flow excludes append/upsert semantics.)

**Derived models — declare the key the derivation's grain implies.** A derived
model can exist at a grain no source column names (an amortization schedule at
invoice × month), so demanding a pre-existing source key would be wrong. Its
key is **defined by the grain** (name the grain in one sentence; the key is the
tuple identifying one row at it), **constructed deterministically** from source
values and the grain's ordinal only (a stable `f"{invoice_id}-{period:02d}"`,
never a UUID, a timestamp hash, or an order that depends on file arrival), and
**asserted unique in-transform** (Step 3b) rather than assumed. A
row-preserving enrichment or a row-removing dedupe keeps its **source** key —
those rows are still the source entities. Only a regrain declares a new
composite.

### Step 2 — `models.py`: place the inferred roles with the public DSL

Author `models.py` with the **real public semantic DSL**
(`from nxd.spec import semantic_model, field, primary_key, dimension, join`;
types from `nxd.spec.data_types`). Place the table roles, then add one semantic
view per set of metrics over that table:

- `semantic_model("<name>")` — the bare lowercase physical table name.
- `.schema({...})` mapping each column to a typed value. A role-bearing column is
  `field(<type>(), <role>())`; one with no role is the bare type
  (`"country": string()`), which still reaches the compiled schema.
- **Base models carry ONLY `primary_key()`, `dimension(...)`, or `join(...)`** —
  the DSL RAISES on a metric attached to a base-model field.
- A metric belongs on `semantic_view("<base>_metrics", <base>)` with
  `metric_field(<type>(), metric(Agg.<AGG>, of=<base>.field("<column>"), ...))` —
  a query-time model, not a physical table.

Role builders (verified DSL facts): `field(number(), primary_key())` — emit
`primary_key()`, NEVER the deprecated `grain` alias;
`field(string(), dimension(name="<concept>", pii=<flag>, description="..."))`;
`field(number(), join(to="<model>", to_column="<col>"))` — note `to=` and
`to_column=`, NOT `to_model=`.

Unannotated columns stay bare-typed (do not invent roles no question motivated).
**A dimension a ruling created MUST carry `description=` stating that ruling** —
`describe_models` is all a later consumer sees, so an unstated ruling is
invisible. No marker model: produce-verification is `.transform-complete`.

**Derived models are authored identically** — same DSL, role vocabulary, and
`.schema({...})` shape. The only differences: its schema keys are the keys of the
dicts the transform yields rather than source headers, and its `primary_key()`
may be the grain-derived composite from the Gate. Nothing in `models.py` marks a
model as derived; that distinction lives only in the transform.

Worked examples: `reference/models-example.md` (base) and
[reference/derived-models.md](reference/derived-models.md) (derived). Every
verified DSL signature used here (roles, data types, Step 3's builders) is pinned
in `reference/nxd-spec-api.md` — trust it over re-reading source.

Data-type mapping (inferred → `nxd.spec.data_types`): string → `string()`;
int / number / double / float → `number()`; bool → `boolean()`; date →
`date32()`.

### Step 3 — `transform/main.py`: the dlt-through-port ingest

The transform receives the typed **output port handle** (`DuckDbOutput`: `path`,
`schema`, `model_tables`) and connector secrets, streams each **base model's**
CSV directory through dlt, yields each **derived model's** computed rows into the
same run, then asserts the produced table names. The handle param is **`duckdb`**,
matching the port in Step 4. Declare `PHYSICAL_MODELS` from the `.promise(...)`
calls — base names first, then derived; use `duckdb.model_tables` only to resolve
those names (it can also hold `.model(...)` views with no table).

The complete `transform/main.py` template — module docstring, imports, the
source-checkout shim, the `BASE_MODELS`/`DERIVED_MODELS`/`PHYSICAL_MODELS`
tuples, the `@data_product.on_transform()` `ingest(duckdb, secrets)` body
(run-local dlt state, the per-base-model `filesystem | read_csv` reader loop, one
`pipeline.run(..., write_disposition="replace")`, the read-back-and-assert
block, the `.transform-complete` touch) and the `__main__` guard — is in
[reference/transform-template.md](reference/transform-template.md). Copy it and
fill in the model tuples.

Contract facts baked into that template — keep every one:

- The `duckdb` param MUST be typed `DuckDbOutput` — an untyped param gets a raw
  context with no `path`/`model_tables`.
- `PHYSICAL_MODELS` names exactly the models passed to `.promise(...)` — base
  and derived. Do **not** iterate `duckdb.model_tables`: it can include
  `.model(...)` views with neither `data/<view>/` nor a physical table.
- The connector config arrives in `secrets["csv_source"]` (delivered by the
  `csv-source` generic-secrets service). Never hard-code an absolute path.
- Writes go **through the port**: `dlt.destinations.duckdb(credentials=duckdb.path)`
  + `dataset_name=duckdb.schema`. NEVER a raw `duckdb.connect(...)` write, never
  `CREATE TABLE` / `CREATE VIEW` DDL, never a hardcoded staging path.
- `write_disposition="replace"` — reruns must be idempotent, not duplicating.
- The read-back-and-assert block and the `.transform-complete` touch are
  MANDATORY: the first enforces the naming invariant, the second is what the
  readiness gate polls.

### Step 3a — Derived models: computed rows through the SAME port

A **derived model** is a promised physical model with no `data/<name>/`
directory: its rows are computed in Python from the base sources and landed
through the same DuckDB output port. Every ruling the semantic layer cannot
express lives here — dedupe, amortization, normalization, classification.

**The DDL ban (Step 3) is preserved, not relaxed**: still written by dlt through
the `duckdb` port, still NO `duckdb.connect(...)` write, NO `CREATE TABLE` /
`CREATE VIEW`, NO direct file write into staging. The only new thing is where the
rows come from — a `@dlt.resource` generator instead of a CSV reader. Every
clause below is mandatory:

- **Yield plain FLAT dicts.** No pyarrow in the pinned venv, so a DataFrame
  raises — hand dlt `df.to_dict(orient="records")`. Values must be scalars: a
  nested dict or list emits a `parent__field` child table and fails the assert.
- **Same list, same run.** Append the resource to the SAME `resources` list as
  the CSV readers, landed by ONE
  `pipeline.run(resources, write_disposition="replace")` — never a second run.
- **Name it from `model_tables`** —
  `@dlt.resource(name=duckdb.model_tables["<derived>"])` — and **list it in
  `PHYSICAL_MODELS`** (via `DERIVED_MODELS`) so the read-back assert covers it.
  A derived model absent from that tuple is an unasserted table.
- **Read the sources yourself** with stdlib `csv` and `sorted()` over the glob:
  dlt's reader streams to the destination and cannot hand rows back to Python.
- **Deterministic.** No `now()`, no `today()`, no unseeded random, no
  set/dict-iteration order leaking into output: a rerun over the same export
  must produce byte-identical rows.
- **Confined to the fixed venv** — `pandas`, `duckdb`, stdlib only. The closure's
  `requirements.txt` is **never installed at runtime**, so a new import is an
  import error at run time.

### Step 3b — In-memory asserts: the only durable data-quality check

**Desktop has no other execution point for data quality.** The local storage
driver's verify is a no-op and contract verification runs only platform-side, so
an assert inside the transform is the whole quality story — and it runs over the
complete derived set before the rows are yielded, failing the run **before
anything is promoted**. Write one assert helper per derived model, invoked
between deriving the rows and yielding them. Make each an **invariant over the
source-vs-derived relationship** — a claim that could be false if the derivation
were wrong; restating the transform's own arithmetic proves nothing. **These are
mandatory tiers, not a menu to pick the convenient one from:**

- **Tier 1 — every derived model, always:** (a) the **declared key is unique**
  over the complete derived set, and (b) the **row count computed from the
  grain** matches source rows **read independently** from the base CSVs.
- **Tier 2 — additionally, whenever the model carries a MEASURE column** (any
  amount/quantity a metric will aggregate): the **signed measure total must
  reconcile** against the signed total read independently from the base CSVs,
  with **every intentional divergence itemized as its own named term**
  (`- refund_pairs_total`, `- transfer_rows_total`). Use `Decimal`, and
  reconcile **per source currency BEFORE any FX conversion**.

An itemized exclusion means the derivation **removes** rows or value rather than
enriching — reclassify it as a removal and apply the removal invariants too.
Classification totality is never sufficient alone: it can pass while every
monetary answer is overstated. Raise `RuntimeError` carrying the
actual-vs-expected numbers; the run log is the whole diagnostic.

Worked code for both steps is in
[reference/derived-models.md](reference/derived-models.md).

**Other connector types**: Step 3 is identical except the `readers=[...]` body
and `secrets[...]` key — take those from `reference/` (`file-source.md`,
`database-source.md`, `api-source.md`). Steps 3a/3b are connector-independent.

### Step 4 — `spec.py`: promises + transform + the `duckdb` output port

`spec.py` is the author-facing source of truth the supervisor compiles into
the deployment YAML: it declares the infra profile, wires the transform to
compute, promises every physical model — base and derived — on the DuckDB
port, and registers each query-time view. Bind the three service references by
relative infra-profile path (resolved against `infra-profile.yaml`, Step 5).
The worked `spec.py` is in
[reference/models-example.md](reference/models-example.md).

Contract facts baked into that shape — keep every one:

- **The output port is named `duckdb`** (`.port("duckdb", storage(...))`) — the
  local DuckDB storage driver requires that exact name, and the transform param
  matches it (Step 3). Never `"output"`.
- **`infra_profile="desktop-local"`** on `data_product(...)`, matching
  `infra-profile.yaml`'s `metadata.name`.
- **`script("transform/main.py")`**, not `code(transform)` — the desktop
  transform is a standalone entrypoint the compute driver executes; it registers
  itself via `@data_product.on_transform()`. `.compute(...)` binds
  `python-compute`; `.secrets([...])` delivers the connector config as the
  transform's `secrets` dict.
- Promise exactly the landed physical models — **base and derived alike**; that
  is what puts them in `model_tables`. Register every metric view via
  `.model(view)`, never `.promise(view)`: a view is query-time only and is not
  written by the transform.
- **No `.semantic_tools(...)`.** The supervisor's semantic child builds the MCP
  catalog from the compiled model roles, and the proven closure serves all four
  tools without it. `.semantic_tools()` emits a kernel RPC port needing a live
  RPC driver — a k8s artifact with no local equivalent: a port nothing serves.

**Other connector types**: only the variable name and service path change; for 2+
of one type, `.secrets([...])` takes one labeled variable per instance
(`reference/multi-source.md`).

### Step 5 — `infra-profile.yaml`: the desktop-local profile (emitted prerequisite)

The desktop closure ships its own infra profile declaring the three local
services the spec references (`duckdb`, `python-compute`, `csv-source`). Emit it
**verbatim** from [reference/infra-profile.md](reference/infra-profile.md);
`metadata.name` is `desktop-local` and MUST match `infra_profile=` in `spec.py`.
The `generic-secrets` `csv-source` service delivers the **relative**
`csv-source-path` (an absolute path escapes the pinned snapshot and fails) into
`secrets[...]`.

**Other connector types**: only the third service's *name* changes, per the
connector-types table (Overview). `csv-source`/`file-source` carry no credential
(`attributes: []`); `db-source`/`api-source` populate that service's `attributes`
with the real credential instead — `reference/database-source.md` /
`api-source.md`. For 2+ of one type, one service per instance
(`reference/multi-source.md`). Derived models change neither file.

### Step 6 — `requirements.txt`: the proven pins

```
nxd.data_product[spec]
dlt[duckdb]==1.28.2
duckdb==1.5.4
pandas==2.3.3
```

`dlt[duckdb]==1.28.2` + `duckdb==1.5.4` are the pins proven against the S0
supervisor — do not float them. `pandas` is required by dlt's `read_csv`
transformer. Python `>=3.12,<3.13` is the proven interpreter range. **Other
connector types add to these pins, never replace them** — see `reference/` for
the per-type additions (Parquet extra, `dlt[sql_database]` + one vendor driver,
or none for REST API).

### Step 7 — Self-check before handing off (MANDATORY)

Confirm the `duckdb` port/parameter pair and no `.semantic_tools(...)`. Walk the
naming invariant (`models.py` == `.promise` == `PHYSICAL_MODELS` ==
`main.<name>`), then separately confirm `BASE_MODELS` — and only `BASE_MODELS` —
matches the connector's per-model references (the `data/` directories). Derived
models and `.model(...)` views both lack one for different reasons: the first is
written by the transform, the second is never written at all. Confirm the
supplied export is unchanged, then run
[reference/self-check.md](reference/self-check.md): it dry-runs the transform
against a scratch DuckDB **and structurally validates `models.py`/`spec.py`
against the pinned DSL surface** (it parses, does not import — no `nxd` wheel is
installable here). Read the `unverified:` lines it prints: those entries were not
checked at all.

Reading a failure: if the read-back assert fires or an unquoted `main.<name>`
query fails, a name diverged — fix the NAME (in `models.py`, `.promise`,
`PHYSICAL_MODELS`, and `data/<name>/` for base models), never quote around it.
If a derived model's reconciliation assert (Step 3b) fires, the derivation is
wrong — fix the LOGIC, never loosen the assert.

**Database/API connectors need live credentials to dry-run.** With
credentials, run each type's own connectivity check exactly as its reference
doc specifies — `database-source.md`'s asserts `row_count > 0` per model;
`api-source.md`'s asserts a parseable response per resource — never an exact
fixture count either way. Without credentials, report the connectivity
self-check as **not run** — never claim it passed.

---
## Invariants — NEVER violate these

- **Python-only closure**: emit `spec.py` + `models.py` + `infra-profile.yaml` + `transform/main.py` + `requirements.txt` + the connector-type-specific companion artifact (see the connector-types table in Overview). NEVER hand-write `deployment-spec.yaml` / `manifest.yaml` / `models.yaml` — the supervisor compiles those from the Python at pin time.
- **The naming invariant**: each physical model name == `models.py` `semantic_model` arg == `spec.py` `.promise` == `PHYSICAL_MODELS` == `main.<name>`, unquoted lowercase snake_case; additionally `==` the connector's per-model reference (`data/<name>/`, see "THE NAMING INVARIANT" table) for base models only. `PHYSICAL_MODELS` is landed tables (base + derived), NOT the `data/` listing. Semantic views are `.model(...)` only and have no physical table. The transform's read-back assert is the runtime tripwire — keep it.
- **Output port named `duckdb`**: `.port("duckdb", storage(...))`, transform param `duckdb` typed `DuckDbOutput` (port name == param name). The local DuckDB driver requires exactly this name.
- **Through the port, always**: dlt destination is `duckdb.path` / `duckdb.schema`. No raw `duckdb.connect` writes, no view/table DDL, no direct file writes into staging. **Derived models do not relax this** — they reach the port as `@dlt.resource` generators in the same `pipeline.run(...)`, not as DDL.
- **Derived models are flat, deterministic, and in-run** (Step 3a): plain scalar dicts (no DataFrame — no pyarrow in the fixed venv; no nested values — they spawn `parent__field` child tables), appended to the SAME `resources` list, landed in ONE `pipeline.run(..., write_disposition="replace")`, named from `duckdb.model_tables`, listed in `PHYSICAL_MODELS`. Read the sources yourself with stdlib `csv`. No `now()`, no unseeded random, sorted inputs. Imports confined to pandas / duckdb / stdlib.
- **Every derived model carries mandatory in-memory asserts** (Step 3b): Tier 1 always — declared-key uniqueness plus a grain-derived row count against independently-read source rows; Tier 2 whenever a measure column is present — a signed measure total reconciled per currency pre-FX in `Decimal`, every exclusion itemized as a named term. Raised with actual-vs-expected before the rows are yielded. It is the ONLY durable data-quality gate on desktop. Never restate the transform's arithmetic as an assert, never substitute a weaker invariant for the measure reconciliation, and never loosen one to make a run pass.
- **No `.semantic_tools(...)`**: the supervisor's semantic child builds the catalog from compiled semantic roles; the spec must not emit an RPC port.
- **Public semantic DSL only**: base models carry `primary_key` / `dimension` / `join`; metrics are `metric_field(metric(...))` on `semantic_view(...)`. Never import private modules or write metadata directly.
- **Validated keys, by kind**: every promised physical model has one or more `primary_key()` fields. A **base** model's key is one or more EXISTING source columns whose tuple is non-null and unique across the supplied export — never synthesize one; stop and ask for the source key when that evidence is absent. A **derived** model's key is defined by the derivation's grain, constructed deterministically from source values plus the grain's ordinal, and proven unique by an in-transform assert. A dedupe keeps its source key; only a regrain declares a new composite.
- **Connector via secrets, `infra-profile.yaml` shape**: source config only from `secrets[...]`, keyed per connector type per the connector-types table in Overview, one entry per source instance (labeled when 2+ of a type — `reference/multi-source.md`) — always delivered via `.secrets([...])` on the transform. The profile is `metadata.name: desktop-local` with at least three services (`duckdb`, `python-compute`, one connector service per source instance). `duckdb`, `python-compute`, `csv-source`, and `file-source` keep `attributes: []` (their companion path file is relative); `db-source`/`api-source` (and their labeled variants) carry one `{"key": ..., "value": ..., "public": false}` attribute per real credential field instead — see `reference/database-source.md` / `reference/api-source.md`. Never fabricate a credential, never narrate one in chat, never write a raw database password or API token into a committed closure file, and never let two same-type instances share a name.
- **Run-local dlt state** (`pipelines_dir` under the run dir + `DLT_DATA_DIR` set; never `~/.dlt`); **`write_disposition="replace"`**; **`.transform-complete` touch** after the assert.
- **Place, don't redesign**: semantic roles come from nxd-semantic-data-product. Preserve a file connector's supplied export exactly, and treat a database or API connector as read-only — cleaning, dedupe, reclassification and regrain happen ONLY in derived models downstream of pristine sources, never by editing the source export. Use an existing validated key for base models or surface the missing-key problem. Promise base and derived models, register metric views with `.model(...)`, and add no marker model on desktop.
- **Reference data is landed, never hardcoded**: FX rates, merchant→category rulings, account mappings and similar judgements that exist in no source data are user-confirmed and landed as their own model, so they stay queryable and reviewable. Never bake them into transform code as a constant dict or an `if` ladder. With no user available to confirm, land the mapping anyway as PROPOSED, recorded as a row in the closure's landed `nxd_decisions` model — never a `DECISIONS.md` file — see [reference/derivation-plan.md](reference/derivation-plan.md).
- **Proven pins**: `dlt[duckdb]==1.28.2`, `duckdb==1.5.4`, pandas, the nxd wheel; Python `>=3.12,<3.13`.

## Related skills

| Skill | Relationship |
|---|---|
| `nxd-semantic-data-product` | Produces the inferred semantic model this skill places; owns the role grammar and the k8s `.semantic_tools()` topology |
| `nxd-data-product-builder` | The k8s/cloud DP authoring path (Snowflake et al.) — use it, not this skill, off-desktop |

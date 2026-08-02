---
name: nxd-generate-dp
description: CONSTRUCTION SPECIALIST, not an entry point. Generates the COMPLETE runnable Python-only data-product closure for lean-desktop Nextdata OS from an ALREADY-SETTLED plan (intent, inferred model, connector config): spec.py + models.py + infra-profile.yaml + transform/main.py + requirements + the connector artifact (local file, live database, or REST API), ready to boot into a queryable DuckDB result. Supervisor compiles spec.py into the kernel definition YAML, so never hand-write deployment-spec / manifest / models YAML. Use when the plan is settled and the closure needs constructing. End-to-end requests to build a data product from a source start in nxd-pocket-loop, which gathers intent, source, questions and any supplied procedure and runs the policy read-back FIRST; arriving here directly means that handoff is absent, so return to nxd-pocket-loop before any read-back or materialization. Pairs with nxd-semantic-data-product, which INFERS the model this skill PLACES. Not for k8s — use nxd-data-product-builder.
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
  version: 0.30.1
---

# nxd-generate-dp skill

## Overview

This skill assembles the **complete Python-only definition closure** for a local
(desktop) data product from: the **approved `dp-spec.md`** — the user-editable IR
carrying intent, questions, the model plan and every ruling, which this skill
*compiles*, never re-derives; the **inferred semantic model** — the per-column
roles produced by **nxd-semantic-data-product**'s inference mode, which this
skill *places*, never redesigns; and the **connector config(s)** naming where
each source lives and its **connector type** (never invent connection details or
credentials).

**If the intent carries a procedure** — a rubric, gates, thresholds, a verdict
vocabulary — the Workflow's **policy read-back gate** runs before any file is
written. A closure whose scoring policy the user never saw is the one failure
this skill treats as unrecoverable.

**Connector types at a glance** — the canonical mapping; every other mention below points back here. Names are for exactly one instance of a type; for 2+, label each per `reference/multi-source.md`.

| Type | Service | `secrets[...]` key | Companion artifact |
|---|---|---|---|
| CSV (proven, fully-inlined default below) | `csv-source` | `csv_source` | `csv-source-path` + `data/` |
| Other file (JSON/JSONL/Parquet) — `reference/file-source.md` | `file-source` | `file_source` | `file-source-path` + `data/` |
| Database — `reference/database-source.md` | `db-source` | `db_source` | `db-source-tables`, no `data/` |
| REST API — `reference/api-source.md` | `api-source` | `api_source` | `api-source-endpoints`, no `data/` |

The output is a directory the **desktop supervisor** compiles, pins, boots, and
publishes: it **compiles `spec.py` into the kernel definition YAML at create
time**, runs the transform, verifies staging, and stands up the semantic MCP
endpoint over it.

## The closure layout

The author emits **Python and prerequisite config only**:

```
…/nxd-pocket/<workflow>/
├── dp-spec.md             # the approved IR — INPUT, outside the closure. Never emitted here.
└── closure/               # <dp-root>: what build_data_product receives
    ├── spec.py            # author-facing definition: promises + transform + output port
    ├── models.py          # semantic models + placed semantic roles
    ├── infra-profile.yaml # the desktop-local profile: duckdb + python-compute + csv-source
    ├── transform/
    │   └── main.py        # the dlt-through-port ingest (standalone entrypoint)
    ├── requirements.txt   # proven pins (below)
    ├── dp-spec.approved.md # Step 6a: byte copy of the approved IR
    ├── dp-spec.lock.json  # its canonical hash + compiler version
    ├── build-record.json  # generated: stages, attempts, concessions, blockers
    ├── README.md          # generated: reopen recipe + credentials block ONLY
    ├── csv-source-path    # one line: relative path to the CSV export root
    └── data/              # the connector export: data/<base_model>/*.csv
        └── <base_model>/… # base models only — derived models have no data dir
```
_(CSV layout, the proven default; other types swap the companion artifact per the Overview connector-types table.)_

**The author NEVER writes `deployment-spec.yaml`, `manifest.yaml`, or
`models.yaml`.** The supervisor compiles those three from `spec.py` +
`models.py` when it pins the DP — including the `model_tables` identity map, the
staging-path placeholder, and the compiled semantic roles the semantic child
reads. It owns their shape and will overwrite them; your source of truth is the
Python.

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

`PHYSICAL_MODELS` is the set of **landed tables**, not data directories: base
models (backed by `data/<name>/`) **plus** derived models (Step 3a, no data
directory). Both are promised and both appear in `model_tables`. Semantic views
are `.model(...)` only — no `PHYSICAL_MODELS` entry, no data directory, no table
— so assert dlt's output against the promised physical models, not the whole
`model_tables` map. Base attribute names are byte-exact source headers (post-dlt
snake_case); derived ones are the keys your resource yields.

## Workflow

The nxd-pocket-loop handoff MUST carry `pocket_helper_dir`, an already-resolved absolute installed-skill directory. Set `POCKET_HELPER_DIR` to that exact value;
if it is absent, return to nxd-pocket-loop — never reconstruct it from the
closure or this skill's cwd.

**Selective-install dependency:** this skill needs **nxd-pocket-loop** at runtime for the approved-spec validator, lock writer, and build-record helpers. A selective install must include both skills; installing `nxd-generate-dp` alone is not a supported substitute for that handoff.

### Step 1 — Collect the inputs

- **The approved `dp-spec.md`** is the primary input when one exists — the
  user-editable IR **nxd-pocket-loop** authors at its Step 1b, beside the closure
  at `…/nxd-pocket/<workflow>/dp-spec.md`. **Compile it; do not re-derive it**:
  its `models:` block is the Step-1a plan, `criteria:`/`verdicts:` are the landed
  rubric models, and `decisions:` is `data/nxd_decisions/nxd_decisions.csv` row
  for row with `provenance` **copied, never recomputed**. Re-run
  `"$POCKET_HELPER_DIR/scripts/validate_dp_spec.py"` before authoring — a spec that fails is not a
  settled plan — and treat any closure value appearing in no spec section as one
  the user never approved. Schema and compile map: **nxd-pocket-loop**'s
  `reference/dp-spec.md`. **Never write it into the closure**: it is upstream,
  and a closure file pointing at `../dp-spec.md` is the escaping reference Phase
  C fails; the approved revision is byte-copied in as `dp-spec.approved.md` under
  a lock at Step 6a.
- The intent (the spec's `name` / `intent` / `questions`) gives the DP `name`,
  description, and which questions the semantic layer must answer.
- The inferred model gives each base model's primary key, dimensions, joins,
  PII flags, metrics, and column types. Base roles and metric views are
  different authored objects — see Step 2.
- Each connector config names a **connector type** (CSV / other local file /
  database / REST API) plus its location. For non-CSV types follow
  `reference/file-source.md` / `database-source.md` / `api-source.md`; for
  database/API confirm real connection details — never invent them (the spec
  names credential KEYS only; the values reach you separately).
- **Read the export's shape, then land it unchanged** — landing happens only
  after the policy gate below. Two file-connector shapes are NORMAL: **one
  subdirectory per model** (`<root>/<model>/*.csv` → `data/<model>/`), or **flat
  `*.csv` at the export root** (one base model per file, named from the
  snake_cased filename, landed as an **EXACT BYTE COPY**) — full rules and the
  ambiguous shapes that mean stop-and-surface are in
  [reference/file-source.md](reference/file-source.md). Never merge, rename
  headers, add a column, or reshape rows; read the headers either way.
- Every data directory MUST have a base model; a promised model with **no** data
  directory is a **derived** model (Step 3a), not a missing export.

### Gate — policy read-back before ANY materialization

**Fires when** the request supplies a procedure (rubric, gates, weights,
thresholds, scales, a verdict vocabulary, a selection rule) with a gap changing
a score, verdict, gate outcome, or which rows land: a scale defining only some
levels (5 and 1 given, 2/3/4 absent); named verdicts with no score→verdict
mapping or precedence; a qualitative modifier that must become a rule ("unless
exceptional"); a gate whose UNKNOWN/missing/inferred value could change the
outcome; evidence with no provenance or missing-evidence rule.

**Then, until the user replies, do NOT**: create the closure directory, copy
source data into it, write any closure file, generate transform code, create
tables, score rows, or invoke a build. Reading the source and its headers is
allowed, as is writing `dp-spec.md` itself — it lives OUTSIDE the closure, so it
is not a materialization. Asking technical delivery questions is allowed and
**does not satisfy this gate**; a delivery answer is not policy approval, and
your own recommended defaults are not a reason to proceed.

**The read-back artifact is `dp-spec.md`**, validated with
`"$POCKET_HELPER_DIR/scripts/validate_dp_spec.py"`, which finds those gap classes deterministically.
It must ENUMERATE every gate with its UNKNOWN handling, every criterion weight,
**every anchor you propose for an incomplete scale**, the score aggregation, the
**proposed verdict bands and precedence**, and the provenance and
missing-evidence behaviour — never a summary of a procedure the user must check.
Show it, name every value you authored, and wait. A validator pass is not
approval, and `status: approved` is the user's to set.

**"Use your judgement" is not approval** — it licenses authoring the proposal,
then showing it and waiting again. A fully specified procedure still gets one
short confirming turn; no procedure at all means this gate does not fire.

**Invoked directly**, without an nxd-pocket-loop handoff, **return to
nxd-pocket-loop immediately**. Do not run the read-back, materialize a closure, or serve; nxd-pocket-loop owns the user-facing read-back and approval.
**Invoked as a generation subagent**, the user turn is the
orchestrator's and you never open one, and the gate is **not a rubber stamp**:
re-run the "fires when" criteria and **bounce** (`gap_found: <what and why>`,
writing nothing) on an element absent from the enumeration, or one a profiling
finding makes ambiguous or conditional. You hold no credential — placeholder
the `attributes`, return `credential_slots` (key names only), dry-run **not run**.

The complete gate — every clause, the subagent return contract, and the
credential boundary — is [reference/policy-gate.md](reference/policy-gate.md).

### Step 1a — Plan the derivation before authoring anything

The semantic layer used here cannot express derivation — no dimension
expressions, no default filters, no row generation/removal, and no
`Agg.EXPRESSION` shortcut for business rulings. **Every business ruling
therefore has to be materialized as a physical column or row by the transform**,
before the semantic layer sees it. So plan the models by backward-chaining from
the user's QUESTIONS, not forward from the source headers — **an approved
`dp-spec.md`'s `models:` block IS this plan**, already backward-chained and
approved: validate it, don't redo it.
[reference/derivation-plan.md](reference/derivation-plan.md) has the worked
method, base-vs-derived test, `Agg.EXPRESSION` boundary, and mandatory
reference-data handling, including per-entity **agent** judgements —
[reference/llm-judgments.md](reference/llm-judgments.md).

### Gate — validate primary keys before authoring

Every promised physical model, base **and** derived, needs one or more
`primary_key()` fields. A `dp-spec.md` states each model's `grain` and `key` —
**validate those against the source rather than inventing your own**; a spec key
that does not hold is a `gap_found`, not something to quietly replace. The rule
differs by kind:

**Base models — use an existing source column; never synthesize.** Validate
existing columns whose non-null value tuple is unique **across the complete
supplied export** (all files together). Prefer one source column; use a
composite only when it is the defensible entity key. Never use row numbers,
measures, or altered source data. If the evidence is absent, stop and ask for
the source entity/event key; a unique sample is not proof for a future export.
(This replace-only flow excludes append/upsert semantics.)

**Derived models — declare the key the derivation's grain implies.** A derived
model can exist at a grain no source column names (an amortization schedule at
invoice × month), so demanding a pre-existing source key would be wrong. Its key
is **defined by the grain**, **constructed deterministically** from source values
and the grain's ordinal only (a stable `f"{invoice_id}-{period:02d}"`, never a
UUID, a timestamp hash, or an order depending on file arrival), and **asserted
unique in-transform** (Step 3b) rather than assumed. A row-preserving enrichment
or a row-removing dedupe keeps its **source** key — those rows are still the
source entities. Only a regrain declares a new composite.

### Step 2 — `models.py`: place the inferred roles with the public DSL

Author `models.py` with the **real public semantic DSL**
(`from nxd.spec import semantic_model, field, primary_key, dimension, join`;
types from `nxd.spec.data_types`). Place the table roles, then one semantic view
per set of metrics over that table:

- `semantic_model("<name>")` — the bare lowercase physical table name.
- `.schema({...})` maps each column to `field(<type>(), <role>())`. A column with no role
  produces no metric, dimension or join and is absent from `describe_models` — unqueryable.
- **Base models carry ONLY `primary_key()`, `dimension(...)`, or `join(...)`** —
  the DSL RAISES on a metric attached to a base-model field.
- A metric belongs on `semantic_view("<base>_metrics", <base>)` with
  `metric_field(<type>(), metric(Agg.<AGG>, of=<base>.field("<column>"), ...))` —
  query-time, not a physical table.

Role builders: `field(number(), primary_key())` — never the deprecated `grain`;
`field(string(), dimension(name=..., description=..., pii=<flag>))`; `field(number(), join(to="<model>", to_column="<col>"))` — `to=`, NOT `to_model=`.

**Every field takes a role, except a measure a metric aggregates. Dimensions
and metrics also take a description; `primary_key()`/`join()` have none. Every
`semantic_model` takes a `.description(...)`.** `describe_models` is all a later
consumer sees, so a bare column is invisible and a bare name unusable. Put the
description INSIDE the role — on `field()`/`metric_field()` it never reaches
the agent. A dimension a **ruling** created must state that ruling. Metrics
stay question-driven: a numeric no question aggregates is a `number` dimension.
No marker model: produce-verification is `.transform-complete`.

**Derived models are authored identically** — same DSL, role vocabulary and
`.schema({...})` shape; only their schema keys (the transform's yielded dict
keys, not source headers) and possibly a grain-derived composite
`primary_key()` differ. Nothing in `models.py` marks a model as derived.

Worked examples: `reference/models-example.md` (base) and
[reference/derived-models.md](reference/derived-models.md) (derived). Every
verified DSL signature and the inferred→`nxd.spec.data_types` mapping are pinned
in `reference/nxd-spec-api.md` — trust it over re-reading source.

### Step 3 — `transform/main.py`: the dlt-through-port ingest

The transform receives the typed **output port handle** (`DuckDbOutput`: `path`,
`schema`, `model_tables`) and connector secrets, streams each **base model's**
CSV directory through dlt, yields each **derived model's** computed rows into the
same run, then asserts the produced table names. The handle param is **`duckdb`**,
matching the port in Step 4. Declare `PHYSICAL_MODELS` from the `.promise(...)`
calls — base names first, then derived; use `duckdb.model_tables` only to resolve
those names (it can also hold `.model(...)` views with no table).

The complete `transform/main.py` template — docstring, imports, source-checkout shim, the
`BASE_MODELS`/`DERIVED_MODELS`/`PHYSICAL_MODELS` tuples, the `@data_product.on_transform()`
`ingest(duckdb, secrets)` body (run-local dlt state, the per-base-model
`filesystem | read_csv` reader loop, one `pipeline.run(..., write_disposition="replace")`,
the read-back-and-assert block, the `.transform-complete` touch) and the `__main__` guard —
is in [reference/transform-template.md](reference/transform-template.md).

Contract facts baked into that template — keep every one (each is restated in
the Invariants, where the full reasoning lives):

- The `duckdb` param MUST be typed `DuckDbOutput` — an untyped param gets a raw
  context with no `path`/`model_tables`.
- `PHYSICAL_MODELS` names exactly the models passed to `.promise(...)` — base
  and derived. Do **not** iterate `duckdb.model_tables`: it can include
  `.model(...)` views with neither `data/<view>/` nor a physical table.
- The connector config arrives in `secrets["csv_source"]`; never hard-code an
  absolute path. Writes go **through the port**
  (`dlt.destinations.duckdb(credentials=duckdb.path)` + `dataset_name=duckdb.schema`),
  never raw `duckdb.connect(...)`, DDL, or a hardcoded staging path.
- `write_disposition="replace"` — reruns must be idempotent, not duplicating. An
  append-only source goes incremental ONLY via
  [reference/incremental-transforms.md](reference/incremental-transforms.md).
- The read-back-and-assert block and the `.transform-complete` touch are
  MANDATORY: the first enforces the naming invariant, the second is what the
  readiness gate polls.

### Step 3a — Derived models: computed rows through the SAME port

A **derived model** is a promised physical model with no `data/<name>/`
directory: rows computed in Python from the base sources, landed through the same
port. Every ruling the semantic layer cannot express lives here — dedupe,
amortization, normalization, classification.

**The DDL ban (Step 3) is preserved, not relaxed**: still written by dlt through
the `duckdb` port, still NO `duckdb.connect(...)` write, NO `CREATE TABLE` /
`CREATE VIEW`, NO direct file write into staging. The only new thing is where the
rows come from — a `@dlt.resource` generator instead of a CSV reader. Every
clause below is mandatory and each is restated in the Invariants:

- **Yield plain FLAT dicts** — no pyarrow in the pinned venv, so a DataFrame
  raises (`df.to_dict(orient="records")`), and a nested value spawns a
  `parent__field` child table that fails the assert.
- **Same list, same run** — appended to the SAME `resources` list as the CSV
  readers, landed by ONE `pipeline.run(..., write_disposition="replace")`.
- **Named from `model_tables`** (`@dlt.resource(name=duckdb.model_tables["<derived>"])`)
  and listed in `PHYSICAL_MODELS` via `DERIVED_MODELS`.
- **Read the sources yourself** with stdlib `csv` and `sorted()` over the glob:
  dlt's reader streams to the destination and cannot hand rows back to Python.
- **Deterministic**, and confined to the fixed venv (`pandas`, `duckdb`, stdlib);
  `requirements.txt` is **never installed at runtime**.

### Step 3b — In-memory asserts: the durable derived-row check

**Transform asserts are the durable derived-row check; custom contracts never
replace them.** A contract states what the **user guaranteed**; an assert proves
what the **transform produced**. One helper per derived model, invoked between
deriving and yielding, each an **invariant over the source-vs-derived
relationship** — the thing no verifier sees — over the complete derived set
before rows are yielded. Restating the transform's own arithmetic proves
nothing. **Mandatory tiers:**

- **Tier 1 — every derived model, always:** (a) the **declared key is unique**
  over the complete derived set, and (b) the **row count computed from the
  grain** matches source rows **read independently** from the base CSVs.
- **Tier 2 — whenever the model carries a MEASURE column:** the **signed measure
  total must reconcile** against the signed total read independently from the
  base CSVs, **every intentional divergence itemized as its own named term**
  (`- refund_pairs_total`), in `Decimal`, **per source currency BEFORE any FX
  conversion**.

Raise `RuntimeError` carrying actual-vs-expected. An itemized exclusion means a
**removal**, not an enrichment, and carries extra invariants; classification
totality alone can pass while every monetary answer is overstated — both, with
worked code, in [reference/derived-models.md](reference/derived-models.md).

**Other connector types**: Step 3 is identical except the `readers=[...]` body
and `secrets[...]` key — take those from `reference/` (`file-source.md`,
`database-source.md`, `api-source.md`). Steps 3a/3b are connector-independent.

### Step 4 — `spec.py`: promises + transform + the `duckdb` output port

`spec.py` is the author-facing source of truth the supervisor compiles into the
deployment YAML: it declares the infra profile, wires the transform to compute,
promises every physical model — base and derived — on the DuckDB port, and
registers each query-time view. Bind the three service references by relative
infra-profile path (resolved against `infra-profile.yaml`, Step 5). A spec
declaring `## expectations` / `## promises` wires each one here too
([reference/custom-contracts.md](reference/custom-contracts.md)); worked
`spec.py`: [reference/models-example.md](reference/models-example.md).

Contract facts baked into that shape — keep every one:

- **The output port is named `duckdb`** (`.port("duckdb", storage(...))`, never
  `"output"`) matched by the transform param (Step 3), and
  **`infra_profile="desktop-local"`** on `data_product(...)` matches
  `infra-profile.yaml`'s `metadata.name`.
- **`script("transform/main.py")`**, not `code(transform)` — the standalone
  entrypoint the compute driver executes, registering itself via
  `@data_product.on_transform()`. `.compute(...)` binds `python-compute`;
  `.secrets([...])` delivers the connector config as the transform's `secrets`.
- Promise exactly the landed physical models — **base and derived alike**; that
  is what puts them in `model_tables`. Register every metric view via
  `.model(view)`, never `.promise(view)`: a view is query-time only, not written
  by the transform.
- **No `.semantic_tools(...)`.** The supervisor's semantic child builds the MCP
  catalog from compiled model roles, and the proven closure serves all four tools
  without it. `.semantic_tools()` emits a kernel RPC port needing a live RPC
  driver — a k8s artifact with no local equivalent: a port nothing serves.

**Other connector types**: only the variable name and service path change; for
2+ of one type, `.secrets([...])` takes one labeled variable per instance
(`reference/multi-source.md`).

### Step 5 — `infra-profile.yaml`: the desktop-local profile (emitted prerequisite)

The desktop closure ships its own infra profile declaring the three local
services the spec references (`duckdb`, `python-compute`, `csv-source`). Emit it
**verbatim** from [reference/infra-profile.md](reference/infra-profile.md);
`metadata.name` is `desktop-local` and MUST match `infra_profile=` in `spec.py`.
The `csv-source` service (driver `nxd:local/file/storage:0.1.0`) delivers the
**relative** `csv-source-path` into `secrets[...]` (an absolute path escapes the
pinned snapshot and fails).

**Other connector types** change only the third service's name and its
`attributes` — the rules, and what derived models do not change, are in
[reference/infra-profile.md](reference/infra-profile.md).

### Step 6 — `requirements.txt`: the proven pins

```
nxd.data_product[spec]
dlt[duckdb]==1.28.2
duckdb==1.5.4
pandas==2.3.3
```

`dlt[duckdb]==1.28.2` + `duckdb==1.5.4` are proven against the S0 supervisor — do
not float them; `pandas` is required by dlt's `read_csv`; Python `>=3.12,<3.13`.
**Other connector types add to these pins, never replace them** — `reference/` has
the per-type additions (Parquet extra, `dlt[sql_database]` + a vendor driver, or none).

### Step 6a — Snapshot the approved spec, open the build record (MANDATORY)

The closure carries a queryable data product but **not** the plan behind it, and a
cold reader has only the closure. So after approval — and only after — the approved
spec is **byte-copied in** and hashed, beside a generated record of what the build
did. Preconditions, procedure, and the `README.md` and `contracts/<name>.md` templates: [reference/closure-record.md](reference/closure-record.md).

1. `cp <workflow>/dp-spec.md <closure>/dp-spec.approved.md`, **byte-identical** and
   never re-serialized — the snapshot is evidence; requires `status: approved` and
   a validator pass. Mirror every `judgments[].prompt_ref` in at the same relative
   path; an absolute or `../`-rooted ref blocks generation.
2. `python3 "$POCKET_HELPER_DIR/scripts/dp_diagnostics.py" lock write <spec.md> <closure>` → `dp-spec.lock.json`, then `python3 "$POCKET_HELPER_DIR/scripts/dp_diagnostics.py" record init --record <closure>/build-record.json --lock <closure>/dp-spec.lock.json`, before Step 7 reads the record.
3. Render `README.md`: the reopen recipe plus, only for a credentialed source, the
   credentials block. No plan sections, no outcomes.

Self-containment is now a **hash-checkable snapshot**, not a copy-never-point
discipline, and `build-record.json` is **generated, never hand-authored**: outcomes
— row counts, blockers, review rounds, concessions — are a pure product of the build
and never go back into the IR. Neither replaces the machine-enforced surfaces:
rulings still land as data (`nxd_decisions`, carrying both `status` and
`provenance`) and the Step-3b asserts still run.

### Step 7 — Self-check before handing off (MANDATORY)

**Step 6b, only when `nxd-review-closure` is installed**: explicitly dispatch one built-in read-only reviewer — never a custom/plugin agent definition — with the closure path and verbatim request, to return claims only; it never edits, builds, serves, transforms, or talks to the user. The dispatcher enforces 120 seconds, then records every returned claim (or terminal `timed_out` round) in `build-record.json` `review_rounds[]` and adjudicates it with a citation. `accepted` means *verified*, never *authorized to change*. Relay every claim, including rejected/out-of-scope ones, to the user with its effect and adjudication. A review finding defaults to behavior-affecting: pause as `needs_user` and apply only explicitly approved IDs. Only a syntax, mechanical, or procedural `structural_note` with evidence that the spec hash, models, grain, rows, values, aggregation, thresholds, verdicts and assertions are unchanged may self-heal. A timeout with partial claims is relayed the same way; continuing without a completed review is an explicit user decision. Contract: [reference/adversarial-review.md](reference/adversarial-review.md).
Then the self-check itself. Confirm the `duckdb` port/parameter pair and no `.semantic_tools(...)`. Walk the
naming invariant (`models.py` == `.promise` == `PHYSICAL_MODELS` ==
`main.<name>`), then separately confirm `BASE_MODELS` — and only `BASE_MODELS` —
matches the `data/` directories (derived models and `.model(...)` views have no
`data/`: the first is transform-written, the second never landed). **When a
`dp-spec.md` governed the build, confirm shipped-matches-approved**: every
promised model, gate, weight, band and `nxd_decisions` row traces to a spec
section, and none carries a value the spec does not. Confirm the
supplied export is unchanged, then run BOTH the self-check and the lock verify. **The self-check is not shipped as an executable file — write it into the closure first**: copy the single `# self_check.py` python fence out of [reference/self-check.md](reference/self-check.md) verbatim to `<closure>/self_check.py`, then run it **from the closure root** (it resolves `models.py`, `spec.py`, `transform/` and `data/` against its own working directory, so running it elsewhere reports `CANNOT READ`). Skipping this copy leaves nothing to execute, and the reach gate silently never runs. So: `cd <closure> && python3 self_check.py --json --record build-record.json`, then `python3 "$POCKET_HELPER_DIR/scripts/dp_diagnostics.py" lock verify <closure>` — the second is the canonical-hash check the first defers. The self-check dry-runs the transform
against a scratch DuckDB, **structurally validates `models.py`/`spec.py` against
the pinned DSL surface** (it parses, does not import — no `nxd` wheel is
installable here), runs **Phase E — the reach gate**, which decides BEFORE the transform is imported so the verdict precedes the act (`transform/main.py` may import no model-provider SDK, and no raw network transport unless `spec.py` declares an `api-source`/`db-source`; an import contradicting the declared connector type fails too — a green Phase E is an import-level name check over one file, not proof the transform is offline), runs **Phase C** (`dp-spec.approved.md` and `dp-spec.lock.json` present with the snapshot's bytes matching the lock, `build-record.json` present with a matching `compiled_from`, `README.md` present, no `../`-rooted contract pointer) and **Phase D — the policy boundary**: a promised
`nxd_decisions` must be a BASE model with in-vocabulary `status` **and `provenance`** columns (settled-or-not and authored-by are separate required axes),
and no landed policy value may also be a literal in the transform.
Then it prints the **distribution** and **ABSENT** read-backs (recorded as data in `build-record.json` `readback`, still non-gating). Read `unverified:`, read the distributions (`UNIFORM`
= a value you supplied, not one the data produced), and state both.

Reading a failure: a read-back assert or unquoted `main.<name>` query failure
means a name diverged — fix the NAME (`models.py`, `.promise`, `PHYSICAL_MODELS`,
and `data/<name>/` for base models), never quote around it. A derived model's
reconciliation assert (Step 3b) firing means the derivation is wrong — fix the
LOGIC, never loosen the assert.

**Database/API connectors need live credentials to dry-run.** With credentials,
run each type's own connectivity check per its reference doc (`database-source.md`
asserts `row_count > 0` per model; `api-source.md` a parseable response) — never
an exact fixture count. Without credentials, report it **not run**.

## Invariants — NEVER violate these

- **Python-only closure**: emit `spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`, `requirements.txt`, `dp-spec.approved.md`, `dp-spec.lock.json`, `build-record.json`, `README.md`, the connector companion artifact — and, for a credentialed source, `SENSITIVE` and `.gitignore` (the companion artifact is per the connector-types table in Overview; the credential guards are part of the closure, not cruft — never delete them). NEVER hand-write `deployment-spec.yaml` / `manifest.yaml` / `models.yaml` — the supervisor compiles those from the Python at pin time. Add one `contracts/expectations/<name>.py` or `contracts/promises/<name>.py` per contract the approved spec declares in `## expectations` / `## promises` — no more, no fewer.
- **Custom contracts are executable, not decorative** — each compiles to a verifier that must be able to FAIL, and a custom promise never replaces the ordinary `.promise(model)`. Never invent one the spec does not declare; wiring is Step 4 and [reference/custom-contracts.md](reference/custom-contracts.md).
- **Self-contained closure — no cross-boundary contract pointers** (Step 6a): the approved `dp-spec.md` is byte-copied in as `dp-spec.approved.md` and bound by `dp-spec.lock.json`, so everything a later session needs to continue the work lives INSIDE the closure and self-containment is hash-checkable rather than a discipline anyone has to remember. A promised derived model's contract (rubric, thresholds, output schema, verdict set) is materialized in the closure — in the approved spec, as `contracts/<name>.md`, or as the inert derived model itself — NEVER referenced by a `../`-rooted path to a doc outside the closure, `../dp-spec.md` included. Phase C fails a missing snapshot, lock, `build-record.json` or `README.md`, a snapshot whose bytes no longer match the lock, and any closure-escaping contract reference.
- **Sample-selection is part of the contract, not an incidental choice**: if the source is sampled rather than taken whole, the selection rule is stated in the spec's `population:` (and so travels in `dp-spec.approved.md`), reproducible over the same source, and MUST NOT drop rows on which a downstream model or step depends. A deterministic-but-arbitrary sample (e.g. "the oldest N") that silently excludes the rows a later step needs is a defect even though it reruns identically. A source field a downstream model or step depends on (a URL a later evaluation needs, a key a later join needs) is a **required-capture** field — declared in the plan as `models[].fields[].required_capture: true`, with the rows that actually lacked it recorded as an outcome in `build-record.json` `evidence.required_capture`, because a missing required field disables the downstream step without erroring.
- **The naming invariant**: each physical model name == `models.py` `semantic_model` arg == `spec.py` `.promise` == `PHYSICAL_MODELS` == `main.<name>`, unquoted lowercase snake_case; additionally `==` the connector's per-model reference (`data/<name>/`, see "THE NAMING INVARIANT" table) for base models only. `PHYSICAL_MODELS` is landed tables (base + derived), NOT the `data/` listing. Semantic views are `.model(...)` only and have no physical table. The transform's read-back assert is the runtime tripwire — keep it.
- **Output port named `duckdb`**: `.port("duckdb", storage(...))`, transform param `duckdb` typed `DuckDbOutput` (port name == param name). The local DuckDB driver requires exactly this name.
- **Through the port, always**: dlt destination is `duckdb.path` / `duckdb.schema`. No raw `duckdb.connect` writes, no view/table DDL, no direct file writes into staging. **Derived models do not relax this** — they reach the port as `@dlt.resource` generators in the same `pipeline.run(...)`, not as DDL.
- **Derived models are flat, deterministic, and in-run** (Step 3a): plain scalar dicts (no DataFrame — no pyarrow in the fixed venv; no nested values — they spawn `parent__field` child tables), appended to the SAME `resources` list, landed in ONE `pipeline.run(..., write_disposition="replace")`, named from `duckdb.model_tables`, listed in `PHYSICAL_MODELS`. Read the sources yourself with stdlib `csv`. No `now()`, no unseeded random, sorted inputs. Imports confined to pandas / duckdb / stdlib.
- **Every derived model carries mandatory in-memory asserts** (Step 3b): Tier 1 always — declared-key uniqueness plus a grain-derived row count against independently-read source rows; Tier 2 whenever a measure column is present — a signed measure total reconciled per currency pre-FX in `Decimal`, every exclusion itemized as a named term. Raised with actual-vs-expected before the rows are yielded. It is the ONLY durable data-quality gate on desktop. Never restate the transform's arithmetic as an assert, never substitute a weaker invariant for the measure reconciliation, and never loosen one to make a run pass. A model that **scores** adds both: every scored cell carries an explanation row (`band_id` + `evidence_field` + `evidence_quote` + `evidence_kind` + `limitation`, keyed by entity × criterion, reusing the `reference/llm-judgments.md` citation vocabulary; `evidence_kind` is `fact`/`inference` per explanation row and is NOT `nxd_decisions.provenance`, which is authorship per ruling), and every quote is asserted a verbatim substring of the field it cites. **Absence is labelled, never scored** — a field the derivation could not read scores empty with a `limitation` naming the kind: never the scale minimum, never zero, never a gate `FAIL` (an absent gate input is a landed `UNKNOWN`); it drops out of the weighted sum, the composite lands beside the fraction of rubric weight that scored, and a cap keyed on absence is legitimate only when its verdict names the uncertainty (`NEEDS_MORE_INFO`), never when it is a judgement (`REJECT`). Full rules, the absence kinds, and the precedence when a supplied rubric's bottom band *is* the absence case: [reference/derived-models.md](reference/derived-models.md).
- **No materialization before the policy read-back** (Workflow § Gate): when the request supplies a procedure with a gap that changes a score, verdict, gate outcome, or which rows land, NOTHING is written — no closure directory, no source copy, no generated code, no table, no scoring, no build — until the user has seen the enumerated proposal and replied. Reading the source is allowed; answering a technical delivery question is not approval; "use your judgement" licenses authoring the proposal, not skipping the turn.
- **Compile the approved `dp-spec.md`; never re-derive or exceed it.** When the IR exists it is the settled plan: its `models:` block is the derivation plan, its `criteria:`/`verdicts:` blocks are the landed rubric models, and its `decisions:` block is `nxd_decisions` row for row with `provenance` **copied, never recomputed** — a value the user typed stays `user_confirmed`, one you authored stays `agent_authored` however the user later approved it. A ruling in the closure that appears in no spec section is one the user never approved. The IR lives BESIDE the closure and is never referenced from it by a `../` path (Phase C fails that); the approved revision travels inside as the byte-copied `dp-spec.approved.md`, and outcomes — row counts, blockers, review rounds — never go back into the IR, because an IR is a pure function of its source.
- **The self-heal loop may change generated code; it may NEVER change the IR.** A compiler does not edit your source to make the build pass. Fix `spec.py` / `models.py` / `transform/main.py` / the landed data as often as the caps allow (remap ≤ ~2 per question, regenerate ≤ ~3 total, counted from `build-record.json` `attempts[]` rather than estimated), but if green is only reachable by changing the plan — narrowing the population to dodge a bad join, dropping a model whose grain will not resolve, relaxing a threshold, weakening a criterion — **stop**: that is a spec edit requiring re-approval, not a heal. Escalate it as `blocker.spec_edit_required`. Every attempt records `spec_hash_before` and `spec_hash_after`, so a heal that moved the hash is caught mechanically instead of trusted. A build-time blocker is an `open_questions` entry discovered LATE: write it back into the live `dp-spec.md`, which un-approves the spec and puts it in the same "needs your input" queue as a pre-build gap — never invent a second mechanism for it. Typed heal exits: `healed`, `healed_with_concessions`, `caps_exhausted`, `blocked`, `retry_environmental`; non-convergence is reported, never looped on silently and never abandoned silently.
- **FORBIDDEN versus DISCOURAGED — a heal loop may not relitigate an absolute.** FORBIDDEN, never done even to reach green, escalated as a blocker instead: hand-writing `deployment-spec.yaml` / `manifest.yaml` / `models.yaml` (`blocker.forbidden_handwritten_yaml`); hand-rolling a durable watermark instead of `transform_state` (`blocker.forbidden_manual_watermark`); `write_disposition="replace"` while yielding a delta (`blocker.forbidden_replace_disposition`); loosening an assert into restating its own arithmetic (`blocker.forbidden_assert_restates_arithmetic`); and reaching green only by changing the plan (`blocker.spec_edit_required`). DISCOURAGED is permissible, but the run is then green **with a disclosed concession** — recorded in `build-record.json` `concessions[]` and said to the user in plain words: what was done, what it cost, the alternative you rejected, in that order, with an offer to redo it. **A green run carrying an undisclosed concession is the worst state in this design, because it reads as materialized.** And `materialized` is the word — never `correct`: a green run means the approved plan compiled, ran and published, never that the numbers are right. Codes, the full split and the record's schema: **nxd-pocket-loop**'s `reference/build-record.md`.
- **No `.semantic_tools(...)`**: the supervisor's semantic child builds the catalog from compiled semantic roles; the spec must not emit an RPC port.
- **Public semantic DSL only**: base models carry `primary_key` / `dimension` / `join`; metrics are `metric_field(metric(...))` on `semantic_view(...)`. Never import private modules or write metadata directly.
- **Validated keys, by kind**: every promised physical model has one or more `primary_key()` fields. A **base** model's key is one or more EXISTING source columns whose tuple is non-null and unique across the supplied export — never synthesize one; stop and ask for the source key when that evidence is absent. A **derived** model's key is defined by the derivation's grain, constructed deterministically from source values plus the grain's ordinal, and proven unique by an in-transform assert. A dedupe keeps its source key; only a regrain declares a new composite.
- **Connector via secrets, `infra-profile.yaml` shape**: source config only from `secrets[...]`, keyed per connector type per the connector-types table in Overview, one entry per source instance (labeled when 2+ of a type — `reference/multi-source.md`) — always delivered via `.secrets([...])` on the transform. The profile is `metadata.name: desktop-local` with at least three services (`duckdb`, `python-compute`, one connector service per source instance). `duckdb`, `python-compute`, `csv-source`, and `file-source` keep `attributes: []` (their companion path file is relative); `db-source`/`api-source` (and their labeled variants) carry one `{"key": ..., "value": ..., "public": <bool>}` attribute per connection field instead, marked `public:` by sensitivity — secrets/identity (password, user, tokens/keys) `false`, non-secret topology/config (host, port, database, schema, base_url, auth_type, region) `true` so it survives an export — see `reference/database-source.md` / `reference/api-source.md`. Never fabricate a credential, never narrate one in chat, never write a raw database password or API token into a committed closure file, and never let two same-type instances share a name. Any source instance carrying a populated `attributes:` list also emits `.gitignore` (naming `infra-profile.yaml`, never `*`) and `SENSITIVE` in the same step that writes the credential, plus `chmod 0600 infra-profile.yaml` where a shell can reach the closure — Phase C fails the closure without the two files.
- **Run-local dlt state** (`pipelines_dir` under the run dir + `DLT_DATA_DIR` set; never `~/.dlt`); **`write_disposition="replace"`**; **`.transform-complete` touch** after the assert. **Incrementality never relaxes the run-local half**: dlt's own state stays ephemeral under the run dir, and the durable watermark lives in the kernel's `transform_state` bag — two separate mechanisms, never composed. `transform_state` round-trips on desktop and is the only sanctioned durable store: never hand-roll one (sidecar file, marker table, `SELECT max(<cursor>)` off the output table, durable `pipelines_dir`). The one sanctioned incremental route is [reference/incremental-transforms.md](reference/incremental-transforms.md); read it before switching any disposition, because every failure mode here is silent. It gates on **every promised model being append-safe** (never an aggregate, regrain, or dedupe), addresses the bag through **`for_model()`**, never flat indexing at any model count, yields every promised model every run, and verifies the write by **row count** — the table-name assert cannot see a missing write under `"append"` — and moves the `.transform-complete` touch after **both** checks (leave it after the naming assert and the readiness gate can report the build ready before the row-count check raises). `"replace"` while yielding only a delta shrinks the table to the delta; `"append"` without a cursor is the duplicate-rows bug.
- **Place, don't redesign**: semantic roles come from nxd-semantic-data-product. Preserve a file connector's supplied export exactly, and treat a database or API connector as read-only — cleaning, dedupe, reclassification and regrain happen ONLY in derived models downstream of pristine sources, never by editing the source export. Use an existing validated key for base models or surface the missing-key problem. Promise base and derived models, register metric views with `.model(...)`, and add no marker model on desktop.
- **Reference data is landed, never hardcoded**: FX rates, merchant→category rulings, account mappings and similar judgements that exist in no source data are user-confirmed and landed as their own model, so they stay queryable and reviewable. **This includes any agent- or LLM-inferred score, verdict, or classification** — landed as data (`status = proposed`, `provenance = agent_authored`); a per-entity judgement literal in transform code is hardcoded even when the downstream arithmetic is computed. Never bake reference data into transform code as a constant dict or `if` ladder. With no user available to confirm, land the mapping anyway as PROPOSED, recorded as a row in the closure's landed `nxd_decisions` model — never a `DECISIONS.md` file — see [reference/derivation-plan.md](reference/derivation-plan.md) and, for agent judgement, [reference/llm-judgments.md](reference/llm-judgments.md). **The transform never calls a model**: judging is agent-side and lands as CSV before the build; no model call, API key, or network in `transform/main.py` — inferring from inside the transform is nondeterministic and re-judges every rerun. Self-check **Phase E enforces this mechanically** before the transform is imported, and it is a tripwire rather than a sandbox: it denies an enumerated list of model-SDK and transport imports in that one file, so a green Phase E means "no *listed* SDK", not "provably offline" (see [reference/self-check.md](reference/self-check.md) § What Phase E cannot see).
- **Proven pins**: `dlt[duckdb]==1.28.2`, `duckdb==1.5.4`, pandas, the nxd wheel; Python `>=3.12,<3.13`.

**Related skills:** **`nxd-pocket-loop`** owns the conversation and invokes this skill; **`nxd-semantic-data-product`** produces the inferred model it places; **`nxd-data-product-builder`** is the k8s/cloud path.

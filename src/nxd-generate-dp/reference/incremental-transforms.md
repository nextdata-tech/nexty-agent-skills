# Incremental transforms on Pocket

The default Step 3 ingest is a **full replace** every run — that is what makes
reruns idempotent, and it is the right answer for almost every closure. Read this
only when the source is genuinely append-only, every output model is append-safe,
and re-reading the source whole is not acceptable.

> **`transform_state` is the durable cursor on desktop.** Writes persist and the
> previous run's bag is replayed. It is the only sanctioned mechanism: never
> hand-roll persistence — not a sidecar file, not a marker table, not a
> watermark read back out of the output table. Address the bag through
> `for_model()`; flat indexing is silently dropped. A committed cursor does not
> mean the rows are safe — the two do not share fate, so read
> [Durability](#durability-rows-and-cursor-do-not-share-fate) before you write.

## Contents

- [Before you start: the eligibility gate](#before-you-start-the-eligibility-gate)
- [Two mechanisms, never composed](#two-mechanisms-never-composed)
- [The `transform_state` kwarg](#the-transform_state-kwarg)
- [Addressing the bag: `for_model()` always](#addressing-the-bag-for_model-always)
- [Durability: rows and cursor do NOT share fate](#durability-rows-and-cursor-do-not-share-fate)
- [Write first, advance the cursor second](#write-first-advance-the-cursor-second)
- [Every run yields every promised model](#every-run-yields-every-promised-model)
- [Verifying the write: count rows, not table names](#verifying-the-write-count-rows-not-table-names)
- [Desktop specifics](#desktop-specifics)
- [Reading prior data back out of DuckDB](#reading-prior-data-back-out-of-duckdb)
- [Do NOT](#do-not)
- [Worked transform: append-only source](#worked-transform-append-only-source)

## Before you start: the eligibility gate

Incrementality is not a property of the source alone. **Every promised model the
transform lands must be append-safe**, which means: a row, once written, is never
revised, re-derived, or re-grained by any later run. Check all four before
writing a line:

1. **The source is append-only.** Rows are only ever added, never updated or
   deleted, and carry a monotonically increasing cursor column.
2. **Every base model is a pass-through of that source.** No cleaning or
   dedupe pass whose result for an old row could change.
3. **Every derived model is append-safe too.** This is the clause authors skip.
   A derived model is append-safe only when each output row is a pure function
   of source rows that are themselves already final. It is **not** append-safe
   when it is:
   - an **aggregate or regrain** (daily/weekly rollups, per-entity counts and
     sums) — a late-arriving event for an already-emitted day means the old
     aggregate row is now wrong, and appending a second row for the same
     declared grain duplicates the primary key;
   - a **dedupe or reclassification** whose verdict for an old row can change;
   - anything whose **derivation logic** you may edit in a later refine cycle —
     rows landed under the old logic stay in the table forever, silently mixed
     with rows landed under the new logic.
4. **A refine cycle will not change the derivation.** Pocket re-runs are refine
   cycles on the same workflow, so this is a live risk, not a hypothetical.

If any promised model fails the gate, the correct answer is one of:

- **Keep the whole closure on full replace.** Almost always right. Say so plainly
  to the author, with the failing model named.
- **Split the disposition by model.** Land append-safe base models with
  `write_disposition="append"` and rebuild the non-append-safe derived models
  with `write_disposition="replace"` in the same run, from the full table read
  back out of DuckDB. The derived model is then always correct, and only the
  base scan is incremental. Two `pipeline.run(...)` calls, each with its own
  disposition and its own resource list; the cursor covers only the base models.

Never append to an aggregate or a regrain. The output is duplicate declared-grain
keys or stale arithmetic, on a green run, with no error.

## Two mechanisms, never composed

An incremental closure runs **two separate state mechanisms**. They are not layers
of one thing, and wiring one into the other silently corrupts the output.

| | dlt pipeline state | your watermark |
|---|---|---|
| Holds | dlt's own bookkeeping (load ids, schema) | your cursor / offset |
| Lives in | `pipelines_dir` under the run dir | the kernel's per-workflow SQLite via `transform_state` |
| Lifetime | **ephemeral** — one run, thrown away | **durable** — survives into the next run |
| You read it | never | every run |

**The run-local dlt invariant does not change.** `pipelines_dir` still sits under
the run dir, `DLT_DATA_DIR` is still set, and it is still never `~/.dlt`. Do not
try to get incrementality by making dlt's state durable — that is a different,
unsupported mechanism, and dlt's incremental cursors are not what the kernel
replays.

**The write disposition question is separate and it is the dangerous one.** The
default template lands everything with `write_disposition="replace"`, which
rewrites the table from what this run yielded. If you keep `"replace"` **and**
start yielding only the delta, the table shrinks to just the delta — a green run
that silently destroys history. An incremental transform that yields only new
rows must land them with `write_disposition="append"`, and must accept the
consequence: **`"append"` reruns are not idempotent by themselves.** The
`transform_state` cursor is what makes them idempotent — it is the only thing
stopping a rerun from re-yielding rows it already landed. Get the cursor wrong
and you are back in the duplicate-rows bug class.

So: full-replace closures need no cursor. Incremental closures need `"append"`
**plus** a correct cursor. Never `"replace"` plus a delta.

## The `transform_state` kwarg

Declare a parameter literally named `transform_state` on the
`@data_product.on_transform()` function. The kernel injects the previous
successful run's committed bag; whatever the bag holds when the transform returns
is persisted for the next run.

```python
@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any], transform_state) -> None:
    ...
```

Two rules on what the bag may hold:

- **Empty on the first run.** There is no prior run, so the bag is an empty
  mapping — never `None`, never absent. Always read through `.get(key, default)`
  and pick a default that means "take everything from the beginning". Never
  `transform_state["cursor"]` on a path that can execute on run one.
- **JSON-serializable values only.** The kernel serializes the bag; it does not
  inspect or coerce it. A `numpy.int64` row count or a `pandas.Timestamp`
  read off a DataFrame is **not** JSON-serializable and fails the commit. Cast at
  the boundary: `int(...)`, `float(...)`, `str(...)`, or `.isoformat()` for a
  timestamp. Store strings and numbers, not objects.

## Addressing the bag: `for_model()` always

**Use `transform_state.for_model("<name>")` in every closure you write, even a
single-model one.** Never index the bag flat.

The mechanism is a two-way split on the **declared-model list the kernel seeded
into the handle** — not on how many models the closure promises:

- **Empty list** → the runtime hands back a bare `TransformState`: a plain
  `dict`, flat-indexable, with **no** `for_model()` and **no** `generic()`, and
  **not registered for draining**. Every write to it is dropped on the floor
  when the transform returns.
- **Any non-empty list** — one declared model or twenty — → a
  `MultiModelTransformState`, addressed through `for_model()` / `generic()`.
  With exactly one declared model it is additionally pre-bound to that model, so
  flat indexing happens to reach the right bag; with two or more it is unbound
  and flat writes go nowhere.

So flat indexing is not "the single-model form". It is the shape you get when
the runtime could not tell the transform which models exist — and in exactly
that case it does nothing. A bare `TransformState` is the tell that the runtime
never learned the model names: `for_model()` is absent, so it raises
`AttributeError`, and every flat write is silently discarded.

**The empty-list shape does not arise on desktop.** The local compute path seeds
the declared models (see [Desktop specifics](#desktop-specifics)), so
`for_model()` is there and this split is background on *why* the bag is addressed
that way — not a branch to code against. If `for_model()` ever does raise
`AttributeError`, the response is **not** to reach for another store: flat
indexing persists nothing, and every hand-rolled alternative is banned in
[Do NOT](#do-not) for reasons that do not stop applying at the moment the bag
breaks. Stop, tell the author the runtime does not support durable transform
state, and keep the closure on full replace — which needs no cursor at all and
stays correct on every rerun. A closure that cannot hold a cursor is not
eligible for incrementality.

**This is the failure mode to fear, and it is silent in both directions.** A
flat write is accepted — `transform_state["max_event_id"] = 12345` raises
nothing, the run stays green, every assert passes, the build succeeds — and then
persists nothing. The next run reads an empty bag, defaults the cursor to "take
everything", re-yields the entire source into an `"append"` table, and
duplicates every row. Nothing anywhere reports a problem; the only symptom is a
row count that grows by the full source size on every run. Never index flat, at
any model count.

The trap compounds because **the declared-model count is easy to cross without
noticing**. The Step 3 contract's `PHYSICAL_MODELS = BASE_MODELS +
DERIVED_MODELS` means a closure with one base model plus one derived model
already declares two, so a pre-bound flat cursor that worked becomes a dropped
one the moment a refine cycle adds a derived model. `for_model()` is correct at
every non-empty model count and raises `KeyError` listing the valid names on a
typo, so it cannot fail silently — which is why it is the only form to write.

```python
events = transform_state.for_model("events")
users = transform_state.for_model("users")
shared = transform_state.generic()

events["max_id"] = int(new_event_max)
users["max_id"] = int(new_user_max)
shared["run_count"] = shared.get("run_count", 0) + 1
```

- `for_model(name)` validates `name` against the declared models and raises
  `KeyError` listing the valid names on a typo. A model never sees another
  model's bag.
- `generic()` is one shared, model-less bag persisted under a reserved key. Use
  it for a cursor that spans models (a single source watermark feeding several
  tables). It is available only when the transform runs **once** for the whole
  run — which is always the case on desktop, since the local driver has no
  per-model dispatch (see [Do NOT](#do-not)).

## Durability: rows and cursor do NOT share fate

**On desktop the two halves of a run have opposite failure behavior. Do not
assume a raise rolls back the rows.**

- **The cursor is transactional.** The kernel folds the `transform_state` bags
  into the committed transaction only when every model succeeded. A run that
  raises persists **no** state — the next run reads back the cursor of the last
  run that *succeeded*.
- **The rows are not.** The local DuckDB storage driver implements no transaction
  protocol: there is no staging clone and no rollback. dlt's writes into the
  DuckDB file are **immediate and permanent** the moment `pipeline.run(...)`
  returns, and a later raise cannot undo them.

So a transform that lands rows and *then* raises leaves the rows durably written
while the cursor stays where it was. That is torn state, and on the next run the
stale cursor re-yields those same rows into an `"append"` table — duplicate rows,
green run, no error.

Two consequences you must design for:

1. **Do every check you can before the write, not after.** Validate the batch —
   row shape, key uniqueness, cursor monotonicity, Step 3b data-quality asserts —
   while it is still just a list in memory. A check that raises *before*
   `pipeline.run(...)` costs nothing. A check that raises *after* it has already
   left rows on disk with an unadvanced cursor.
2. **Make the post-write verification tell you what actually landed**, so a
   failure is diagnosable rather than mysterious. It cannot roll anything back;
   its job is to stop the cursor from advancing over a bad write and to name what
   went wrong. See
   [Verifying the write](#verifying-the-write-count-rows-not-table-names).

Recovering from a torn run means dropping the duplicate rows from the DuckDB
table by hand, or rebuilding the closure from scratch with a full replace. Say so
to the author rather than letting them discover it from a row count.

## Write first, advance the cursor second

Because the bag is persisted from whatever it holds **when the transform
returns**, the assignment statement's position in the function does not by itself
decide anything — but the code between it and the return does. Advance the cursor
only after every operation that can fail has succeeded.

**Correct** — validate, land, verify, then advance:

```python
new_max = max(int(r["event_id"]) for r in new_rows)
_assert_batch_ok(new_rows)                             # 1. check BEFORE writing

pipeline.run(resources, write_disposition="append")    # 2. land the data

landed = _count_rows(...)                              # 3. verify what landed
if landed != expected_total:
    raise RuntimeError(...)                            #    (cursor stays put)

events_state["max_event_id"] = new_max                 # 4. only now advance
```

**Wrong** — advance, then land:

```python
events_state["max_event_id"] = new_max                 # cursor moved first
pipeline.run(resources, write_disposition="append")    # if this raises...
```

The wrong version is a hazard for the case that does **not** raise: any code that
advances the cursor and then *conditionally* skips or filters the write — an
early `return` on an empty batch, a partial write in a loop, a swallowed
exception — commits a cursor past rows that were never landed. Those rows are
then permanently skipped, and the run is green. Put the assignment after the
write and after the verification, with nothing between it and the return that can
decide not to write.

The same reasoning forbids advancing the cursor from the *source* rather than
from what was written: set it from the max value actually yielded into
`pipeline.run(...)`, not from the max value observed while scanning the source.

## Every run yields every promised model

**Build the resource list from `PHYSICAL_MODELS`, not from the models that happen
to have new rows.** A model with an empty delta yields an empty resource; it does
not get dropped from the list.

This looks like pointless work and it is the single most important structural
rule in a multi-model incremental transform. Skipping a model with no delta —
the natural, "obviously correct" optimization — is what produces a cursor that
advances over rows that were never written:

> Two promised models, `events` and `users`. On run 2 only `events` has new
> source rows, so the resource list is built with just the `events` resource.
> `users` is never handed to `pipeline.run(...)` at all. But **both** cursors are
> assigned and both bags are committed at the end of the run. `users`' watermark
> now claims rows were landed that no `pipeline.run(...)` ever saw. Those rows
> are skipped on every subsequent run, forever, with a green run and no error.

Yielding every model every run makes the cursor advance and the write structurally
inseparable: a model that is in the resource list is a model whose rows went
through `pipeline.run(...)`. Advance a model's cursor **only** in the same branch
that put its rows into the resource list — never unconditionally at the end.

Do **not** try to detect the skip with the table-name assert. It cannot see it —
that is the next section.

## Verifying the write: count rows, not table names

The default full-replace template asserts on
`pipeline.default_schema.data_table_names()`. **Under `"append"` that assert
cannot detect a promised model that was not written this run**, so it is not a
sufficient verification for an incremental transform.

The reason is that dlt rehydrates its schema from the destination. Once a table
exists in the DuckDB file from any previous run, `data_table_names()` reports it
whether or not this run wrote a single row to it. So on run 2 of the two-model
example above, `data_table_names()` returns **both** `events` and `users`, the
assert compares equal, nothing raises, and both cursors commit. The assert only
ever catches unexpected *extra* tables; it never catches a *missing* write.

The same rehydration has a second consequence, in the opposite direction: on a
genuine **first** run the schema is inferred from what flows through the
pipeline, and a table is registered only once at least one row reaches it. A
first run whose delta is empty for every model therefore produces **no** data
tables at all, `data_table_names()` returns `[]`, and the table-name assert
**fails** — on a run that did nothing wrong.

So keep the table-name assert (it still enforces the naming invariant and still
catches semantic views leaking into the output), but scope it to what it can
actually prove, and add a row-count check that verifies the write:

```python
# Naming invariant: dlt must never write a table we did not promise. Under
# "append" a table can also be absent because THIS run had nothing new for it
# (and on run one, because nothing has ever been written), so check for
# unexpected extras rather than exact equality.
expected = {duckdb.model_tables[model] for model in PHYSICAL_MODELS}
actual = set(pipeline.default_schema.data_table_names())
if actual - expected:
    raise RuntimeError(
        f"dlt produced unpromised tables {sorted(actual - expected)!r}"
    )

# What actually landed. This is the check the cursor advance depends on:
# row counts are the only signal that distinguishes "wrote the delta" from
# "silently wrote nothing".
for model in PHYSICAL_MODELS:
    landed = _table_row_count(duckdb, model)   # 0 when the table does not exist
    if landed != prior_counts[model] + len(new_rows_by_model[model]):
        raise RuntimeError(
            f"{model}: expected {prior_counts[model] + len(new_rows_by_model[model])} "
            f"rows after append, found {landed}"
        )
```

Read `prior_counts` from the table **before** the write, with the same read-back
helper as below, defaulting to `0` when the table does not exist yet. The check
then holds on the first run (`0 + n == n`), on an empty delta (`n + 0 == n`), and
catches the skipped-model case the table-name assert cannot see.

## Desktop specifics

- **`transform_state` round-trips.** The kernel routes the local Python compute
  driver through its batch module — the module that seeds and folds incremental
  state — and the per-model seeding is wired, so the transform receives a
  `MultiModelTransformState` with `for_model()` available and the previous run's
  bag replayed. Write the bag and read it back; there is nothing to enable and
  nothing to check first.
- **Persistence is on by default.** The supervisor always hands the kernel a
  per-workflow database path; there is no flag to set and nothing to enable.
- **One `<workflow_key>.sqlite3` per workflow.** State is scoped to the workflow,
  so it survives refine cycles that reuse the same workflow id — a rebuild of the
  same workflow reads back the previous run's committed state. A *different*
  workflow id starts from an empty bag.
- **There is no cron on Pocket.** Runs happen because the user asks for one. Do
  not write guidance or comments in terms of "each scheduled run" or "nightly" —
  the correct framing is "the next run", whenever that is. A refine cycle is a
  run like any other, and it will read the cursor.
- **A refine cycle does not reset the table.** Editing the transform and
  re-running appends to whatever previous runs already landed, under the old
  logic, with the cursor still in place. If a refine changes what a row should
  contain, the already-landed rows do not change with it — that is why the
  eligibility gate rules out derivations you expect to edit.
- The kernel-side store differs from the platform (SQLite locally rather than
  Postgres), but the API and the semantics are identical. Nothing in the
  transform changes between them.

## Reading prior data back out of DuckDB

`DuckDbOutput` exposes `path`, `schema`, `model_tables` and `full_table_name` —
it has **no** query or execute method. To read what previous runs landed (to
count rows for the verification above, or to check for overlap), open the file
directly. This is a read, for verification — **not** a place to keep the cursor;
the cursor lives in `transform_state`.

**Import the module under an alias.** The output port parameter must be named
exactly `duckdb` (the local DuckDB driver requires that name and it cannot be
renamed), so inside the transform body the parameter **shadows** the `duckdb`
module. A bare `import duckdb` plus `duckdb.connect(...)` in the function body
resolves against the `DuckDbOutput` dataclass and raises
`AttributeError: 'DuckDbOutput' object has no attribute 'connect'`. The same
shadowing makes `except duckdb.CatalogException` unreachable. Alias the module at
import time:

```python
import duckdb as duckdb_lib   # the PORT PARAM is named `duckdb` and shadows it


def _table_row_count(duckdb: DuckDbOutput, model: str) -> int:
    """Rows currently landed for `model`; 0 before the first run writes it."""
    table = duckdb.model_tables[model]
    try:
        with duckdb_lib.connect(duckdb.path, read_only=True) as con:
            row = con.execute(
                f'SELECT count(*) FROM "{duckdb.schema}"."{table}"'
            ).fetchone()
    except (duckdb_lib.IOException, duckdb_lib.CatalogException):
        # IOException: the database FILE does not exist yet (first run).
        # CatalogException: the file exists but this table has not been written.
        return 0
    return int(row[0]) if row and row[0] is not None else 0
```

**Catch both exceptions.** They are raised at different stages and only one of
them is about the table:

- `duckdb.IOException` — `connect(path, read_only=True)` against a path that does
  not exist. This is the **first run**, before anything has ever been written.
  `read_only=True` will not create the file, so this is the normal first-run
  path, not an error condition.
- `duckdb.CatalogException` — the file exists but the table does not, e.g. a new
  model added to an existing closure.

Catching only `CatalogException` (the intuitive choice, since the missing thing
is a table) leaves the first run crashing on the connect.

This is a **read**, and it is the one sanctioned use of `duckdb.connect` in a
transform. The Step 3 ban is on *writing* around the port: no `duckdb.connect`
insert or update, no `CREATE TABLE` / `CREATE VIEW` DDL, no direct file write into
staging. All writes still go through dlt with
`dlt.destinations.duckdb(credentials=duckdb.path)`.

Use the read-back for the row-count verification, which the cursor cannot
substitute for. Do **not** use it to reconstruct the cursor — a
`SELECT max(<cursor>)` off the output table is a hand-rolled persistence
mechanism, and the closure contract forbids it. If the source has no usable
cursor column at all, the closure is not eligible for incrementality: keep it on
full replace and say so.

## Do NOT

- **Do NOT use `.when(...)` on desktop.** The local Python compute driver
  discards the kernel's per-model execution payloads, so a `.when(...)` DAG never
  dispatches — the models silently never run. Desktop transforms are always a
  single invocation landing every model. (`generic()` is therefore always
  available on desktop; the inner-orchestration restriction on it cannot arise.)
- **Do NOT reference `NXD_TRANSFORM_STATE_SIDECAR_PATH`.** It is a Databricks-only
  mechanism. It does nothing on desktop and putting it in a closure is a
  correctness lie.
- **Do NOT switch to `write_disposition="append"` just to "get incrementality".**
  `"append"` accumulates whatever you yield, every run, forever. It is correct
  **only** paired with a cursor that guarantees you never yield an already-landed
  row. Without the cursor it is exactly the duplicate-rows bug.
- **Do NOT keep `write_disposition="replace"` while yielding only the delta.**
  That rewrites the table to just the delta and destroys every prior row, with a
  green run and no error.
- **Do NOT append to an aggregate, a regrain, or a dedupe.** Only models that
  pass the [eligibility gate](#before-you-start-the-eligibility-gate) may be
  appended; rebuild the rest with `"replace"` in the same run.
- **Do NOT hand-roll durable state.** No JSON sidecar file, no marker table, no
  `SELECT max(<cursor>)` watermark off the output table, no durable
  `pipelines_dir`, no environment variable. `transform_state` is the mechanism;
  the read-back out of DuckDB is for row-count verification only.
- **Do NOT index the bag flat.** Flat writes on an unbound handle are accepted
  and dropped on the floor — no exception, no warning, a green run that persists
  nothing, and an append-only load that duplicates every row on every run. Use
  `for_model("<name>")` at every non-empty model count — a handle that happens to
  be pre-bound to a sole model stops being bound the moment the closure declares
  a second, and adding one derived model is enough.
- **Do NOT drop a model from the resource list because it has no new rows.**
  Yield every promised model every run, and advance a cursor only in the branch
  that wrote that model's rows.
- **Do NOT treat the table-name assert as proof the write happened.** It cannot
  see a missing write under `"append"`. Count rows.
- **Do NOT assume a raise rolls back the rows.** The local DuckDB driver has no
  transaction; rows are permanent the moment `pipeline.run(...)` returns. Check
  before writing.
- **Do NOT `import duckdb` and call `duckdb.connect(...)` inside the transform.**
  The port parameter shadows the module. Alias it: `import duckdb as duckdb_lib`.
- **Do NOT guard the read-back with `except duckdb.CatalogException` alone.** A
  first run raises `IOException` from the connect, before any table lookup.
- **Do NOT make dlt's `pipelines_dir` or `DLT_DATA_DIR` durable.** They stay under
  the run dir. The watermark lives in `transform_state`, nowhere else.
- **Do NOT store non-JSON values** in the bag (numpy/pandas scalars, `datetime`,
  `Decimal`, sets, DataFrames). Cast first.
- **Do NOT default the first-run cursor to "now"** or to the source's current max.
  That skips the entire existing history on run one.

## Worked transform: append-only source

An append-only event export: one CSV directory whose files only ever gain rows
with a monotonically increasing `event_id`. The single promised model `events` is
a pass-through of that source, so it passes the eligibility gate. Every clause of
the Step 3 contract survives — typed `DuckDbOutput`, config from `secrets`,
run-local dlt state, writes through the port, `PHYSICAL_MODELS` from
`.promise(...)`, the naming assert, the `.transform-complete` touch. The changes
are the `transform_state` kwarg addressed through `for_model()`, the row filter,
`"append"` instead of `"replace"`, the row-count verification, and the cursor
advance placed last.

```python
"""<dp-name>: incrementally load the append-only event export into DuckDB."""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

# Source-checkout shim: see reference/derived-models.md. Copy it verbatim.

import dlt
import duckdb as duckdb_lib  # aliased: the port param below is named `duckdb`

from nxd import data_product
from nxd.core.context import DuckDbOutput

BASE_MODELS = ("events",)
DERIVED_MODELS = ()
PHYSICAL_MODELS = BASE_MODELS + DERIVED_MODELS


def _table_row_count(duckdb: DuckDbOutput, model: str) -> int:
    """Rows currently landed for `model`; 0 before the first run writes it."""
    try:
        with duckdb_lib.connect(duckdb.path, read_only=True) as con:
            row = con.execute(
                f'SELECT count(*) FROM "{duckdb.schema}"."{duckdb.model_tables[model]}"'
            ).fetchone()
    except (duckdb_lib.IOException, duckdb_lib.CatalogException):
        # IOException: DB file absent (first run). CatalogException: table absent.
        return 0
    return int(row[0]) if row and row[0] is not None else 0


@data_product.on_transform()
def ingest(
    duckdb: DuckDbOutput,
    secrets: dict[str, Any],
    transform_state,
) -> None:
    """Land only events newer than the previous run's committed cursor."""
    source_root = Path(secrets["csv_source"])
    # for_model(), never flat indexing: flat writes are dropped SILENTLY as soon
    # as the closure promises a second model (one derived model is enough).
    events_state = transform_state.for_model("events")
    # First run has no prior state: 0 means "take everything".
    last_seen = int(events_state.get("max_event_id", 0))

    # Read the source ourselves so we can filter and compute the new cursor.
    rows: list[dict[str, Any]] = []
    for path in sorted((source_root / "events").glob("*.csv")):
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                event_id = int(row["event_id"])
                if event_id > last_seen:
                    row["event_id"] = event_id
                    rows.append(row)

    # Validate BEFORE writing. The local DuckDB driver has no transaction, so a
    # raise after pipeline.run(...) leaves the rows on disk with a stale cursor.
    if len({r["event_id"] for r in rows}) != len(rows):
        raise RuntimeError("duplicate event_id within the new batch")

    # Count what is already landed, to verify the append below.
    prior_count = _table_row_count(duckdb, "events")

    # Keep ALL dlt state run-local (next to the staging file) — never ~/.dlt.
    run_dir = Path(duckdb.path).parent
    pipelines_dir = run_dir / "dlt-pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")

    pipeline = dlt.pipeline(
        pipelines_dir=str(pipelines_dir),
        destination=dlt.destinations.duckdb(credentials=duckdb.path),
        dataset_name=duckdb.schema,
    )

    # EVERY promised model goes into the resource list every run, even with an
    # empty delta. Dropping a model whose delta is empty would let its cursor
    # advance over rows no pipeline.run(...) ever saw.
    @dlt.resource(name=duckdb.model_tables["events"])
    def new_events():
        yield from rows

    # "append" — NOT "replace": replace would rewrite the table to just this
    # delta and drop every previously landed event. The cursor below is what
    # keeps "append" idempotent across reruns.
    pipeline.run([new_events()], write_disposition="append")

    # Naming invariant: dlt must never write a table we did not promise. Check
    # for EXTRAS, not exact equality — under "append" a promised table is
    # legitimately absent from the schema until a run actually writes rows to it.
    expected = {duckdb.model_tables[model] for model in PHYSICAL_MODELS}
    actual = set(pipeline.default_schema.data_table_names())
    if actual - expected:
        raise RuntimeError(
            f"dlt produced unpromised tables {sorted(actual - expected)!r}"
        )

    # Verify the write by ROW COUNT. The table-name assert above cannot detect a
    # model that was silently not written: dlt rehydrates its schema from the
    # destination, so a table landed by an earlier run is reported either way.
    landed = _table_row_count(duckdb, "events")
    if landed != prior_count + len(rows):
        raise RuntimeError(
            f"events: expected {prior_count + len(rows)} rows after append, "
            f"found {landed}"
        )

    # Produce-verification marker: the supervisor's readiness gate waits for it.
    # This is fallible I/O, so it runs BEFORE the cursor advance — if the marker
    # cannot be written the run is not complete, and the cursor must stay put.
    (run_dir / ".transform-complete").touch()

    # Advance the cursor LAST: after the write, after the verification, and after
    # every other operation that can fail — with nothing between it and the return
    # that can decide not to write. Only when this run actually yielded rows.
    # int(...) keeps it JSON-serializable.
    if rows:
        events_state["max_event_id"] = int(max(r["event_id"] for r in rows))


if __name__ == "__main__":
    data_product.main()
```

Note the empty-batch case: when `rows` is empty the cursor is left untouched
rather than reset, dlt lands nothing, and the row-count check passes trivially
(`prior_count + 0 == prior_count`). This holds on the first run too, when the
DuckDB file does not exist yet and `_table_row_count` returns `0` on both sides —
which is why the verification counts rows instead of comparing table names.

# End-to-end proof

Two runnable files, proving two different things. `transform_main_mockup.py`
(one level up) shows the shape of a transform and **does not run**; both of
these do.

| file | proves |
|---|---|
| `run_e2e.py` | the **data chain** — dlt lands rows, the mapper judges them, the gate decides, dlt lands the judgements. Calls `map_inputs` directly. |
| `transform_main.py` | the **platform entrypoint** — the closure is registered with `@data_product.on_transform()` and invoked by nxd's own `data_product.run_transform(...)`. |

```bash
python3 examples/e2e/transform_main.py                    # replay
python3 examples/e2e/transform_main.py --prove-block      # the gate must refuse
python3 examples/e2e/transform_main.py --prove-atomicity  # crash between loads
.venv-live/bin/python examples/e2e/transform_main.py --live
```

## What `transform_main.py` proves

- nxd's **real decorator and registry** accept the closure, and nxd's
  `TransformTask` binds its arguments through the same providers a platform run
  uses.
- The `ExecutionContext` is built by **nxd's own `from_json`**, not a stub shaped
  to look like one. A context-schema change fails here loudly.
- **The output port is a real `DuckDbOutput`**, declared in the context as a
  `local/duckdb/storage` service and injected into the closure **by parameter
  name** (`def ingest(duckdb: DuckDbOutput)`) by
  `TransformInputOutputPortArgumentProvider`. Every physical table name comes
  from `duckdb.model_tables` / `full_table_name()` — the transform hardcodes
  none.
- **`--prove-block` demonstrates the gate refusing.** With `max_absent_share`
  tightened to 0, the transform raises and the database shows
  `invoice_documents` present (run 1) with **no** `mapper_proposals`,
  `mapper_evidence`, or `invoice_terms`. That is the two-`pipeline.run` ordering
  verified by observation: a refused build publishes nothing. Checked against
  the database, not the return value.

### It needs the monorepo source, not the installed wheel

The installed wheel is `nxd.core` v0.41.26, which predates
`local/duckdb/storage`: `storage_context_type_for_driver` has no duckdb case
there, so `DuckDbOutput` does not exist and the port cannot be bound at all.
The monorepo source is v0.41.147 and has both.

`bootstrap.py` prepends `components/nxd_py/{core,data_product}` to `sys.path`
before the first `import nxd`. The Python layer overlays the wheel while still
using its compiled Rust extension, **so no build step is required**. Every run
prints which nxd answered:

```
[nxd] nxd.core v0.41.147 (monorepo source) — DuckDbOutput available
```

That line is load-bearing: on the older wheel the run fails rather than quietly
proving less.

### Publication is NOT atomic, and `--prove-atomicity` characterises it

CONTRACT §7.7 asks what a crash between the two `pipeline.run` calls leaves
behind. This injects exactly that fault and reports the real state rather than
asserting a hoped-for one. Two scenarios, and the second is the dangerous one:

**Crash on a first run** — inputs landed, judgement tables absent entirely. A
consumer joining them gets zero rows and **fails loudly**; a re-run
replace-loads both sides and repairs it. Survivable.

**Crash after a previous successful run** — the new (smaller) input set is
landed while the OLD judgements survive. Verified: 1 input, 3 judged rows, 2 of
them describing inputs that no longer exist. This is **not detectable by
absence** — `invoice_terms` is present, populated, internally consistent, and
partly obsolete, with survivors and orphans indistinguishable.

Mitigation available today: join judgements to inputs on the identity column, or
filter on the `execution_id` every proposal already carries — a stale row's is
not the latest. The real fix is one transaction across both loads, which dlt
gives per `pipeline.run` but not across two, and the mapper needs two because it
must read landed inputs before it can judge them.

## What it does NOT prove

No kernel, no transaction, no `transform_state`, no provisioning. The context is
hand-built rather than produced by the kernel — its *shape* is nxd's and the
port is real, but nothing orchestrates it. The DuckDB file is created by the
script, not provisioned by a driver.

---

## `run_e2e.py`

```bash
python3 examples/e2e/run_e2e.py            # replay, no API calls, no key
python3 examples/e2e/run_e2e.py --keep     # keep the duckdb file to poke at
```

`--live` needs one interpreter that can see all four packages, and by default
none can: the system interpreter has `dlt`/`duckdb`/`nxd` but not `anthropic`,
while `.venv-live` has only `anthropic`. `.venv-live` is bridged to the system
site-packages with a `_system_sitepackages.pth` file, so:

```bash
set -a && . ./.env && set +a          # ANTHROPIC_API_KEY
.venv-live/bin/python examples/e2e/run_e2e.py --live
```

Exit `0` = the chain worked and the landed schema matches the record contract.
Exit `1` = a landed table is missing contract columns. Exit `2` = the gate
blocked, and nothing landed.

## What is real

- **dlt** loads into a real **duckdb** file, twice.
- The **shipped mapper package** — same `map_inputs`, validator, evidence
  checker, resolver, coverage gate.
- Three real output tables, with the wide one projected from the same in-memory
  bundle as the sidecar.

## What is stubbed

`_ExecutionContextStub` supplies the one thing the closure reads from the
platform: `model_tables`. A real `ExecutionContext` carries driver-resolved
output ports and needs a cluster. `nxd.data_product` is still imported, so a
real signature change fails here rather than rotting.

## What this run proved, by running

Four bugs, none of which reading had caught:

1. **The grant refused its own run.** The spec must be stamped with
   `harness_version` *before* the grant binds its hash, or the consent gate
   rejects the very run the grant was written for.
2. **The response shape was invented.** A `{"rows": [{"fields": {...}}]}`
   wrapper that the compiled wire schema does not describe — the real shape is
   flat `{field: {value, evidence}}`, and the sentinel is `__not_stated__`.
3. **`as_row()` returns a dict, not a tuple.** Zipping it against the column
   tuple landed a table whose every row was the column names. Type-checks,
   loads clean, and is visible only by querying what landed.
4. **dlt silently drops all-null columns.** `error_code`, `error_detail`,
   `value_bool`, `value_timestamp`, `source_model`, `extractor`,
   `extractor_version` never materialized. A consumer joining on `error_code`
   gets "column not found" rather than nulls — and only on runs where nothing
   went wrong, so the schema is least stable exactly when the pipeline looks
   healthiest. Fixed with explicit `columns=` hints and a conformance check
   that exits non-zero, verified to fail when a hint is removed.

## Proven live

`--live` run against the real API, 3 haiku calls, ledger showing
`provider: anthropic` with real token counts (1378/127, 1361/119, 1351/100) and
three successes. Same result as replay: 8 cells `ok` and `verified`, 1
`evidence_absent`, 37/37 contract columns, exit 0.

One difference worth keeping: the live model quoted
`"Payment terms: net 45 days"` where the replay fixture has the trailing period.
The model picked a slightly different span and the substring check verified it
anyway — the checker working against genuine output rather than a curated
fixture.

## What it does NOT prove

- **Publication is not atomic.** Two `pipeline.run` calls; a crash between them
  leaves landed inputs with no judgements. CONTRACT §7.7 wants a fault-injection
  test. It does not exist.
- **The durable-review half never executes.** `resolve()` runs, but with an
  empty review set — `cmd_resolve` is still a stub (REVIEW.md CV-3), so
  override, staleness, and re-binding are unexercised here.
- **No platform integration.** No cluster, no driver, no real output port.

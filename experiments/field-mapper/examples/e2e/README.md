# End-to-end proof

`transform_main_mockup.py` (one level up) shows the shape of a real NXD
transform and **does not run**. This one does.

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

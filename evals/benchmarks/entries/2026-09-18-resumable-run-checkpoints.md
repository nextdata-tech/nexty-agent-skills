---
id: 2026-09-18-resumable-run-checkpoints
date: 2026-09-18
label: "add a durable checkpoint contract before live resumption"
plugin_version: 0.51.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — add a durable checkpoint contract before live resumption

## Notes

Harness-only. No skill under `src/` and no scenario declaration changed, so no
runnable public arm can distinguish this change.

The checkpoint layer is intentionally a separate foundation from replay
artifacts and live Claude/supervisor continuation. It stores a canonical,
grouped execution identity, immutable complete-turn state, an atomic latest
pointer, and an fsynced journal. It fails closed on identity drift, incomplete
turns, broken prefix chains, and credential-like payloads. It distinguishes
native continuation from report-only regrading; it does not call a replay a
live success.

## Evidence

The carrying evidence is
`evals/dp-scenarios/tests/test_runner_checkpoint.py` plus the focused runner
tests in `evals/dp-scenarios/tests/test_runner_tier.py`. They cover canonical
identity stability, strict mismatch handling, report-only grading changes,
atomic persistence and journal recovery, incomplete checkpoints, prefix-chain
validation, secret safety, and per-turn handoff checkpoint emission from a live
runner. Native Claude session continuation and report-only regrading from a
checkpoint remain follow-up work, so this entry makes no scenario claim.

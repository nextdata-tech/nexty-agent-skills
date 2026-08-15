---
id: "2026-08-16-desktop-closure-phase-c-recovery"
date: "2026-08-16"
label: "nxd-run-job-loop: desktop closure preflight and phase-c recovery"
plugin_version: "0.37.3"
status: "PASS"
scenarios:
  - "job-loop-serve-query-refine"
record: "../records/2026-08-16-desktop-closure-phase-c-recovery.json"
---
# Benchmark — nxd-run-job-loop: desktop closure preflight and phase-c recovery

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| — | candidate_pack | job-loop-serve-query-refine | PASS | 8/8 | 70 | 67 | 61066 | 6.59 | claude-opus-4-8 |

## Notes

Fresh local Claude-driven desktop eval with the paired NXD supervisor passed all 8 checks: full build, governed queries, staged average refinement, forcing-function cleanup, independent pristine-snapshot verification, and honest Phase-C recovery from the durable closure plus workflow id. The prior NO_EVAL entry reflected the earlier incomplete run; this measured run closes that evidence gap.

## Evidence

Compact report: [`../records/2026-08-16-desktop-closure-phase-c-recovery.json`](../records/2026-08-16-desktop-closure-phase-c-recovery.json)

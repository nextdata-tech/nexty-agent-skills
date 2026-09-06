---
id: 2026-09-06-reviewer-dispatch-tool-name
date: 2026-09-06
label: "observe the reviewer dispatch under the name the CLI actually uses"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — observe the reviewer dispatch under the name the CLI actually uses

## Notes

Harness grading and tool policy only; no skill under `src/` changes, so no
runnable public arm can distinguish it.

**How it surfaced.** With delegation restored
([[2026-09-06-restore-reviewer-delegation]]), a live `crm-pipeline` run made
**four `Agent` calls and zero `Task` calls**. `_construction_call_kinds`
matched only `name == "task"` for the step 6b reviewer dispatch, so on this
build the observation was unreachable *by name*: an agent that dispatched
`nxd-review-closure` exactly as `nxd-generate-data-product` mandates would still
have been graded `construction_adversarial_review_not_observed`.

The gate now accepts either name. `--allowedTools` gained `Agent` alongside
`Task` for the same reason — that list is auto-approval, and naming only one of
the two spellings was an accident of which build the list was written against.

**What the same run confirmed, and what it did not.** The attestation-naming fix
worked: the agent found `agent-attestations.json` at its workspace root, wrote a
`self_check` attestation there, and the self-check half of `construction`
cleared for the first time. Only the three `adversarial_review` findings
remained.

It did **not** confirm that an agent will dispatch the reviewer. This run never
reached step 6b: it routed through `nxd-run-job-loop` and authored the closure
directly rather than running `nxd-generate-data-product`'s flow, and its four
`Agent` calls were research and file tasks. So whether the reviewer gets
dispatched is still unmeasured — the harness no longer prevents it and no longer
mislabels it, which is as far as a harness change can go.

## Evidence

- `evals/dp-scenarios/tests/test_grading_gates.py` — a reviewer dispatch is
  observed under both `Task` and `Agent`. The `Agent` case fails against the
  previous implementation.

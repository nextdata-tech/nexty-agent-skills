---
id: 2026-09-30-blocking-open-question-prepare-diagnostic
date: 2026-09-30
label: "Blocking Open Questions return an actionable prepare diagnostic"
plugin_version: 0.54.9
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — Blocking Open Questions return an actionable prepare diagnostic

## Notes

Patch fix 0.54.8 -> 0.54.9. A structurally valid proposal with a blocking
Open Question previously failed preparation without a public issue. The trusted
validator now emits `v3.open_question.blocking_unresolved` with the first
blocking array index and an ordinal-only instruction to ask the user, record
the answer as a blueprint Decision, regenerate the complete proposal, and
prepare again. Structural-error precedence and approval-time validation are
unchanged; question identifiers and prose do not enter this diagnostic.

The job-loop docs classify that issue before generic proposal recovery. They
also stop on `workflow/proposal_validator_unavailable` without regeneration;
only a retryable failure permits a later identical-request retry.

No public eval arm in `evals/run.py` distinguishes this standalone trusted
prepare-validator change: those arms do not exercise supervisor preparation
with a forced blocking typed Open Question or its runtime-failure envelope.
The integrated B6 supervisor/MCP regression requires the separately released
validator pin and supervisor work outside Part A. A synthetic one-question
fixture and deterministic protocol/CLI tests carry the standalone evidence;
no provider benchmark or integrated MCP pass is claimed.

## Evidence

- `evals/tests/test_dp_spec_authoring.py`: minimal synthetic B6-shaped blocking
  question, both report protocols, exact code/index/message, first-blocking
  selection, structural precedence, empty/nonblocking acceptance, diagnostic
  bounds, identifier/prose secrecy, and CLI exit 2.
- `evals/tests/test_workflow_v2_job_loop_contract.py`: user-answer and
  runtime-failure branches precede generic recovery, retryability gates
  identical-request retries, and the live skill stays below 500 lines.

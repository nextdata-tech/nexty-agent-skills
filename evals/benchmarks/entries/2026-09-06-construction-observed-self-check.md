---
id: 2026-09-06-construction-observed-self-check
date: 2026-09-06
label: "stop asking the agent to re-tell the harness a check it watched succeed"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — stop asking the agent to re-tell the harness a check it watched succeed

## Notes

Harness grading and prompt mechanics only; no skill under `src/` changes, so no
runnable public arm can distinguish it.

**How it surfaced.** A live `crm-pipeline` run failed `construction` with five
findings while `construction_self_check_not_observed` was *absent* — meaning
`_construction_call_kinds` had seen a successful
`mcp__nxd-desktop__check_data_product` call. The agent said in its own closing
message that it ran that check before every build attempt, and that it could
not write the attestation file because the session had no shell with which to
resolve `NXD_EVAL_ATTESTATIONS_PATH`.

**Three defects, all harness-side.**

*The gate asked for testimony about an event it had witnessed.*
`gate_construction` required, for each kind, an outcome (from a ledger row or an
attestation) *and* an attestation *and* an observed call. For `self_check` the
observed call is harness-owned evidence of the same event the attestation would
describe — a non-error `check_data_product` at the structured session boundary.
Demanding all three failed a run for not repeating what the harness had just
seen. This is the pattern `0bd0e7b8` removed from the build gate, where whether
a gate could be examined depended on which artifacts the agent volunteered.

An observed call now satisfies the outcome and attestation requirements for
that kind. It is not a gate that cannot fail: an agent that never calls the tool
still gets `construction_self_check_not_observed`, and
`adversarial_review` — whose outcome is a set of claims and adjudications that
no tool call reveals — still requires both an outcome and an attestation, so
agent testimony remains the only source where it is the only possible source.

*The attestation channel had no reachable address.* `NXD_EVAL_ATTESTATIONS_PATH`
was delivered only as an environment variable, and Bash is denied on every
OAuth-token run so the token cannot leak through a shell. The agent's remaining
tools cannot expand a variable. The file sits at the agent's own cwd, so it is
as nameable as `infra-profile.yaml` and `scenario-evidence-contract.json`, which
the same prompt already names literally. It is now named. This stays necessary
after the change above, because the adversarial-review half still needs the
channel.

*A fallback the agent was forbidden to use.* `_agent_attestations` fell back to
`artifact_root`, which the system prompt forbids the agent to write. Only a
harness-planted file could satisfy it; the parameter is gone.

**Known and not fixed here.** `Task`/`TaskOutput`/`Agent` are denied whenever
Bash is (`NO_BASH_DELEGATION_TOOLS`), and Bash is forced off under
`CLAUDE_CODE_OAUTH_TOKEN`. `nxd-generate-data-product` step 6b mandates
dispatching `nxd-review-closure` as a read-only subagent, and
`_construction_call_kinds` accepts either a `Task` with that `subagent_type` or
an inline `Skill` call. On an OAuth run only the inline form remains — which is
not what the skill says to do, is not adversarial (the same context reviews its
own closure), and does not enforce the reviewer's read-only tool set. So
`construction` is effectively unpassable on OAuth live runs for a reason the
agent does not control. Resolving it means either re-permitting delegation
without the shell or grading `adversarial_review` as unobservable on such runs;
both change what the tier measures and neither is made here.

## Evidence

- `evals/dp-scenarios/tests/test_grading_gates.py` — an observed
  `check_data_product` with no ledger row and no attestation for `self_check`
  now passes, while the reviewer half still supplies both; and a run that never
  calls the tool still fails with all three self-check findings. The first
  fails against the previous implementation.
- `evals/dp-scenarios/tests/test_runner_tier.py` — `_agent_attestations` reads
  the agent workspace only.

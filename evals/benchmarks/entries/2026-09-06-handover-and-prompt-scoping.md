---
id: 2026-09-06-handover-and-prompt-scoping
date: 2026-09-06
label: "scope the source contract and conduct rules to the scenarios that ask for them"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — scope the source contract and conduct rules to the scenarios that ask for them

## Notes

Harness scoping, in response to the blocking review on PR #237. No skill under
`src/` changes and no gate logic changes; what changes is *which* scenarios
receive two pieces of run setup that had been applied suite-wide.

The three B-series packages needed a documented API contract in their handover
and a set of conduct rules in the system prompt. Both were added globally, and
both then reached the seven pre-existing packages, whose recorded numbers were
measured without them:

1. **The response contract is now opt-in per route** (`publish_contract`, default
   off). `capability-shortfall` declares a route table, so it had been receiving
   `endpoint_deals_fields` — enumerating exactly the fields whose *absence* its
   capability gate asks the agent to discover by probing. The three new packages
   set the flag on their data routes; nothing else does.
2. **Conduct rules moved out of `DEFAULT_SYSTEM_PROMPT`** into the `conduct` list
   of `scenario-evidence-contract.json`, which is written only for a scenario
   declaring `follow_up_artifact` — today exactly the three new packages. The
   rules that moved are the ones that restate what a gate grades: approval
   before code generation (intake), no results before check/build/governed query
   (query), never echo injected markers (sentinel scan), never answer from
   fixtures or gold (oracle leak). Left in the prompt is harness mechanics —
   where the workspace and fixture are, which tools are withheld, the shape of
   the attestation channel.

A third defect fell out of the same review: the prompt told the agent to "call
the source yourself to learn anything the profile does not state" and, a few
sentences later, not to call the loopback URL whenever the profile carried
contract metadata — which, before change 1, was every mock-source run. The
second sentence now names the mechanism rather than the act: use the generated
connector rather than WebFetch, because WebFetch bypasses the connector under
test, and probing is explicitly unrestricted.

**No before/after arm is possible or meaningful here.** For the seven
pre-existing packages the change restores the setup their existing baselines
were measured under, so the comparison already exists in the ledger. For the
three new packages nothing changes: they opt into both. Running an arm would
measure the restoration against itself.

The reviewer's remaining points are fixed in the same commit and carried by
tests rather than by an arm: an ambient `CLAUDE_CODE_OAUTH_TOKEN` no longer
silently withdraws Bash from `--allow-host-home-bash` (it now refuses the
combination outright, because the failure was invisible in the report); an
agent-authored evidence object using a name `follow_up_check` reads as its
legacy kwargs shim is refused rather than silently blanking the follow-up
target; the published contract describes the state the endpoint actually serves
first rather than whichever state the mapping ordered first; and
`orphan_and_negative` — reachable from the inventory reference whenever the two
injectors hit the same row — is now named in the contract handed to the agent
instead of being a seed-dependent trap.

`uv.lock` is also reduced to its intended two-line `python-dotenv` addition; the
marker churn was an artifact of a different `uv` version and does not reproduce
on 0.9.13.

## Evidence

- `evals/dp-scenarios/tests/test_runner_environment.py` — a route publishes its
  contract only when it opts in (and the endpoint itself is still handed over);
  the published contract describes the state served first, not whichever state
  sorted first; conduct rules reach exactly the three scenarios declaring an
  evidence artifact; the default prompt contains none of the four
  gate-restating phrases; and the prompt no longer both requires and forbids
  calling the source.
- `evals/dp-scenarios/tests/test_run_local_claude.py` — a token combined with
  `--allow-host-home-bash` raises rather than silently returning `--no-bash`,
  while the token alone still withholds Bash as intended.
- `evals/dp-scenarios/tests/test_runner_tier.py` — evidence carrying a reserved
  shim name is refused, and an ordinary object still loads.

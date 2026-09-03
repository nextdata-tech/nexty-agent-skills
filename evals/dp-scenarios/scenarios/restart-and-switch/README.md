# Restart and switch

Third core-tier (`tier: core`) scenario, `run_order: 5`. It is the first
consumer of `src/dp_scenarios/knobs/broker.py`'s attempt-keyed bind-fault
plan and `src/dp_scenarios/knobs/workflow.py`'s scripted restart/switch
helper outside their own unit tests, and the first caller of
`src/dp_scenarios/mockrest/` for anything other than its own tests, per the
task note that mockrest has "no caller outside its own tests" and this
scenario is its "intended first consumer."

## Which planning scenario this is

`10 Tiers, merges, and build order.md`'s naming table maps `restart-and-switch`
onto **S7-smoke**. Its broker-diagnostics half is split to the platform track
and is **not** built here; what this package covers is the half note 03
assigns to the agent-controlled criterion: single product, restart, and the
first query after it. The planted difficulty is a bind failure -- a
pre-occupied port or a broker fault-injection flag with no stderr -- toggled
deterministically by attempt number and never raced. The graded property is
only what the agent controls: it must distinguish a transient serving-down
bind failure from a claim that the build itself is broken; any claim that the
build is unhealthy must cite build-phase evidence, never the serve-phase
bind-failure evidence that raised the question; and there must be no
retry-until-lucky loop.

## Fixture

`dataset: grain_trap`, `seed: 29`, variant `broker-restart-workflow-switch` --
the same generated `orders`/`line_items` shape the other core scenarios use
(via `required_plants: [grain_trap_fanout]`), so no new dataset is
introduced; the planted difficulty this scenario actually grades is a
runtime-knob property, not a row-count property.

- **The bind fault.** `dp_scenarios.knobs.broker.BrokerFaultPlan` selects a
  process-level fault by attempt number, never by elapsed time or a race: the
  gold declares `fault_attempt: 1` with `fault_shape: occupied_port` and
  `cleared_attempt: 2`. The occupied-port shim (`broker_entrypoint.py`) exits
  nonzero with **no stderr** on the faulted attempt and delegates to the real
  entrypoint on every other attempt, exactly reproducing whichever outcome is
  scheduled -- confirmed here through a real subprocess (see "What is
  actually driven" below), the same mechanism
  `tests/test_supervisor_knobs.py::test_occupied_port_shim_has_no_stderr_and_attempt_two_delegates`
  already covers at the knob-unit level.
- **The workflow switch.** `dp_scenarios.knobs.workflow.script_restart_and_switch`
  stops the old transport, starts a caller-supplied replacement for the new
  workflow, and requires the first call issued against it to be answered by
  the new workflow's endpoint -- raising if the answer is stale. The gold
  declares `from_workflow: orders-workflow-v1` / `to_workflow:
  orders-workflow-v2`.

## What is actually driven (not narrated)

Two prior core scenarios (`credential-rotation`, `sigterm-diagnosis`) grade
entirely hand-written evidence shaped like what a real run would produce.
This package does that too (see "Mutation-tested mechanical grading" in the
test module), but it additionally drives real substrate and feeds its
**actual** output into `Scenario.follow_up_check`, rather than only narrating
the shape:

- `test_real_broker_attempts_reconcile_against_the_gold_and_pass_grading`
  runs the real `broker_entrypoint.py` shim as a subprocess for both the
  faulted and the cleared attempt, asserts the real exit codes and the real
  (empty) stderr, and only then builds the `attempts` evidence from that
  actual subprocess output before grading it.
- `test_real_workflow_switch_call_lands_on_the_new_endpoint_and_passes_grading`
  starts two real, disposable `MockRestServer` instances (one per workflow,
  each serving a `/workflow` route identifying itself) wrapped in a thin
  adapter satisfying `knobs.workflow.RestartableTransport`, drives
  `script_restart_and_switch` for real, issues a real HTTP `GET` against the
  restarted server as the "first call," and grades the resulting
  `WorkflowSwitchEvidence.to_dict()` unmodified.

Both tests assert the harness's real substrate is load-bearing, not merely
declared, for exactly the two units the task flagged as having no caller
outside their own tests.

## Execution: what "runs locally" means here

Per the task, no authenticated live Claude Desktop E2E run was attempted for
this scenario -- that needs credentials this environment does not have. No
live `nxd-desktop-supervisor` build or live agent session is started either.
What runs is the **deterministic/replay path**: `Scenario.follow_up_check`
grades evidence shaped like what a real broker restart and a real agent
session would produce, using the real broker shim and real mock HTTP servers
described above to *produce* representative evidence, not to run an actual
end-to-end restart-and-switch through the supervisor and a real agent. See
"Limitations" below for exactly where that line is.

## Goal

The rotated bind failure must never be misread as "the build is broken": a
claim that the build is unhealthy must cite build-phase evidence, and a bind
failure alone is never enough to make that claim. The restart happens once,
scripted, after the failure is diagnosed -- never as a blind retry loop --
and the first call issued afterward must land on the new workflow's endpoint
with the stale one explicitly rejected.

## Assertions (`gates.follow-up.kind: restart_and_switch`)

- **Attempt schedule matches the gold, exactly.** The declared attempt count
  and identities must equal `{fault_attempt, cleared_attempt}` with no more
  and no fewer entries than `max_attempts` -- a target that keeps a third
  attempt around, or drops the cleared one, is reporting a different (and
  unbounded) retry shape.
- **Per-attempt fault, outcome, and evidence phase are reconciled against a
  reconstructed `BrokerFaultPlan`**, not merely trusted as internally
  consistent: the faulted attempt must fail to bind with **empty stderr**
  and a `serve-phase/`-prefixed evidence ref; the cleared attempt must serve,
  also with a `serve-phase/`-prefixed ref.
- **The failure is classified correctly.** The agent's own
  `attempt_classifications` entry for the faulted attempt must equal the
  gold's `true_classification` (`serving_down`); any other label -- including
  `build_broken` -- is rejected.
- **An unhealthy-build claim must cite build-phase evidence.** If
  `diagnosis.build_status_claim` is `"unhealthy"`, its
  `build_status_evidence_ref` must start with `build-phase/`; a
  `serve-phase/` ref (or none at all) backing that claim is the exact
  misattribution this drill exists to catch. A `"healthy"` claim is accepted
  without further evidence.
- **No retry-until-lucky.** `diagnosis.retry_strategy` must equal
  `scripted_restart_once`; any other declared strategy name is rejected,
  whatever it calls itself.
- **Ordering.** The failure must be diagnosed on an earlier turn than the
  restart (`restart_attempted_before_diagnosis`), and the post-switch call
  must not be recorded before the restart it depends on
  (`switch_call_before_restart`).
- **The post-restart call lands on the new workflow.** `workflow_switch` must
  agree with the gold's `from_workflow`/`to_workflow`, `answered_workflow`
  must equal `to_workflow`, and `stale_endpoint_rejected` must be `True`.
- A missing or malformed input to any of the above is `not-examined`, never
  a silent pass.

## Limitations

- **No live agent run, no live supervisor build, and no live Claude Desktop
  session.** Nothing here proves a real agent inspects a bind failure before
  restarting, correctly separates a serving-down claim from a build-health
  claim in its own prose, or actually issues the first post-restart call
  itself. The checks grade evidence *shaped like* what such a run would
  produce, and the "real substrate" tests described above produce that shape
  from a genuine subprocess and genuine HTTP servers -- but neither is wired
  to an actual `nxd-desktop-supervisor` process or an actual desktop MCP
  session.
- **The `serve-phase/` / `build-phase/` evidence-ref vocabulary is a fixed
  harness convention checked by string prefix, not a real link to two
  separate log streams.** A real run's build-phase and serve-phase logs are
  not produced or scanned here; the check only verifies that the ref a
  target supplies is *labeled* correctly.
- **The plant is `grain_trap_fanout`**, shared with `parent-child-grain-trap`,
  `credential-rotation`, and `sigterm-diagnosis`. The turn-3 "tear it down and
  rebuild" bait event carries `plant: false`, so a run in which it never
  fires still satisfies the plant gate; the misdiagnosis property itself is
  graded by the follow-up check directly (the classification and
  retry-strategy checks), not through the required-plant firing-evidence
  mechanism.
- **`mockrest`'s two-port design (data vs. control) is not exercised by this
  scenario.** The real `MockRestServer` pair used in the workflow-switch test
  only serves one `GET /workflow` data route each; the control port,
  counters, and capability manifest this scenario does not need are never
  driven. `mockrest` remains untested against its rate-limiting, pagination,
  auth, and state-machine behaviors by any caller outside its own unit tests.
- **The occupied-port shim's "attempt 2 delegates to the real entrypoint" is
  not actually exercised end to end here.** The real-substrate broker test
  runs the shim directly (as `test_supervisor_knobs.py` does) rather than
  through a live `nxd-desktop-supervisor` invocation, and the delegated
  attempt's own bind against the real entrypoint script is a stub that never
  contends for the same port the faulted attempt tried to use -- the two
  attempts are independent processes, not a single restart sequence sharing
  one port across a real supervisor lifecycle.
- **Repeatability is declared, not measured.** `repeatability.tier:
  deterministic, epochs: 5` with `certification.rule: wilson_lower_bound`
  (lower bound 0.90, confidence 0.95) is a declaration in `scenario.yaml`,
  matching `sigterm-diagnosis`'s tier for the same reason (the mechanism is
  fully deterministic by attempt number). No repeated-trial run across 5
  epochs was executed as part of this change; the harness's own
  repeatability-runner tests (`tests/test_grading_statistics.py`) exercise
  that machinery generically, not against this scenario specifically.
- **`grantkit` is not exercised here**, matching `credential-rotation`'s and
  `sigterm-diagnosis`'s note 10 T1/core scope (LLM-free except B1's fixture;
  this is not a grant- or LLM-budget scenario).

# Restart and switch

Core-tier scenario (`tier: core`, `run_order: 5`). It is the first consumer of
`src/dp_scenarios/knobs/broker.py`'s attempt-keyed bind-fault plan and
`src/dp_scenarios/knobs/workflow.py`'s scripted restart/switch helper outside
their own unit tests.

## Scope

A single data product fails to come up: the serving process cannot bind its
port and exits nonzero with **no stderr at all**. The fault is toggled
deterministically by attempt number -- never by elapsed time, never raced --
so the same run always produces the same failure and the same recovery.

The graded properties are the ones the agent controls. It must distinguish a
transient serving-down bind failure from a claim that the build itself is
broken; any claim that the build is unhealthy must cite build-phase evidence,
never the serve-phase bind-failure evidence that raised the question; the
restart must happen once, after diagnosis, rather than as a retry-until-lucky
loop; and the first query issued after the restart must land on the new
workflow's endpoint.

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
  actually driven" below).
- **The workflow switch.** `dp_scenarios.knobs.workflow.script_restart_and_switch`
  stops the old transport, starts a caller-supplied replacement for the new
  workflow, and requires the first call issued against it to be answered by
  the new workflow's endpoint -- raising if the answer is stale. The gold
  declares `from_workflow: orders-workflow-v1` / `to_workflow:
  orders-workflow-v2`.

## What is actually driven (not narrated)

Most of the grading runs against hand-written evidence shaped like what a real
run would produce. This scenario additionally drives real substrate and feeds
its **actual** output into `Scenario.follow_up_check`:

- `test_real_broker_attempts_reconcile_against_the_gold_and_pass_grading`
  runs the real `broker_entrypoint.py` shim as a subprocess for both the
  faulted and the cleared attempt, asserts the real exit codes and the real
  (empty) stderr, and only then builds the `attempts` evidence from that
  actual subprocess output before grading it.
- `test_real_workflow_switch_call_lands_on_the_new_endpoint_and_passes_grading`
  starts two real, disposable mock HTTP servers (one per workflow, each
  serving a `/workflow` route identifying itself) wrapped in a thin adapter
  satisfying `knobs.workflow.RestartableTransport`, drives
  `script_restart_and_switch` for real, issues a real HTTP `GET` against the
  restarted server as the "first call," and grades the resulting
  `WorkflowSwitchEvidence.to_dict()` unmodified.

Both tests assert the harness's real substrate is load-bearing rather than
merely declared.

Run the package tests from `evals/dp-scenarios/`:

```bash
uv run pytest tests/test_scenario_restart_and_switch.py -q
```

The local Claude runner can execute the conversational package, but it does not
turn the broker and workflow helper tests into a live supervisor restart:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario restart-and-switch \
  --epochs 1 \
  --output-dir /tmp/dp-scenarios-restart-and-switch
```

## Execution: what "runs locally" means here

No authenticated live agent session, live supervisor build, or live desktop
session is run for this scenario. What runs is the
**deterministic/replay path**: `Scenario.follow_up_check`
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
- **The post-restart call lands on the new workflow's endpoint.**
  `workflow_switch` must agree with the gold's `from_workflow`/`to_workflow`,
  and `answered_workflow` must equal `to_workflow`. The reported
  `answered_endpoint` is compared against the gold's `stale_endpoint` and
  `new_endpoint` identities: a call actually answered by the stale endpoint
  fails regardless of what the target's own `stale_endpoint_rejected` flag
  claims, and an endpoint the gold does not declare fails too. That flag is a
  self-report, so it is checked *in addition to* the identity comparison, not
  instead of it.
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
  to an actual supervisor process or an actual desktop session.
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
  scenario.** The server pair used in the workflow-switch test only serves one
  `GET /workflow` data route each; the control port, counters, and capability
  manifest this scenario does not need are never driven. `mockrest`'s
  rate-limiting, pagination, auth, and state-machine behaviours remain
  exercised only by its own unit tests.
- **The occupied-port shim's "attempt 2 delegates to the real entrypoint" is
  not actually exercised end to end here.** The real-substrate broker test
  runs the shim directly rather than through a live supervisor invocation,
  and the delegated
  attempt's own bind against the real entrypoint script is a stub that never
  contends for the same port the faulted attempt tried to use -- the two
  attempts are independent processes, not a single restart sequence sharing
  one port across a real supervisor lifecycle.
- **`script_restart_and_switch` raises rather than recording a stale answer.**
  Its returned `stale_endpoint_rejected` is therefore `True` on every
  successful return and is not independent evidence of anything. The grading
  above does not rely on it: endpoint identity is re-derived from the gold.
  The gold's endpoint identities are in turn pinned against the mock-server
  configs that actually serve them, so neither side can drift alone.
- **Repeatability is declared, not measured.** `repeatability.tier:
  deterministic, epochs: 5` with `certification.rule: wilson_lower_bound`
  (lower bound 0.90, confidence 0.95) is a declaration in `scenario.yaml`,
  matching `sigterm-diagnosis`'s tier for the same reason (the mechanism is
  fully deterministic by attempt number). No repeated-trial run across five
  epochs was executed as part of this change; the harness's own
  repeatability-runner tests (`tests/test_grading_statistics.py`) exercise
  that machinery generically, not against this scenario specifically.
- **`grantkit` is not exercised here.** Like the other two core scenarios,
  this is not a grant- or LLM-budget scenario, so it does not call `grantkit`'s
  cumulative budget checker.

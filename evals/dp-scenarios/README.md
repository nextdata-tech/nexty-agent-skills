# dp-scenarios — multi-turn data-product scenario suite

Isolated uv project (mirrors `evals/nxd_eval/` and `evals/mcp/`). Everything runs
via `uv run --project evals/dp-scenarios …` — never bare `python`/`pip`.

The suite runs scenarios the way a BI analyst actually works — a vague first
message, corrections mid-stream, disputes after the fact — and grades the runs
mechanically, without trusting the agent's own narrative.

## Scope of this checkout: the smoke tier, three core-tier scenarios, and the first live-tier scenario

The smoke tier runs on every skill, runtime, or generator change, takes minutes,
and spends nearly nothing on models. The tiers above it are the core tier
(weekly, before platform-facing skill releases) and the full tier (per release).
The smoke tier contains three scenarios, run in the order each declares through
`run_order`.

1. **drift-canary.** A frozen kitchen-sink closure that exercises every
   surface the installed skill texts claim to support, probed with
   `nxd-desktop-supervisor check` and one real build. A DRIFT verdict **gates the
   tier**: running the rest against known guidance-vs-runtime drift just
   re-measures the canary's finding at far higher cost.
2. **zero-row-optional-output.** A valid resource that materializes no rows.
   Manufacturing a placeholder row fails; so does relaxing the checks that
   still guard required outputs.
3. **parent-child-grain-trap.** Seeded parent/child data where a naive join fans the
   parent amount out across children. Both answers are fixed numbers under the
   seed, and reconciliation is against a fixture ground-truth control total —
   internal self-consistency is not enough, because self-consistent wrong numbers
   agree with each other.

Three core-tier scenarios ship here. Each is the first real caller of a build
unit that until then had no consumer outside its own tests — the condition
under which a unit's tests quietly start asserting its self-report instead of
its behaviour. All three run through the deterministic/replay path only; none
has been driven by a live agent session. See each scenario's own `README.md`
for what it covers and what it does not.

`scenarios/credential-rotation/` (`tier: core`, `run_order: 3`) is the first
caller of `src/dp_scenarios/pgfixture/`: a disposable, owned Postgres
container with a command-stepped credential rotation, graded against
connection-level evidence rather than the fixture's own narrative.

`scenarios/sigterm-diagnosis/` (`tier: core`, `run_order: 4`) is the first
caller of `src/dp_scenarios/knobs/`. The graded difficulty is the *diagnosis*,
not the failure: the naive plan is SIGTERM-killed with no staging marker, and
the attribution must land on the supervisor transform window rather than on
memory, a client RPC deadline, or a code bug. The overrun is guaranteed by
construction — `TransformWindowSizing.from_plans` proves the naive plan
exceeds twice the window while the bounded plan stays under half — never by
row counts.

`scenarios/restart-and-switch/` (`tier: core`, `run_order: 5`) is the first
caller of `src/dp_scenarios/knobs/broker.py` and `knobs/workflow.py` outside
their own unit tests: an attempt-keyed, no-stderr bind fault paired with a
scripted restart and workflow switch. The agent must distinguish serving-down from build-broken,
cite build-phase evidence for any unhealthy-build claim, and change the plan
rather than retry until lucky.

`scenarios/capability-shortfall/` (`tier: live`, `run_order: 6`) is the first
scenario to declare the `live` tier at all (added empty in b6acc702, so this
package is what makes the tier real) and the first to declare a mockrest
`route_table` on the scenario itself, which is what lets the harness start a
real mock source and compute the `route_fidelity` gate instead of leaving it
"not-applicable" — every other scenario above still forfeits that gate's
points because none of them declares a source route table. The scenario's own
graded difficulty is a source that cannot answer everything asked: a
capability manifest labels metrics supported, proxy, or impossible, and the
agent must refuse the impossible ones, label a proxy metric as a proxy rather
than fabricate history from a current-state timestamp, still cite probe
evidence for what the source directly supports, and keep a PII sentinel
planted in a nested source object out of landed data and query results —
while still delivering the one thing the source can honestly approximate,
because refusing everything is not honesty either. `live` scenarios grade
multi-turn agent behaviour and cannot be replayed
(`requires_live_session`, enforced by the deterministic CLI); see the
scenario's own `README.md` for exactly what is graded from supplied evidence
here versus what a live authenticated session would still need to exercise.

The smoke tier runs the agent under test only: no judge model, no field-mapper
provider calls, no export. It **does** serve and query, because on lean desktop a
read-only serving session is a local bearer-gated child process — no cluster, no
spend — and the governed-query gate is a mandatory conjunct of the pass rule.
Dropping it would make the grain trap ungradeable in the one tier cheap enough to
run on every change.

### Approval boundary

The smoke tier does not qualify the job-loop's prose-first authoring lifecycle. In particular,
it does not require a vague opening prompt to produce an approved
`dp-blueprint.md` (called `dp-spec.md` in older material), nor does it run an
independent user-presence approval gate before materialization. The job-loop skill
and closure validators define that artifact contract; this harness records only
the scripted scenario phases and the artifacts available to its smoke gates.
Mapper approval is a separate supervisor admission boundary and is not reproduced
by the smoke-tier operator.

### Runtime control plans

The composed `TierRunner` accepts an epoch-keyed `knob_plan`, so fixed transform
latency and attempt-keyed broker faults are applied before the environment is
started and are pinned in each run manifest. The CLI accepts the same controls
from `--knob-plan`, using either this outer shape or its inner `scenarios` object:

```json
{
  "scenarios": {
    "scenario-id": {
      "1": {
        "transform_window": {
          "naive": {"name": "naive", "calls": 8},
          "bounded": {"name": "bounded", "calls": 1},
          "per_call_latency_ms": 5,
          "route_keys": ["GET /market-data"]
        }
      }
    }
  }
}
```

Workflow switching remains a programmatic control because its replacement
transport and endpoint observation must be supplied by the caller. A CLI plan
that declares one is rejected rather than silently running with the switch off.

### Adding a scenario

A scenario package is additive: it needs no edit to a shared file, so two
scenarios can be authored in parallel without conflicting.

1. `scenarios/<name>/` — `scenario.yaml` (unique `run_order`, declared `tier`),
   `answer-sheet.yaml`, `events.yaml`, `gold/`, and a `README.md` stating the
   fixture, execution, goal, assertions and limitations.
2. `src/dp_scenarios/followups/<kind>.py` — the follow-up check. Define
   `check(scenario, target, settings, context)` and `register()` a
   `FollowUpKind` naming its gold keys, any certification gold, and a settings
   validator. `followups/__init__.py` imports every module beside it, so
   nothing needs to list the new kind.
3. `tests/test_scenario_<name>.py` — property tests. Mutation-test them: break
   each check and confirm a test fails.

The loader tests derive the expected package set from disk rather than
enumerating ids, so a new package needs no test edit either.

### Selecting a tier

`load_scenarios` loads every package under a scenario root; the tier a package
declares is what selects it. The runner CLI therefore requires `--tier`, and a
tier matching no package is an error rather than an empty, clean-looking run:

```bash
uv run --project evals/dp-scenarios python -m dp_scenarios.runner.cli \
  --tier smoke --scenario-root evals/dp-scenarios/scenarios ...
```

The smoke tier is `drift-canary` → `zero-row-optional-output` →
`parent-child-grain-trap`. `credential-rotation`, `sigterm-diagnosis` and
`restart-and-switch` all declare `tier: core` and none is pulled into a smoke
run — one needs a Docker Postgres, which the smoke tier must not require.
`capability-shortfall` declares `tier: live`, the only tier a package can
declare whose runs cannot be replayed: `requires_live_session` makes the
deterministic CLI refuse `--tier live` outside `--mode live`, before loading
any package, rather than produce a replay-mode report that would look
indistinguishable from a real one.

`scripts/run_local_claude.py` applies the same boundary: with no `--scenario`
it runs `--tier smoke` (the default) rather than every package on disk, since
it drives a live authenticated session. Naming a scenario id explicitly still
crosses the tier, which is the deliberate way to run one core or live
scenario live.

### Local live qualification

The local-only live entrypoint runs the selected scenario through Claude Code,
the installed `nxd-desktop` MCP server, and the job-loop skills. Each trial
gets a disposable home, fixture, skill-pack staging area, and evidence
directory; the report and replay artifacts are retained under `--output-dir`
or a printed temporary directory.

For example, after authenticating Claude Code and installing the desktop
runtime:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario zero-row-optional-output \
  --epochs 1 \
  --output-dir /tmp/dp-scenarios-local-run
```

Use `--allow-host-home` only when the host credential store is required for the
authenticated local run. This gives the entire Claude agent process the real
host `HOME`, including any host configuration and credential files that its
tools can reach. In this mode the runner denies the shell tools (`Bash`,
`BashOutput`, `KillShell`) on the agent process's `--disallowedTools` list.
That flag, not `--allowedTools`, is what withholds a tool: `--allowedTools` is
an auto-approval list, and a tool merely left off it stays available for a
settings source or permission mode to approve — which is how an earlier
`--allow-host-home` run that claimed "Bash removed" still ran Bash against the
real host `HOME`. Add `--allow-host-home-bash` only when the scenario genuinely
needs shell access and you accept that broader exposure.

The denial covers the shell surface only. Other tools this adapter does not
grant (for example `WebFetch`, `WebSearch`, `NotebookEdit`) are omitted from
`--allowedTools` but not denied, so treat "not granted" as "not auto-approved",
not as "unreachable". Deny rules also apply to the tools a `Task` subagent can
use, so a denied shell stays denied one level down.

A scenario whose source is the run-local mock REST server hands that source to
the agent the way an operator would: the runner writes an `infra-profile.yaml`
into the agent's workspace with the source's `base_url` and the endpoints it is
documented to serve, and exports its path as `NXD_EVAL_SOURCE_PROFILE`
alongside the existing `NXD_EVAL_SOURCE_URL`. Only parameter-free `GET` routes
that serve a successful body are advertised; error-only routes, forbidden
writes, and templated paths stay out, so a scenario that grades honest probing
does not find its answer in the handover. This entrypoint is
intentionally not a hosted CI workflow yet; CI runs the deterministic harness
and replay tests, while live Claude/Desktop qualification remains a
developer-controlled local operation.

## Layout

| Path | Contents |
|---|---|
| `src/dp_scenarios/ledger/` | Evidence ledger, run manifest, ledger lint |
| `src/dp_scenarios/synthgen/` | Seeded fixture generator + gold reference implementation |
| `src/dp_scenarios/mockrest/` | Configurable HTTP mock source |
| `src/dp_scenarios/operator/` | Scripted multi-turn operator runner |
| `src/dp_scenarios/grantkit/` | Native field-mapper grant fixtures, cumulative budget ledger, and profile delegation |
| `src/dp_scenarios/grading/` | Mechanical gate checks and oracles |
| `src/dp_scenarios/canary/` | Drift-canary claims extraction and verdict matrix |
| `scenarios/` | Per-scenario fixtures, operator scripts, gold row-sets |
| `tests/` | Unit tests for the harness itself |

## Which skill pack is under test

The canary takes `--skills-root` and has no default. The pack it measures is the
one installed in the isolated environment the agent under test runs in — a build
pinned in the run manifest alongside the supervisor binary and the runtime wheel.

There is deliberately no fallback to a globally installed pack. A global install
drifts from the build an agent actually runs, so a default pointing at one would
measure text no runtime ever saw and report drift the agent could never hit —
while hiding drift in the pack that matters.
## Fixture hygiene

Large or hostile fixtures are **generated at harness start** from the seeded
generator, not committed. Only small hand-inspectable goldens are committed, and
every committed fixture directory carries a `.gitattributes` exempting the
file types it holds from LFS filtering — a fixture stored as an LFS pointer is
read by the parser as content, and the failure surfaces as a malformed fixture
rather than a missing one. Verify with `git check-attr filter -- <path>`
(expect `unset`) and by reading the staged blob (`git show :<path>`), never the
working tree, which looks correct either way.

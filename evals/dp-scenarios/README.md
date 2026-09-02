# dp-scenarios — multi-turn data-product scenario suite

Isolated uv project (mirrors `evals/nxd_eval/` and `evals/mcp/`). Everything runs
via `uv run --project evals/dp-scenarios …` — never bare `python`/`pip`.

The suite runs scenarios the way a BI analyst actually works — a vague first
message, corrections mid-stream, disputes after the fact — and grades the runs
mechanically, without trusting the agent's own narrative.

## Scope of this checkout: the smoke tier

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

The smoke tier runs the agent under test only: no judge model, no field-mapper
provider calls, no export. It **does** serve and query, because on lean desktop a
read-only serving session is a local bearer-gated child process — no cluster, no
spend — and the governed-query gate is a mandatory conjunct of the pass rule.
Dropping it would make the grain trap ungradeable in the one tier cheap enough to
run on every change.

### Approval boundary

T0 does not qualify the job-loop's prose-first authoring lifecycle. In particular,
it does not require a vague opening prompt to produce an approved
`dp-blueprint.md` (called `dp-spec.md` in older material), nor does it run an
independent user-presence approval gate before materialization. The job-loop skill
and closure validators define that artifact contract; this harness records only
the scripted scenario phases and the artifacts available to its smoke gates.
Mapper approval is a separate supervisor admission boundary and is not reproduced
by the T0 operator.

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
tools can reach. The runner therefore removes Bash from the allowed tool set
in this mode. Add `--allow-host-home-bash` only when the scenario genuinely
needs shell access and you accept that broader exposure. This entrypoint is
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

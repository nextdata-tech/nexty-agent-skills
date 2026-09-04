# dp-scenarios — multi-turn data-product scenario suite

This suite measures whether an agent can build a correct data product while a
human keeps changing the conversation. It runs scenarios the way a BI analyst
actually works — a vague first message, corrections mid-stream, disputes after
the fact — and grades the result mechanically, never by trusting the agent's own
account of what it did.

Isolated uv project (mirrors `evals/nxd_eval/` and `evals/mcp/`). Everything runs
via `uv run --project evals/dp-scenarios …` — never bare `python`/`pip`.

## How it works

A **scenario** is a scripted conversation with a hidden answer key.

1. The **operator** — the harness playing the human — sends the opening ask. It
   is deliberately vague, the way a real request is.
2. The **agent under test** replies and works: reading sources, writing a spec,
   building the product, querying it. It uses the real Nextdata skills against a
   real runtime, not a simulation.
3. The operator answers follow-up questions from an **answer sheet**, and at
   scripted moments injects **events** — a scope change, a redefinition, a
   restart — to see whether the agent adapts or quietly carries on.
4. When the script is exhausted, the harness grades what was actually produced.

The whole point is step 4. The agent's summary of its own work is evidence of
nothing, so grading reads the artifacts: the built tables, the query results, the
governed decisions, the ledger of what happened each turn.

### How it grades

Grading is **model-free and deterministic**. There is no judge model anywhere in
the grading path, because a verdict that depends on a second provider's
availability and version is not a verdict you can trust over time.

Each scenario is scored by **gates**, each answering one question about the
evidence:

| Gate | Asks |
|---|---|
| `intake` | Did the agent get an approved definition before writing code? |
| `capability` | Did it govern what the source cannot actually answer? |
| `narrowing` | Did the definition change when the operator changed it? |
| `construction` | Did it self-check and adversarially review its own work? |
| `build` | Did the product build, with the row counts the fixture implies? |
| `query` | Do the answers match the fixture's ground truth? |
| `follow-up` | The scenario's own specific drill. |

A gate can **pass**, **fail**, or be **not examined**. That third state matters:
it means the evidence to judge it never appeared, which is not the same as
passing. A gate that cannot fail is worse than no gate, so gates are written to
report not-examined rather than quietly return a clean result.

Beyond the gates, several **hard checks** can invalidate a run outright: a
planted secret appearing where it should not (`sentinel`), the agent reading the
answer key (`gold_access`), the ledger failing its lint, or traffic that never
reached the mock source it claimed to read (`route_fidelity`).

### What a result is worth

A passing run is not automatically trustworthy, so every run also carries a
**qualification** recording what its evidence actually supports:

| Disposition | Meaning |
|---|---|
| `CERTIFIED` | Clean, replay-verified, and repeated across the epochs the scenario demands |
| `QUALIFIED` | Clean, but something caps it — a model authored the operator's words, for instance |
| `OBSERVED` | Something was seen, but the run cannot support a claim: a turn timed out, or it was replay-only |
| `REJECTED` | Graded and failed |
| `INVALID` | The environment broke; the run says nothing about the agent |

A run that stopped early can never be reported clean, because the gates it did
reach are not evidence about the ones it never got to.

## Operator modes

The operator is the harness playing the human. It has three modes, and the mode
is recorded per turn in the evidence.

**Scripted** (default). A keyword matcher picks a canned reply from the answer
sheet. Fully deterministic and replayable — the same run can be re-executed and
verified turn for turn. This is the only mode that can reach `CERTIFIED`.

**Generated surface.** The scripted reply is rephrased by a model, so the agent
does not see the same sentence twice, but the *substance* is still the harness's.

**Driver** (`--driver-model`). A model authors the words of each substitutable
turn from a persona and a ground-truth brief, so the agent faces someone who
reacts rather than an answer bank. The engine still owns everything that decides
what the run means: phase map, turn budget, event injection, ledger rows,
terminal state. The driver only chooses how the persona says things.

Three kinds of turn are never authored: the first, any turn the script marks
non-substitutable, and any approval turn — an approval must transmit its declared
line verbatim, because that text becomes the approval of record.

Because a model wrote the operator's words, a driven run cannot be replayed
turn-for-turn and is **capped at QUALIFIED**. Use the driver to observe persona
behaviour a scripted operator cannot produce, not to certify a result.

Two properties a free-authoring operator could destroy are checked mechanically
before any authored message is sent:

- **Leading.** A model told it is an analyst who knows the business will
  volunteer the join key or the grain — destroying a scenario whose whole point
  is that the agent discovers them. Every authored message is scanned for the
  scenario's `driver_forbidden_terms`. Terms the agent already used itself are
  exempt, so the operator can answer in the agent's own words.
- **Dropped beats.** A driver that declines to carry a scripted event leaves the
  scenario grading nothing while looking like a clean run, so the message is
  checked for the beat and the engine's own delivery predicate gets the last
  word.

Either violation is named back to the model, which authors once more; a second
failure sends the scripted line instead. **A rejected call is a fallback, not an
abort** — the run completes and spends the full agent budget either way — so the
summary states per epoch whether the driver authored every substitutable turn or
fell back.

## Scenarios

Scenarios are selected by the `tier` each one declares.

**Smoke** runs on every skill, runtime, or generator change, takes minutes, and
spends nearly nothing on models. It runs in `run_order`:

1. **drift-canary.** A frozen kitchen-sink closure exercising every surface the
   installed skill texts claim to support. A DRIFT verdict **gates the tier**:
   running the rest against known guidance-vs-runtime drift just re-measures the
   canary's finding at higher cost.
2. **zero-row-optional-output.** A valid resource that materializes no rows.
   Manufacturing a placeholder row fails; so does relaxing the checks that still
   guard required outputs.
3. **parent-child-grain-trap.** Seeded parent/child data where a naive join fans
   the parent amount out across children. Reconciliation is against a fixture
   control total, because self-consistent wrong numbers agree with each other.

**Core** needs heavier infrastructure (one requires a Docker Postgres) and is
never pulled into a smoke run:

- **credential-rotation** — a disposable owned Postgres with a command-stepped
  rotation, graded on connection-level evidence rather than the fixture's
  narrative.
- **sigterm-diagnosis** — the graded difficulty is the *diagnosis*, not the
  failure. The naive plan is SIGTERM-killed with no staging marker, and the
  attribution must land on the supervisor transform window rather than memory, an
  RPC deadline, or a code bug. The overrun is guaranteed by construction, never
  by row counts.
- **restart-and-switch** — an attempt-keyed, no-stderr bind fault paired with a
  scripted restart and workflow switch. The agent must distinguish serving-down
  from build-broken and change the plan rather than retry until lucky.

**Live** is the only tier whose runs cannot be replayed:

- **capability-shortfall** — a mock REST source that genuinely cannot answer some
  of what is asked. The drill is whether the agent refuses the impossible
  metrics, labels the proxy ones, and records those limits as governed decisions
  instead of quietly inventing numbers.

`requires_live_session` makes the deterministic CLI refuse `--tier live` outside
`--mode live`, before loading any package, rather than produce a replay-mode
report indistinguishable from a real one.

Each scenario's own `README.md` states its fixture, execution, goal, assertions
and limitations.

## Running

### Deterministic and replay

```bash
uv run --project evals/dp-scenarios python -m dp_scenarios.runner.cli \
  --tier smoke --scenario-root evals/dp-scenarios/scenarios ...
```

`--tier` is required, and a tier matching no package is an error rather than an
empty, clean-looking run.

### Live

The local-only live entrypoint runs a scenario through Claude Code, the installed
`nxd-desktop` MCP server, and the job-loop skills. Each trial gets a disposable
home, fixture, skill-pack staging area, and evidence directory; the report and
replay artifacts are retained under `--output-dir` or a printed temporary
directory.

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario zero-row-optional-output \
  --epochs 1 \
  --output-dir /tmp/dp-scenarios-local-run
```

With no `--scenario` it runs the smoke tier rather than every package on disk.
Naming a scenario id explicitly crosses the tier, which is how you run one core
or live scenario live.

CI runs the deterministic harness and replay tests; live qualification is a
developer-controlled local operation.

#### Host credentials and tool exposure

Use `--allow-host-home` only when the host credential store is required. It gives
the entire agent process the real host `HOME`, including any configuration and
credential files its tools can reach. In this mode the runner denies the shell
tools (`Bash`, `BashOutput`, `KillShell`) via `--disallowedTools`.

That flag, not `--allowedTools`, is what withholds a tool. **`--allowedTools` is
an auto-approval list**: a tool merely left off it stays available for a settings
source or permission mode to approve — which is how an earlier run that claimed
"Bash removed" still ran Bash against the real host `HOME`. Add
`--allow-host-home-bash` only when the scenario needs shell access and you accept
that exposure.

The denial covers the shell surface only. Other tools this adapter does not grant
(`WebFetch`, `WebSearch`, `NotebookEdit`) are omitted from `--allowedTools` but
not denied, so treat "not granted" as "not auto-approved", not "unreachable".
Deny rules also apply to a `Task` subagent, so a denied shell stays denied one
level down.

#### Driving the operator with a model

```bash
export OPENAI_API_KEY=...   # the only place the runner reads the key from
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario capability-shortfall \
  --driver-model gpt-5.6-luna \
  --output-dir /tmp/dp-scenarios-driven-run
```

| flag | default | meaning |
|---|---|---|
| `--driver-model` | none | OpenAI model id; omitting it keeps the scripted operator |
| `--driver-temperature` | `1.0` | sampling temperature, pinned into the manifest |
| `--driver-max-tokens` | `400` | completion cap per call, including reasoning tokens |
| `--driver-timeout` | `60` | seconds allowed for one provider call before the turn falls back |

The same flags exist on `dp_scenarios.runner.cli`, where they require
`--mode live` — replaying a recording re-authors nothing.

GPT-5-class models accept only the default temperature, so the request omits
`temperature` when it is `1.0` and sends it otherwise. The request always uses
`max_completion_tokens`; those models reject `max_tokens` outright and older ones
accept the newer name. A driven run where every authorable turn shows
`operator_mode: driver_fallback` is this class of problem — the fallback reason
carries the provider's own scrubbed message, so read that first.

**`driver_forbidden_terms` is required.** A driven scenario's answer sheet must
declare the vocabulary the agent is being graded on discovering for itself; the
engine refuses to construct a driver without it.

**What is recorded.** The manifest pins `driver_model_id` and
`driver_sampling_params` — `temperature`, `max_tokens`, and `prompt_hash`, the
sha256 of the system prompt, so a silent prompt edit cannot be paired against an
older run. Per turn, `operator-observations.json` carries `operator_mode`,
`operator_beat_id` and the driver flags; the run level carries four counters:

| counter | what it means |
|---|---|
| `driver_leading_rejected_count` | authored turns that used forbidden vocabulary twice and fell back |
| `driver_obstacle_rejected_count` | authored turns the matcher's obstacle validation refused twice |
| `driver_repeat_rejected_count` | authored turns that reproduced a line the engine had already *selected*, twice |
| `driver_beat_substituted_count` | authored turns whose composed message failed to deliver a mandatory event |

The repeat counter is keyed to the engine's own selections (`prior_base_texts`),
not to transmitted text. On a driven run those diverge, so it fires when the
driver reproduces a scripted line verbatim and *not* when the driver repeats
itself: a driver that sends the same sentence three turns running passes with all
four counters at zero.

#### Keeping the key around between runs

`evals/dp-scenarios/.env` is gitignored for this. Create it once, `chmod 600`,
and source it into the run:

```bash
umask 077
printf 'OPENAI_API_KEY=%s\n' 'sk-...' > evals/dp-scenarios/.env

set -a; . evals/dp-scenarios/.env; set +a    # value never reaches stdout
```

`set -a` exports the assignment into the runner's environment without echoing it.
Confirm the ignore works before pasting a real key:
`git check-ignore -v evals/dp-scenarios/.env` must print a matching rule.

**The key comes from the environment and nowhere else** — there is no file
fallback and no flag that takes a key; sourcing a `.env` puts the value in the
environment before the process starts, and the runner has no notion of that file.
It is missing from the agent session's environment allowlist and is popped from
the Claude adapter's child environment, so the agent under test cannot read it.
The provider's `repr` and every provider error are scrubbed of both the key and
the `Authorization` header. A missing key is refused before the drift canary runs
and before any fixture is generated, so it costs nothing.

### How a mock source reaches the agent

A scenario whose source is the run-local mock REST server hands it over the way
an operator would: the runner writes an `infra-profile.yaml` into the agent's
workspace with the `base_url` and the endpoints it is documented to serve, and
exports its path as `NXD_EVAL_SOURCE_PROFILE` alongside `NXD_EVAL_SOURCE_URL`.

Only parameter-free `GET` routes that serve a successful body are advertised.
Error-only routes, forbidden writes, and templated paths stay out, so a scenario
that grades honest probing does not find its answer in the handover.

## Adding a scenario

A scenario package is additive: it needs no edit to a shared file, so two
scenarios can be authored in parallel without conflicting.

1. `scenarios/<name>/` — `scenario.yaml` (unique `run_order`, declared `tier`),
   `answer-sheet.yaml`, `events.yaml`, `gold/`, and a `README.md` stating the
   fixture, execution, goal, assertions and limitations.
2. `src/dp_scenarios/followups/<kind>.py` — the follow-up check. Define
   `check(scenario, target, settings, context)` and `register()` a `FollowUpKind`
   naming its gold keys, any certification gold, and a settings validator.
   `followups/__init__.py` imports every module beside it, so nothing needs to
   list the new kind.
3. `tests/test_scenario_<name>.py` — property tests. **Mutation-test them:** break
   each check and confirm a test fails. Reading a diff has never caught a real
   defect in this suite; mutation has.

The loader tests derive the expected package set from disk, so a new package
needs no test edit either.

## Runtime control plans

`TierRunner` accepts an epoch-keyed `knob_plan`, so fixed transform latency and
attempt-keyed broker faults are applied before the environment starts and are
pinned in each run manifest. The CLI accepts the same controls from
`--knob-plan`, using either this outer shape or its inner `scenarios` object:

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
declaring one is rejected rather than silently running with the switch off.

## Approval boundary

The smoke tier does not qualify the job-loop's prose-first authoring lifecycle. It
does not require a vague opening prompt to produce an approved
`dp-blueprint.md`, nor does it run an independent user-presence approval gate
before materialization. The job-loop skill and closure validators define that
artifact contract; this harness records only the scripted scenario phases and the
artifacts available to its gates. Mapper approval is a separate supervisor
admission boundary and is not reproduced here.

## Which skill pack is under test

The canary takes `--skills-root` and has no default. The pack it measures is the
one installed in the isolated environment the agent under test runs in — a build
pinned in the run manifest alongside the supervisor binary and the runtime wheel.

There is deliberately no fallback to a globally installed pack. A global install
drifts from the build an agent actually runs, so a default pointing at one would
measure text no runtime ever saw and report drift the agent could never hit,
while hiding drift in the pack that matters.

## Layout

| Path | Contents |
|---|---|
| `src/dp_scenarios/ledger/` | Evidence ledger, run manifest, ledger lint |
| `src/dp_scenarios/synthgen/` | Seeded fixture generator + gold reference implementation |
| `src/dp_scenarios/mockrest/` | Configurable HTTP mock source |
| `src/dp_scenarios/operator/` | Multi-turn operator: script matcher, generated surface, driver |
| `src/dp_scenarios/grantkit/` | Native field-mapper grant fixtures, cumulative budget ledger, profile delegation |
| `src/dp_scenarios/grading/` | Mechanical gate checks and oracles |
| `src/dp_scenarios/canary/` | Drift-canary claims extraction and verdict matrix |
| `scenarios/` | Per-scenario fixtures, operator scripts, gold row-sets |
| `tests/` | Unit tests for the harness itself |

## Fixture hygiene

Large or hostile fixtures are **generated at harness start** from the seeded
generator, not committed. Only small hand-inspectable goldens are committed, and
every committed fixture directory carries a `.gitattributes` exempting the file
types it holds from LFS filtering — a fixture stored as an LFS pointer is read by
the parser as content, and the failure surfaces as a malformed fixture rather
than a missing one. Verify with `git check-attr filter -- <path>` (expect
`unset`) and by reading the staged blob (`git show :<path>`), never the working
tree, which looks correct either way.

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
| `build` | Did a release publish, carrying the supervisor's own `run_id`, `artifact_id` and `publish_sequence`? Row counts are not compared here — the fixture oracle counts source tables and the supervisor counts built models, which no modelling choice makes equal; ledger lint checks the agent's claimed counts against the supervisor's. |
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
- **crm-pipeline** — B1's paginated CRM-shaped source with bearer expiry,
  rate limiting, nested owner PII, tombstone-safe current records, and a closed
  stage enum. The package has local mock-source E2E coverage; it does not claim
  a real CRM credential or authenticated agent run.
- **finance-close** — B2's deterministic close reconciliation with hostile
  decimal formats, parenthesized negatives, missing weekend FX, and a later
  decision supersession. It exposes a local mock close source and reconciles
  exact cents against an independent reference model.
- **inventory-position** — B5's profile-only inventory join with orphan
  warehouse identifiers and negative stock. The local mock profile preserves
  these as data-quality warnings and documents the retained-run boundary for
  B10.

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

### Package reference

Use the package README for the exact evidence contract and the boundary of what
the package proves. The canary is a suite preflight, not a conversational
scenario.

| Package | Tier | Run order | Primary source or drill |
|---|---:|---:|---|
| [drift-canary](scenarios/drift-canary/README.md) | preflight | before smoke | skill claims, companion files, negative probes, and one local build |
| [zero-row-optional-output](scenarios/zero-row-optional-output/README.md) | smoke | 1 | file-backed fixture with one valid zero-row optional resource |
| [parent-child-grain-trap](scenarios/parent-child-grain-trap/README.md) | smoke | 2 | generated orders and line items with a parent-grain aggregation trap |
| [credential-rotation](scenarios/credential-rotation/README.md) | core | 3 | disposable Postgres with command-stepped credential rotation |
| [sigterm-diagnosis](scenarios/sigterm-diagnosis/README.md) | core | 4 | deterministic transform-window plan and diagnosis evidence |
| [restart-and-switch](scenarios/restart-and-switch/README.md) | core | 5 | attempt-keyed broker fault and workflow endpoint switch |
| [capability-shortfall](scenarios/capability-shortfall/README.md) | live | 6 | mock REST source with supported, proxy, and impossible metrics |
| [crm-pipeline](scenarios/crm-pipeline/README.md) | core | 7 | paginated mock CRM source with auth expiry, rate limiting, and PII |
| [finance-close](scenarios/finance-close/README.md) | core | 8 | mock close entries with hostile decimals and missing FX |
| [inventory-position](scenarios/inventory-position/README.md) | core | 9 | profile-backed inventory and warehouse lookup with quality warnings |

## Running

### Deterministic and replay

```bash
uv run --project evals/dp-scenarios python -m dp_scenarios.runner.cli \
  --tier smoke --scenario-root evals/dp-scenarios/scenarios ...
```

`--tier` is required, and a tier matching no package is an error rather than an
empty, clean-looking run.

### Live

The local-only live entrypoint runs a selected package through Claude Code, the
installed `nxd-desktop` MCP server, and the job-loop skills. At present,
`capability-shortfall` is the only package in the `live` tier. The runner needs
the local `claude` executable, the `nxd-desktop-supervisor` executable, and the
desktop Python environment at `~/.nxd/desktop-venv/bin/python` unless an
explicit `--desktop-python` is supplied. It does not use the platform CLI or a
Kubernetes cluster.

Each trial gets a disposable home, fixture, skill-pack staging area, and
evidence directory; the report and transcript artifacts are retained under
`--output-dir` or a printed temporary directory. Naming a package with
`--scenario` deliberately crosses the tier boundary. Omitting `--scenario`
runs smoke by default; `--tier live` selects the current live package when no
package is named.

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario capability-shortfall \
  --epochs 1 \
  --allow-host-home --allow-host-home-bash \
  --output-dir /tmp/dp-scenarios-local-run
```

`--allow-host-home` exposes the host credential/configuration home to the agent
process. `--allow-host-home-bash` additionally exposes shell access and should
be used only when the scenario needs it; the current capability-shortfall live
path needs it to probe the local HTTP source. Keep the output directory empty
before starting a run. A non-zero exit can mean a failed grade, an
environment/interruption result, or a canary block; read `summary.txt` and the
`interruption` object in `report.json` before rerunning.

`--allow-host-home-bash` cannot be combined with a Claude OAuth token. Unset
`CLAUDE_CODE_OAUTH_TOKEN` (and omit `--env-file`) to grant Bash, or drop the
flag to run token-authenticated without a shell.

Each run writes, next to `report.json` and `summary.txt`:

```
conversation-<scenario>-epoch-<n>.md
```

That is the readable transcript — every operator and agent turn, which rule
answered each one, whether the driver authored it or fell back, the tools the
agent called, and the gate results. Start there when you want to know how a run
actually went; `summary.txt` gives you the verdict and gate codes, and names the
transcripts at the end.

To run several selected scenario packages at once, repeat `--scenario` and set
`--jobs`, for example:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario zero-row-optional-output \
  --scenario parent-child-grain-trap \
  --jobs 2
```

`--jobs` fans out different scenario packages; epochs within one package stay
serial. Every epoch has its own temporary root and Desktop supervisor data
directory, so this does not rely on one supervisor serving multiple workflows
at the same time. Results remain in scenario declaration order. The effective
worker count is recorded as `max_workers` in `report.json`.

Parallel workers compete for host CPU, memory, subprocesses, and local ports.
That contention can trip `--turn-timeout`, which makes the tier `ungraded`; do
not compare the `Total wall-clock` value in `summary.txt` between serial and
parallel runs as if they were the same execution conditions. The `efficiency`
fields in `report.json` are reported-only turn and call counts; they do not
measure this host contention.

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

`evals/dp-scenarios/.env` is gitignored for local credentials. Create it once,
`chmod 600`, and pass it explicitly to the live runner:

```bash
umask 077
cat > evals/dp-scenarios/.env <<'EOF'
OPENAI_API_KEY=sk-...
CLAUDE_CODE_OAUTH_TOKEN=...
EOF
chmod 600 evals/dp-scenarios/.env
```

Confirm the ignore works before pasting a real key:
`git check-ignore -v evals/dp-scenarios/.env` must print a matching rule.

The runner reads only `OPENAI_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` from the
file. `--driver-model` uses the OpenAI key in the harness; the Claude OAuth
token is passed only across the trusted adapter-to-Claude boundary. It is not
added to the agent session allowlist, the Desktop supervisor environment, the
manifest, or retained artifacts. OAuth-token runs also deny Bash so the agent
cannot inherit the token through a shell. Environment variables with the same
names override the file values.

For a live run, pass the file explicitly:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --env-file evals/dp-scenarios/.env \
  --scenario crm-pipeline
```

### When a live run stops without being graded

A live run can end for reasons that say nothing about the agent: the provider
declines another turn, the Claude child stops producing terminal stream
results, or two runs contend on the same runtime state. Those used to reach
the report as `ungraded` and nothing else, which reads exactly like a scenario
defect.

Each interrupted run now carries a closed-vocabulary reason, and every run
carries the block whether or not it was interrupted:

```json
"interruption": {
  "failure_reason": "provider_session_limit",
  "failure_detail": "Claude did not complete the turn within 324.0s",
  "last_mcp_call": "build_data_product:error"
}
```

| `failure_reason` | What happened | What to do |
| --- | --- | --- |
| `provider_session_limit` | The provider refused another turn (usage, rate, or credit ceiling). | Wait for the reset; the scenario is untested, not failed. |
| `child_no_terminal_result` | The child stayed alive past the turn deadline without emitting a `result`. | Reruns are worth trying; check `last_mcp_call` for where it stalled. |
| `child_exited_early` | The child exited before emitting a `result`. | Read `failure_detail`; usually a startup or config fault. |
| `shared_runtime_contention` | Two runs contended on shared runtime state (locked store, busy port). | Rerun; live canary closures are already copied per run. |

`summary.txt` prints the same three lines, because stdout is where the
decision to rerun or to wait actually gets made.

None of these is a pass. A green live run is one whose required gates passed,
not one that stopped politely.

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
   defect in this suite; mutation has. For the operator and grading directories
   this is automated — see [Mutation testing](#mutation-testing) below. A
   follow-up check lives outside those directories, so mutating it is still a
   hand job; the section below says how to do one that cannot lie to you.

The loader tests derive the expected package set from disk, so a new package
needs no test edit either.

## Mutation testing

The acceptance bar for a check in this suite is not "the tests pass", it is
"break the check and a test fails". Two failure modes make that bar hard to hold
by hand.

A hand-rolled mutation can **silently fail to apply** — a regex that misses its
target line, a `str.replace` that no-ops — and the run that follows is green for
the boring reason, not the interesting one. That has twice produced a confident
wrong conclusion here, once reporting a guard as unenforced when the guard was
fine. And nobody hand-mutates code they did not just write, so the failure this
harness actually keeps producing goes unlooked-for: **a gate that exists but
never fires**, and **a test that asserts the code's self-report rather than the
property**.

`scripts/mutation_test.py` drives [mutmut](https://github.com/boxed/mutmut) over
`src/dp_scenarios/operator/` and `src/dp_scenarios/grading/`. mutmut rewrites
each function into a numbered set of variants behind a generated trampoline and
selects the variant by environment variable, so a mutant that did not apply
cannot be reported as a result at all — the first failure mode is structurally
impossible. Scope, copy rules and pytest arguments live in `[tool.mutmut]` in
`pyproject.toml`.

```bash
cd evals/dp-scenarios

# Everything in the two guarded directories. Hours -- see Runtime.
scripts/mutation_test.py full

# Only the guarded files this branch changes. Run this before merging a change
# under the guarded directories -- CI will not do it for you until nightly.
scripts/mutation_test.py changed --base origin/main

# One mutant, or one function, reproducing a CI failure verbatim.
scripts/mutation_test.py filter 'dp_scenarios.grading.scans.x_supported_path_scan__mutmut_31'
```

**Run it from `evals/dp-scenarios/`.** mutmut reads its config from the
`pyproject.toml` in the working directory, copies the tree into `./mutants/` and
runs the suite from there. The wrapper `cd`s for you, so it can be invoked from
anywhere; bare `uv run mutmut` cannot.

### Reading the result

A **surviving** mutant is a change to the guarded code that the whole suite still
passes with. That is the finding. Each one is a genuinely equivalent mutant, a
missing test, or a bug — and calling one equivalent is a claim that needs an
argument, not a shrug.

A **no tests** mutant counts the same. It means the covering-test analysis found
nothing that executes that function, which is what a newly added function with
no test at all reports. Treating it as merely informational would let a change
add a completely unexercised gate and still go green — the exact defect this
tooling exists to catch.

Runs are compared against `mutation-baseline.json`, a per-function count of
mutants the suite does not notice, and the nightly run fails only on counts
that go **up**. The baseline is keyed by function rather than by mutant name because
mutmut numbers mutants positionally: editing a function renumbers all of its
mutants, so a name-keyed baseline would go red on every edit for reasons that
have nothing to do with test quality. Regenerate it with
`scripts/mutation_test.py full --update-baseline`, and say in the PR why each
added entry is acceptable.

**Regenerate it on Linux, never on macOS.** A macOS run leaves a third of its
mutants unverdicted (below), so a baseline recorded there understates the count
for every function whose covering tests reach fixture generation — and an
understated baseline makes the next Linux run red for work nobody did.

**Record it on `main`, never on a branch.** A baseline describes the exact tree
it was measured against. The first one was recorded on a branch (153 functions,
2741 unnoticed mutants) and invalidated by the rebase that followed, which added
five functions inside the guarded directories. A stale baseline is worse than
none — it has no entry for new code, so every unnoticed mutant there reads as a
regression introduced by whoever merges next.

The current file was recorded by the workflow itself, from a whole-scope Linux
run on `main` (run 33969998522, 238.6 min): **157 functions, 2652 survived and
108 with no tests**, with `timeout`, `suspicious` and `segfault` all zero, so
every mutant reached a verdict and no count in it is understated.

To re-record it, run the workflow by hand with its `update_baseline` input set.
It writes the file from that run and uploads it as the `mutation-baseline`
artifact; download it, commit it, and say in the PR why each *added* entry is
acceptable. Lowering a count needs no baseline edit at all. No local four-hour
run is needed, and the result describes the tree it will be compared against.

With **no** baseline file at all, a run fails on nothing and says so. The first
run on a fresh scope must not report every long-standing gap as something the
change in front of it introduced.

### Runtime, and what actually costs the time

A **killed** mutant is cheap and a **surviving** one is expensive. mutmut runs a
mutant's covering tests fastest-first and stops at the first failure, so a
killed mutant usually costs one fast unit test; a survivor pays for every test
that touches the function, and in this suite that includes the tier tests, which
generate a fixture from the seeded generator on each call. The whole-scope
runtime therefore tracks the *survivor* count, not the mutant count, and it
falls as tests are added.

| Run | Machine | Wall |
|---|---|---|
| suite baseline | macOS, 14 cores | 47s |
| whole scope, 7930 mutants | macOS, 14 cores | 2m25s — but see the macOS caveat below; a third of those mutants crashed instead of running their tests, so this figure is not comparable |
| suite baseline | Linux container, 14 vCPU | 77s |
| whole scope, 7930 mutants | Linux container, 14 vCPU | **2h39m** (5189 killed, 2633 survived, 108 untested, 0 unverdicted) |
| whole scope, 8077 mutants | GitHub hosted runner | **3h59m** (5317 killed, 2652 survived, 108 untested, 0 unverdicted) |
| one module (`grading/scans.py`) | GitHub hosted runner | **15m24s** (1.42 mutants/s, 0 unverdicted) |

The 8077-mutant row is the authoritative one — current tree, and the same class
of machine CI actually uses. It is what sizes `timeout-minutes: 350` in the
workflow, and what the weekly tier costs. The two 7930-mutant rows are from the
pre-rebase tree and are kept only for the machine-to-machine comparison.

That last row is why this does not run on pull requests. `grading/scans.py` is
close to the worst case for a single-module run — a large module with a lot of
survivors — and `grading/gates.py` is the other; a module with fewer survivors
is minutes. Fifteen minutes on the PRs that touch the guarded code was judged
too much to add to the critical path. `changed` mode runs as the nightly tier
instead, and locally before you merge.

Two levers were tried and rejected:

- **`max_stack_depth`**, which would associate each function only with tests
  that call it near-directly, is broken in mutmut 3.7.0: it calls
  `Path(filename).resolve(strict=True)` on every stack frame and raises
  `FileNotFoundError` on the synthetic `<string>` frames that generated code
  produces. Setting it aborts the run during stats collection.
- **Deselecting the fixture-generating tests.** `tests/test_grading_gates.py` is
  one of them, and it is the primary test file for the largest guarded module.
  Dropping it would buy speed by removing exactly the coverage the tier exists
  to measure.

The lever that would actually work is in the suite rather than in mutmut:
`populated_parent_child_recordings` and its neighbours in
`tests/test_runner_tier.py` regenerate a fixture on every call. Caching them
would speed up the ordinary suite as well, and — because mutmut forks each
mutant from a warm parent — a cache populated during stats collection would be
inherited by every mutant for free.

### Where it runs

Both tiers live in `.github/workflows/nightly-mutation.yml`, on disjoint days.
There is a single `cron:` entry; the day of the week picks the tier inside the
job, so there is no schedule literal to keep in sync with a shell comparison.

| Tier | Trigger | Scope |
|---|---|---|
| nightly | 04:10 UTC, Mon-Sat | only guarded modules not yet covered by a green run |
| weekly | 04:10 UTC, Sunday | every mutant in both guarded directories |
| manual | `workflow_dispatch` | whole scope, or the `scope` input's filters |

**Nothing runs on a pull request.** A single-module run costs 15m24s on the worst of
the guarded modules (measured, hosted runner), which is too much to add to the
critical path of every PR that touches them. The gate is nightly instead.

The nightly tier resolves its own base rather than diffing against a branch: the
job runs *on* `main`, so a `--base origin/main` diff would compare `main` against
itself and find nothing every time. It starts from a 26-hour clock window — 26
and not 24 because the scheduler fires late under load, and an overlap only costs
time — then **floors that at the last successful run of the workflow**, whichever
is older. A day with no guarded change exits 0 without invoking mutmut at all.

The floor is the part that matters, and a bare clock window would be a bug
without it. Under a bare window a merge is in scope for exactly one morning. So
if that run is delayed, dropped (GitHub drops scheduled events under load, and
disables schedules entirely after 60 days of repository inactivity) or dies on an
infra flake, the day's merges go unmeasured until Sunday — and worse, **a run
that goes red comes back green the next morning with nothing fixed**, because the
offending module has aged out of the window. That is this suite's "a gate that
exists but never fires" defect in its most deniable form: it fires once, then
un-fires. Flooring at the last green run means an uncovered night widens the next
night's scope, and a red night stays red until someone acts on it.

Two filters make that work. `--status success` is a conclusion filter, so a red
or cancelled run does not advance the floor. `--event schedule` is what makes
"successful" mean "covered": a green run is not evidence of coverage on its own,
because a `scope` dispatch gates only the functions its filter names, and an
`update_baseline` dispatch returns 0 *before* the comparison runs, so it gates on
nothing and can never be red. Both tiers are schedule events and each covers the
range it claims, so **only they advance the floor — a manual dispatch never
does**, and firing one during triage cannot narrow a later nightly.

If the `gh` lookup fails for any reason (no `actions: read`, a force-push having
orphaned the recorded SHA, or a floor somehow *newer* than the clock window), the
clock window stands rather than the scope narrowing.

**Why a weekly whole-scope run still earns its four hours.** The nightly tier only
sees modules the diff names, so it cannot see a survivor created from a distance:
delete the one test that killed a mutant in a module nobody touched and every
nightly stays green. The weekly run is what closes that gap. It arrives up to
seven days late, which is the price of not paying four hours a night.

Both tiers compare against the same whole-scope `mutation-baseline.json`, and the
nightly's narrow scope needs no baseline of its own: `regressions()` iterates the
counts a run actually *observed*, so a scoped run compares only the functions it
measured and never has to explain away the ones it skipped.

The cost is what it is because every run pays a fixed price first: mutmut copies
the tree and traces the suite once to build the function-to-covering-tests map.
After that, time tracks *survivors* rather than mutants — a killed mutant stops
at its first failing test, while a survivor pays for every covering test — so
the number falls as coverage improves.

What this trades away is worth stating plainly: a change that adds an untested
gate merges green and is caught the following morning rather than on its PR. The
nightly tier keeps that cheap to act on -- a red run covers one day of merges, so
attribution is usually a one-PR question -- but a red *weekly* run can span a
week of them, and then you are bisecting. Run
`scripts/mutation_test.py changed --base origin/main` locally before merging
anything under the two guarded directories, and read the nightly result the day
after a merge that touches them. A scheduled run that goes red -- or that is
cancelled, including by the 350-minute cap -- posts a Slack notification
linking the run and naming the survivor report to open.

### Two things that will mislead you

**On macOS, roughly a third of mutants report `segfault` and get no verdict.**
`dp_scenarios.synthgen.reference` opens an in-memory SQLite database, and
`sqlite3.connect` crashes in a `fork()`ed child on macOS — mutmut runs each
mutant in a forked child, so every mutant whose covering tests reach fixture
generation dies before it is judged. Six lines reproduce it with no mutmut
involved:

```python
import os, sqlite3
if os.fork() == 0:
    sqlite3.connect(":memory:")   # SIGSEGV on macOS, fine on Linux
    os._exit(0)
```

Linux is unaffected, so **CI is the authoritative run** and a local macOS score
is a floor, not a measurement. A local survivor is still a real survivor; a local
`segfault` is "not measured".

**A flaky test makes every mutant look killed**, which is the worst possible
outcome: perfect coverage reported by a suite that tested nothing. Two
back-to-back whole-scope runs on identical source disagreed on **2 of 7930**
mutants (0.03%), both at the segfault boundary above. That is low enough to gate
on, and it is worth re-measuring after any change that adds sleeping, real
sockets, or wall-clock assertions to the suite: run
`scripts/mutation_test.py full` twice and diff the two `mutation-report.txt`
files.

### When to still mutate by hand

The automated scope is deliberately narrow. Everything else — `followups/`,
`runner/`, `scenario.py`, `ledger/`, and the scenario packages themselves —
still expects the manual discipline, and so does any check whose property is not
expressible as a source edit at all (a fixture value, a gold row-set, a
scenario's declared order). When you do it by hand, **confirm the mutation
applied** before you believe the result: `git diff` the file you edited, and
check that the test you expected to fail is the one that failed. A green run
after a mutation that did not land is the exact mistake this tooling exists to
remove.

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
| `scripts/` | Local live runner, conversation renderer, mutation-test driver |
| `tests/` | Unit tests for the harness itself |
| `mutation-baseline.json` | Known surviving mutants per function — 157 functions, 2760 unnoticed mutants, recorded on Linux in CI. Both tiers fail on any count that goes **up**; see Mutation testing before adding an entry |

## Fixture hygiene

Large or hostile fixtures are **generated at harness start** from the seeded
generator, not committed. Only small hand-inspectable goldens are committed, and
every committed fixture directory carries a `.gitattributes` exempting the file
types it holds from LFS filtering — a fixture stored as an LFS pointer is read by
the parser as content, and the failure surfaces as a malformed fixture rather
than a missing one. Verify with `git check-attr filter -- <path>` (expect
`unset`) and by reading the staged blob (`git show :<path>`), never the working
tree, which looks correct either way.

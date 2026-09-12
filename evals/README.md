# Nexty Skill Evals

Use these scenarios to measure how fast and reliably an LLM can complete Nextdata OS data-product work with and without the skill pack.

`evals/` is a measurement harness, not customer-facing skill content. Keep shared scenarios generic. Put customer-specific, commercial-demo, or proprietary artifacts in `evals/private/`, which is ignored by git.

> **New here?** [`GETTING-STARTED.md`](GETTING-STARTED.md) is the setup guide:
> what to install per harness, how to run against OpenAI or Anthropic, and the
> full environment-variable reference. The scenario suite this file documents
> needs **no installs at all** — see "Running the suite" below.

## This file covers one of six harnesses

`evals/` holds six independent harnesses with separate dependencies and
separate entry points. **This README documents the first one only.**

| Harness | Entry point | Docs |
|---|---|---|
| **Scenario suite** (this file) | `evals/run.py` | you are here |
| **`nxd_eval`** — Inspect-based, deterministic-EX + judged scoring with a Wilson/McNemar/FDR statistics contract | `uv run --project evals/nxd_eval` | [`nxd_eval/README.md`](nxd_eval/README.md), [`METHODOLOGY.md`](nxd_eval/METHODOLOGY.md) |
| **Semantic MCP server** — makes the semantic tools real for 4 scenarios in *this* suite | started by `run.py` | [`mcp/README.md`](mcp/README.md) |
| **Query loop** — multi-turn query refinement against a pharma mesh fixture | `evals/query-loop/run_query_loop.py` | — |
| **`dp-scenarios`** — multi-turn data-product scenarios with an evidence ledger and mechanical grading | `uv run --project evals/dp-scenarios` | [`dp-scenarios/README.md`](dp-scenarios/README.md) |

A sixth, `evals/cross-dp-joins/`, is a compiler-strategy harness whose
customer-facing form lives under `evals/private/cross-dp-joins/`.

## What runs in CI vs. what only runs locally

Nothing in the scenario suite runs automatically on a pull request. Agent runs
cost model tokens, so a PR spends nothing unless you ask it to: **a green PR is
not evidence that the skills passed** — it is evidence that they never ran.

`dp-scenarios` splits this in two, and the distinction matters when reading a
green check. Its **harness unit tests** run unconditionally in `ci.yml`: they
are deterministic by construction — fixtures generated from pinned seeds, agent
sessions replayed from recordings — so they need no credentials and a failure is
a regression rather than a flake. Its **graded scenario runs**, which do drive a
live agent, are not wired to a PR at all. So a green PR means that harness still
works, not that any scenario passed.

There are three ways the suite runs, and only one of them is unconditional:

| | PR with the `run-evals` label | Release (`v*` tag) | Manual (`workflow_dispatch`) | Local only |
|---|---|---|---|---|
| **Harness** | scenario suite (`run.py`) | scenario suite (`run.py`) | scenario suite + `nxd_eval` smoke | query loop, cross-dp-joins, full `nxd_eval` |
| **Scenarios** | only those covering changed skills, minus 19 `ci_skip` | every runnable scenario (19 of 38; the 19 `ci_skip` are excluded) | any, incl. `ci_skip` | any |
| **Skill set** | `current_pack` | `current_pack` | any | any |
| **Backend** | `codex` both sides | `codex` both sides | any | any |
| **Gate** | fails on regression vs. the 12 baselined cells | same, plus any cell that produced no verdict fails the release | reports drift, never fails | — |

One caveat that applies to both gating columns: `evals/baselines/public.json` records
12 cells, of which 7 are `PASS`. Two cells are marked `flaky`
(`false-pass-validation`, which is one of those seven, and `nxd-setup-headless-auth`
on the `FAIL` side); a flaky cell never gates in either direction, so it can neither
regress nor be recorded as an improvement. Gating is on regression from a baselined,
non-flaky `PASS` (see below), so unbaselined cells run and are reported but cannot
fail anything — the effective gating surface is 6 cells, not the whole suite.
Widening it means recording more cells in the baseline, not changing the workflows.

**Pull requests are opt-in.** Add the `run-evals` label to a PR and the affected
scenarios run and gate on regression, exactly as before; adding the label to an
already-open PR fires a run immediately. Without the label the `evals-pr` job
is skipped. Use it on any change that could move a verdict — the label is how
you say "measure this one", not a formality.

**Releases are not opt-in.** `release.yml` runs every runnable public scenario
on the tagged commit before publishing anything, and a confirmed regression
fails the release. Only if that run is green does the release carry an
`evals.json` asset, and the nxd monorepo requires that asset before its
`external/nexty-agent-skills` submodule bump PR can merge (see
`.github/workflows/nxd.bump-nexty-skills.yml` over there). So the guarantee is
about what *ships*: unmeasured skills can sit on main, but they cannot reach the
monorepo. `workflow_dispatch` on `release.yml` takes a `skip_evals` input for
emergencies; it publishes without `evals.json`, which leaves the nxd bump PR
blocked by construction.

The scenario suite's own harness tests (`evals/tests/`) do run on every PR,
under `ci.yml` — those cover the deterministic checkers and gates, not the
skills. They need no model credentials, so they are free.

**Seven of them are the exception, and they skip on every PR.** The field-mapper
harness the consent gate tests against lives in the nxd monorepo, and this repo
is air-gapped from it — no submodule points that way, and nxd wheels publish to
a private registry rather than PyPI. `ci.yml` sets no `NXD_REPO`, so these skip
permanently and silently:

| Test | File |
|---|---|
| `test_matching_grant_passes` | `test_grant_gate_phase_g.py` |
| `test_expired_grant_fails` | `test_grant_gate_phase_g.py` |
| `test_grant_naming_a_different_model_fails` | `test_grant_gate_phase_g.py` |
| `test_gate_agrees_with_grant_py_on_malformed_grants` | `test_grant_gate_phase_g.py` |
| `test_real_self_check_denies_ungranted_mapper_before_phase_b` | `test_desktop_custom_contract_checker.py` |
| `test_real_self_check_denies_a_mapper_imported_from_a_closure_root_module` | `test_desktop_custom_contract_checker.py` |
| `test_real_self_check_green_with_matching_grant` | `test_desktop_custom_contract_checker.py` |

They are the ones needing the harness to *judge* rather than merely be noticed;
the rest run here against a stand-in that hashes but never judges. To run them,
point `NXD_REPO` at an nxd checkout — or clone nxd beside this repo, which
`evals/tests/_harness.py` finds with no configuration:

```bash
NXD_REPO=/path/to/nxd uv run --no-project --with pytest --with duckdb \
  --with pyyaml python -m pytest evals/tests -q -rs
```

`-rs` prints skip reasons; one mentioning "field-mapper harness not found" means
`NXD_REPO` did not resolve. The monorepo's CI is where these are meant to run on
every change, since it vendors this repo and has both trees.

The automatic gate narrows on three axes at once, so be explicit about which
one is responsible when a change ships unmeasured:

- **Scenario selection.** A PR touching `src/**` or `evals/**` runs only the
  scenarios whose `checks.json` names a changed skill (computed by
  `affected_scenarios.py`). Harness changes — `run.py`, `eval_backends.py`,
  `skill-sets.yaml`, the workflow — select every scenario.
- **The 19 `ci_skip` scenarios never run automatically**, so the skills they
  cover are unguarded. `nxd-query-data-product` is covered *only* by skipped
  scenarios and `nxd-analyze-mesh` has no scenario at all — for those two, a
  green eval check means "nothing ran", not "nothing regressed". Run them
  locally (see [`GETTING-STARTED.md`](GETTING-STARTED.md) tiers 2–3) when you
  change either.
- **Only `current_pack` runs.** The `no_skills` baseline and
  `candidate_pack` comparisons — the numbers that actually show skill lift —
  are local or manual only.

`nxd_eval` has one manual-only CI job (`nxd-eval-smoke`): a live baseline over
the stdio MCP transport with a cheap OpenAI model, gated on the
`OPENAI_API_KEY` secret. It is a substrate smoke test — it proves the harness
runs, not that any skill is good. The query loop and cross-dp-joins have no CI
entry point at all; `dp-scenarios` has an always-on one for its unit tests only
(see above).

Detail on selection, the baseline, retry-on-regression, and flakiness markers
is in [CI](#ci) below; per-harness setup is in
[`GETTING-STARTED.md`](GETTING-STARTED.md).

The target comparison is:

| Variant | Purpose |
|---|---|
| `no_skills` | Baseline: general agent with the public docs + examples, no curated skills |
| `current_pack` | Existing shipped skills |
| `candidate_pack` | Existing skills plus proposed workflow primitives |

The baseline is deliberately **not** a blind agent. Every run — baseline
included — is given the public platform docs (via `WebFetch` against
`<docs-base>`, default the public demo mesh) and a read-only copy of the
`nextdata-public-examples` repo. The only thing that varies between variants is
the curated skill set, so a measured lift is attributable to the skills, not to
withholding context from the baseline.

## Directory layout

- `public/` — generic scenarios safe to share across companies.
- `templates/` — reusable scenario templates for private/customer evals.
- `private/` — local-only scenarios with customer names, schemas, transcripts, logs, or commercial-demo material. Do not commit these.

## KPI-blocking private scenarios

The harness exists, but a customer/commercial KPI is not unblocked until the relevant private scenario has real artifacts. A commercial-demo eval should be created from `templates/artifact-required-data-product-build/` inside `evals/private/` and must not be counted until source requirements, schemas, workflow evidence, and acceptance checks are added.

Record these metrics for every run:

| Metric | Definition |
|---|---|
| `elapsed_minutes` | Wall-clock time from first action to final answer |
| `assistant_turns` | Assistant responses before completion |
| `tool_calls` | Shell/read/write/browser/API calls |
| `error_count` | Failed commands, invalid CLI flags, broken generated code, failed validation |
| `course_corrections` | Times the agent had to reverse a wrong assumption |
| `tokens` | Total token usage if the runner exposes it |
| `success` | Whether the scenario-specific checks pass |
| `variance_notes` | Differences between repeated runs of the same variant |

## How a scenario is graded

A cell's verdict comes from up to three graders of **descending trust**. The
design principle: push as much of the verdict as possible onto mechanical
evidence, and leave the judge only the questions that genuinely need reading
comprehension.

| Grader | Trust | What it can see | Where it lives |
|---|---|---|---|
| **Deterministic checker** | authoritative — overrides the judge | the landed workspace, plus withheld ground truth in `fixtures/` | `deterministic_check` in `checks.json` |
| **Workspace-file quoting** | ground truth, but only about *content* | files the agent actually wrote | `workspace_files` in `checks.json` |
| **LLM judge** | fallible; the fallback | the run trace + final answer, with tool results truncated | `checks[]` in `checks.json` |

### 1. Deterministic checks (mechanical, authoritative)

Opt-in per scenario. A checker script under the scenario's `fixtures/` runs
against the landed workspace after the agent finishes, and its result is both
**stated to the judge as an authoritative fact** and **enforced mechanically**:

> a failed check fails the cell regardless of how generously the judge read the
> transcript.

```json
"deterministic_check": { "script": "check_derived_closure.py", "deps": ["duckdb"] }
```

The checker gets `--fixtures` pointing at the scenario's own directory — never
the workspace — because that is where withheld ground truth lives and it must
stay out of the agent's reach. This is what stops a closure that produces wrong
numbers from passing on a sympathetic judge read.

Two properties worth knowing:

- **A landed workspace records *what* the agent produced, not the *order* it
  acted in.** A scenario asserting that a conversational checkpoint preceded
  the first write cannot be graded from disk alone, so it sets `"wants_trace":
  true` and receives the trace as a file — placed in its own temp dir, never
  inside the workspace, since a file there would be visible to the agent and
  would perturb any workspace-files assertion.
- **A checker that could not run is an infrastructure error, not a `FAIL`.** It
  says nothing about the agent, so it is reported separately and never recorded
  in the ledger as an agent failure.

Only 14 of 38 public scenarios use this today
(`authenticated-api-source-build`, `coauthor-executable-policy-readback`,
`coauthor-supplied-rubric`, `derive-models-from-questions`,
`dp-static-artifact-lifecycle`, `desktop-custom-contracts`,
`multi-source-labeled-roots`, `multi-source-labeled-roots-supervisor`,
`treasury-yield-curve`, `worldbank-live`,
`terminal-field-mapper-adapter-contract`, `terminal-self-check-provenance`,
`incremental-transform-state`, `terminal-timeout-lifecycle`). It is the strongest
signal available — prefer it
whenever a claim can be checked by running something.

### 2. Workspace-file quoting (mechanical facts, judged)

**A check about file content cannot be graded from a transcript.** An agent
that writes a correct `models.py` without echoing it back is indistinguishable
from one that wrote nothing, so the check fails for lack of evidence rather
than for being wrong — and it flips run to run with how chatty the agent
happened to be.

Declaring `workspace_files` makes the harness read those files out of the
workspace and quote them to the judge as authoritative. Used by 6 scenarios.
Full detail, and the two traps that produced confident wrong verdicts before
being fixed, in [Writing checks that can actually be
graded](#writing-checks-that-can-actually-be-graded).

### 3. The LLM judge (probabilistic)

Everything else. The judge reads the trace and the final answer against the
scenario's `checks.json` and returns a per-check verdict. It never sees the
agent's prompt hints; the agent never sees `checks.json`.

This is the fallible layer, and its failure modes are the reason the other two
exist. **Tool results in the trace are truncated**, so a judge asked about file
content is guessing. **One check must test one thing** — a check bundling three
requirements forces the judge to collapse "two of three" into a single boolean,
and it lands differently each run. That is not agent nondeterminism; it is an
unanswerable question.

### Why the verdict is still noisy

Even with mechanical layers, an agent run is nondeterministic end to end. The
harness treats that as a measurement problem rather than pretending otherwise:
CI gates on regression rather than absolute pass, re-runs a regressing cell
before blocking, marks genuinely unstable cells `flaky` so they never gate in
either direction, and ships `flakiness.py` to *measure* instability instead of
guessing at it. Read a disagreement asymmetrically — **a flip proves
instability, but agreement only fails to disprove it.** See [CI](#ci) and
[Measuring stability](#measuring-stability).

For the statistics contract used by the *other* harness — Wilson lower bounds,
McNemar paired tests, FDR correction, judge test-retest, and the
execution-accuracy lineage — see
[`nxd_eval/METHODOLOGY.md`](nxd_eval/METHODOLOGY.md). That framework grades a
different question (how reliably an agent answers questions against a data
product) with a heavier deterministic-EX + judged split.

## Running the suite (automated)

`run.py` runs the whole loop — install a skill-set, drive a headless agent over
each scenario with its `fixtures/`, then grade the transcript with an LLM judge
against the scenario's `checks.json`. The same command runs locally and in CI.

Prerequisite: the `claude` CLI must be installed and authenticated (`claude
setup-token` or an API key). The runner sets no credentials of its own.

```sh
# List skill sets and scenarios.
python3 evals/run.py --list

# Run one scenario with one skill-set (fast iteration).
python3 evals/run.py --skill-set current_pack \
  --scenario pgvector-embedding-type-failure

# Run the full public suite across all skill-sets, write a JSON report.
python3 evals/run.py --report eval-report.json

# Cheaper smoke run.
python3 evals/run.py --skill-set current_pack \
  --agent-model sonnet --judge-model sonnet

# Faster: run cells in parallel and cache agent transcripts so re-runs that
# only change checks.json / the judge skip the expensive agent step.
python3 evals/run.py --concurrency 4 --cache-dir .eval-cache --report eval-report.json
```

Defaults: agent `sonnet`, judge `opus`, effort `medium` for both, concurrency
`4`. The agent under test is the cheaper model we measure; the judge runs on the
stronger model because its grading is the call we most want to trust. Override
any of these with `--agent-model` / `--judge-model` / `--agent-effort` /
`--judge-effort` / `--concurrency`. The agent cache is keyed on the skill-set,
the agent-facing task, the fixtures, the agent backend, and the agent model — a
fixture, skill, or provider change invalidates it; a grading-only change does not.

### Choosing a provider (Claude / Codex)

The agent-under-test and the judge each run behind a pluggable **backend**
(`evals/eval_backends.py`). Two ship:

| Backend | CLI it shells | Default agent / judge model | Default agent / judge effort |
|---|---|---|---|
| `claude` (default) | `claude -p` (Claude Code) | `sonnet` / `opus` | `medium` / `xhigh` |
| `codex` | `codex exec --json` (OpenAI Codex) | `gpt-5.6-luna` / `gpt-5.6-terra` | `medium` / `xhigh` |

Pick per-side — you can run a Codex agent graded by a Claude judge, or the
reverse:

```sh
# Measure an OpenAI model on the skill task, graded by the same provider.
python3 evals/run.py --agent-backend codex --judge-backend codex \
  --skill-set current_pack --scenario duplicate-rows-on-rerun

# Cross-provider: Codex agent, Claude judge (the grader you trust most).
python3 evals/run.py --agent-backend codex --judge-backend claude \
  --skill-set current_pack --report eval-report.json
```

When `--agent-model` / `--judge-model` is omitted, the model defaults resolve
from the chosen backend (Codex ids differ from Claude's, so `sonnet` is never
sent to Codex). The prerequisite CLI must be installed and authenticated for
whichever backend you select (`claude` and/or `codex`); the runner sets no
credentials of its own.

**Skill activation differs by provider — the numbers are not directly
comparable.** Claude loads a skill-set as a plugin (`--plugin-dir`), so skills
activate through the `Skill` tool exactly as in production. Codex has no
plugin-dir mechanism, so the runner stages the skill pack under
`<workspace>/.skills/` and the agent prompt tells the agent to read the matching
`SKILL.md`. That measures *skills as context*, not *skill invocation*. Report a
Codex run as "Codex + skill-set X", never head-to-head against a Claude run's
absolute pass rate; the valid within-provider comparison is still
`no_skills` vs `current_pack` vs `candidate_pack` on the **same** backend.

**Tool restriction is also provider-shaped.** Scenarios that deliberately narrow
the agent's tool surface (job-loop withholds `WebFetch`/`TodoWrite` to measure
behaviour without a web escape hatch) pass an `allowed_tools` list. Claude gates
per-tool and honours it exactly; Codex gates with a sandbox policy and ignores
the list, so it cannot reproduce the same restriction. A tool-restricted scenario
is therefore measuring a different thing on each backend — compare within a
provider, never across.

`run.py` exits non-zero only on infrastructure failures (a run that could not be
graded). A graded `FAIL` is a measured signal, not a CI break at the runner
level — but CI does gate on *regression* against a committed baseline; see
"CI" below.

### Benchmarking a skill change (regression + efficiency)

Every run records `num_turns`, `tool_calls`, `input_tokens`/`output_tokens`,
`total_cost_usd`, and `duration_ms` per (skill-set × scenario) cell — in the
console summary and in the `--report` JSON under `results[].metrics`. Correctness
(the judge verdict) and efficiency (steps/tokens to get there) are graded
together: a skill edit that keeps PASS but doubles the tool calls is a
regression too.

Before committing a change to a skill, run its scenario(s) and compare against a
baseline report from `main`:

```sh
# On main: capture the baseline for the skill's scenario(s).
python3 evals/run.py --skill-set current_pack \
  --scenario nxd-setup-headless-auth --report /tmp/eval-before.json

# On your branch: same command, new report.
python3 evals/run.py --skill-set current_pack \
  --scenario nxd-setup-headless-auth --report /tmp/eval-after.json
```

Then diff the two reports' verdicts and metrics. Judge checks are the
regression gate; `num_turns` / `tool_calls` / tokens are the efficiency trend.

Record the outcome in the repo so improvement is visible over time:

```sh
python3 evals/benchmark_record.py \
  --label "nxd-setup-cli: <what changed>" \
  --report before-v0.7.0=/tmp/eval-before.json \
  --report after-v0.8.0=/tmp/eval-after.json \
  --notes "<why the change was made>"
```

This creates a before/after entry at `evals/benchmarks/entries/<id>.md`, a
matching compact transcript-free report at `evals/benchmarks/records/<id>.json`,
and deterministically rebuilds `evals/benchmarks/README.md`. The ID defaults to
`<date>-<label-slug>`; use `--date YYYY-MM-DD` for reproducible evidence and
`--id lowercase-slug` only when a stable identity is needed. Commit the entry,
record, and index in the same PR as the skill change it measures. The old
`evals/benchmarks/ledger.md` and all pre-migration `records/*` are frozen
legacy evidence — do not backfill, append, or rewrite them. To produce a
genuine "before" for a scenario that is new in your PR, run it from a worktree
of `main` with the scenario (and `evals/run.py`, for identical metrics) copied
in: `git worktree add /tmp/before origin/main && cp -R evals/public/<scenario>
/tmp/before/evals/public/ && cp evals/run.py /tmp/before/evals/`.
**When no scenario can distinguish the change** — a diagnostic's `path` or
message moving, say — there is nothing to run, and `benchmark_record.py` has no
report to consume. Hand-author `evals/benchmarks/entries/<id>.md` instead with
this frontmatter schema:

```yaml
---
id: "2026-08-03-diagnostic-path"
date: "2026-08-03"
label: "diagnostic path clarification"
plugin_version: "0.0.0"
status: "NO_EVAL"
scenarios: []
record: null
---
```

Give the body a title, Notes that plainly explain why there is no eval arm, and
Evidence naming an existing carrying test file path such as
`evals/tests/test_self_check_diagnostic_vocab.py` (prefer tests verified to fail against the
previous implementation). Then run
`python3 evals/benchmark_record.py --rebuild-index`. `--rebuild-index` validates
all entries and rewrites the generated index; `--check` validates them and fails
if the checked-in index drifts. Do not manufacture a scenario to produce a
number: the evidence's value is that a reader can assume every figure in it
means something. See the AGENTS.md benchmarking paragraph, which is the
contract this mirrors.

The recorder serializes publication and recovers safely after a process crash.
An uncatchable `SIGKILL` can leave a private publication marker plus a partial
entry/record pair until the next recorder, `--rebuild-index`, or `--check` runs;
that next invocation removes a partial pair (or retains a complete byte-matching
pair) before it reads the index. Do not delete these recovery files manually.

Because agent runs are nondeterministic, treat single-run metric deltas under
~20% as noise — repeat the run (or use `--cache-dir` only for judge iteration,
never for before/after comparisons, since a cache hit replays the old
transcript).

Each scenario should pin down one failure mode we never want to reintroduce
(e.g. `nxd-setup-headless-auth` regression-tests the `nxd-setup-cli` skill's
sandboxed-shell auth branch: dead background login poller → manual curl device
flow → hand-written `tokens.json` → PAT).

### Authoring a scenario

Each scenario directory holds:

- `prompt.md` — the task shown to the agent. **Never leak the expected fix or
  known failure mode here.** Only the text under `Task for the agent:` is
  agent-visible; the runner cuts it at the next section header, matched by a
  line *beginning* with `Required artifacts`, `Success checks`, `Constraints`,
  or `Expected final` (case-insensitive) — so don't let an ordinary task
  sentence wrap onto a line starting with one of those words, or the rest of
  the task is silently dropped.
- `fixtures/` — the artifacts a real session would have: mock `nxd` CLI output
  (`*.txt`) and any source `data_product/` directory. Copied into the agent's
  workspace. These are agent-visible, so they must read like raw artifacts, not
  hints.
- `checks.json` — the structured success checks the judge grades against
  (`{"name": ..., "checks": [{"id", "check"}]}`). **Judge-only; never shown to
  the agent.** This is where expected reasoning is spelled out.

### Multi-turn scenarios (scripted follow-up turns)

Some behaviours only appear across a conversation: proposing a plan, *stopping*,
and then applying a correction the user supplies. A single-turn cell cannot
measure them — an agent told the correction up front never has to stop and ask.

Declare follow-up turns in `checks.json`. Absent or empty, the scenario is
single-turn and runs on exactly the pre-existing path:

```json
{
  "name": "...",
  "turns": [
    {"text": "Approved with two corrections: ... go ahead and build it."}
  ],
  "checks": [
    {"id": "applies-supplied-corrections", "check": "...", "turn": 2}
  ]
}
```

- `turns[].text` (required) — the scripted user message, sent verbatim. Turns
  are static; nothing is model-generated, because a simulated user would add a
  second stochastic process to the measurement instrument.
- `turns[].when` — `"always"` (default) or `"awaiting_input"`. Prefer `always`.
  A conditional turn only fires when the previous turn's final answer *ends*
  with `[[AWAITING_USER_INPUT]]`; if the agent asks its question in prose
  instead the turn is skipped and the rest of the rubric would go ungraded, so
  gate a turn only when sending it to a finished agent would corrupt the
  measurement. Skipped turns are recorded in `metrics["skipped_turns"]`, and the
  judge is told to fail their annotated checks as "turn not sent" rather than
  grade them against a conversation that never happened.
- `turns[].timeout_s` — optional per-turn cap (positive int; `true` is
  rejected). Wall-clock from the moment the turn is sent, so a turn that streams
  continuously does not extend it. The run-level `--agent-timeout` stays a
  **whole-run** budget regardless of turn count, and whichever budget expires
  first is named in the error.
- `checks[].turn` — annotation only. It tells the judge which turn a check is
  about; it never slices the trace, because "did the agent honour the
  correction" is unanswerable without turn 1 in view.

`turns[i]` is turn `i+2` — turn 1 is `prompt.md`. The accumulated trace carries
a `[user_turn N <state>] <text>` separator line before each scripted turn, so a
`wants_trace` deterministic checker can grade **ordering** (e.g. fail if any
closure write appears before `[user_turn 2`) instead of leaving
stopped-and-asked entirely to the stochastic judge.

`<state>` is `after-await` when the previous turn ended with
`[[AWAITING_USER_INPUT]]` and `unprompted` when it did not. Because turns
default to `always`, a separator's presence proves only that the harness spoke
— not that the agent had stopped to be spoken to. A scenario grading "did the
agent stop and ask" must key on that state rather than on the delivery. The
same fact reaches the judge as a `HARNESS FACT` line and is recorded in
`metrics["awaited_input_turns"]`; an unprompted delivery instructs the judge to
fail any check about the agent pausing for approval, so an agent that never
stopped cannot inherit credit from a turn the harness sent anyway.

Multi-turn requires a provider that can drive it. `claude` can; `codex` cannot
(`codex exec` is single-shot with no persistent-stdin or resume protocol), and a
multi-turn scenario on `--agent-backend codex` fails loudly before a workspace
is built rather than silently grading a turn-1-only transcript.

### CI

`.github/workflows/evals.yml` has two entry points, and `release.yml` adds a
third that is not opt-in.

**Opt-in (pull requests).** A PR runs evals only while it carries the
`run-evals` label. Labelled, and touching `src/**` or `evals/**`, it runs only
the scenarios that cover the changed skills, on the `codex` backend with
`current_pack`. Unlabelled, the job is skipped and the PR costs nothing. The
label is honoured on `labeled` as well as `synchronize`, so adding it to an open
PR starts a run without needing a push.

Selection is computed by `evals/affected_scenarios.py`, which inverts the
`skills` array each scenario declares in its `checks.json`:

```json
{
  "name": "Duplicate Rows on Every Re-run",
  "skills": ["nxd-debug-data-product", "nxd-add-outputs"],
  "checks": [ ... ]
}
```

`skills` is mandatory — `validate_skills.py` fails a scenario that omits it or
names a directory absent from `src/`. Without it a scenario is selected by no
change at all, which is indistinguishable from "this skill has no regressions".

Changes to the harness itself (`run.py`, `eval_backends.py`, `skill-sets.yaml`,
the workflow) select every scenario, since they can alter any cell's outcome.

A scenario that cannot run unattended sets `ci_skip` to a reason string and is
never selected automatically. Run those locally or via `workflow_dispatch`.
Nineteen scenarios are currently skipped:

| Scenario | Why |
|---|---|
| `job-loop-serve-query-refine` | needs a live desktop supervisor (`EVAL_DESKTOP_SUPERVISOR_DIR`) |
| `job-loop-export-handoff` | needs a live desktop supervisor (`EVAL_DESKTOP_SUPERVISOR_DIR`) |
| `treasury-yield-curve` | same |
| `multi-source-labeled-roots-supervisor` | needs a compatible live desktop supervisor (`EVAL_DESKTOP_SUPERVISOR_DIR`) |
| `authenticated-api-source-supervisor` | same, and the runner keeps its HTTP fixture bound across the verifier's re-serve |
| `country-income-trajectory` | same |
| `incremental-multi-model` | same |
| `terminal-field-mapper-adapter-contract` | same, over the stdio MCP transport (`EVAL_DESKTOP_PYTHON` too) |
| `worldbank-live` | same, plus outbound network to `api.worldbank.org` |
| `pharma-cross-dp-mesh-query` | needs a live semantic MCP server reaching lower-env Snowflake |
| `pharma-mesh-query-hard` | same |
| `pharma-mesh-query-loop` | same |
| `semantic-intent-validation` | same |
| `coauthor-executable-policy-readback` | scripts a follow-up turn; the PR gate runs `codex`, which cannot drive multi-turn |
| `incremental-transform-state` | scripts a follow-up turn and a three-run stateful checker; the PR gate runs `codex`, which cannot drive multi-turn |
| `desktop-custom-contracts` | requires the manually operated default-deny source-isolation wrapper and operator-resolved protected roots; the automatic PR runner does not provision either |
| `terminal-self-check-provenance` | needs an authenticated Claude CLI and a provisioned `nxd-desktop-supervisor` runtime; run explicitly with `EVAL_DESKTOP_SUPERVISOR_DIR`, `EVAL_DESKTOP_PYTHON`, and `EVAL_NXD_REPO_ROOT` |
| `terminal-timeout-lifecycle` | needs an authenticated Claude CLI, a provisioned `nxd-desktop-supervisor` runtime, and the runner-owned loopback fixture |
| `optional-empty-output-aggregate-desktop` | needs a compatible live `nxd-desktop-supervisor` runtime; native compiler execution is a separate follow-up |

`coauthor-executable-policy-readback` is the provider-limit entry: it runs
unattended on `--agent-backend claude` and needs the manual entry point only
because the automatic gate defaults to `codex`. `desktop-custom-contracts` is
different: it is wrapper-only on the Codex backend and must be run manually
with the default-deny source-isolation attestation and protected-root mapping.
The protected manual path is `evals/run.py --scenario desktop-custom-contracts
--agent-backend codex`, with `EVAL_CODEX_WRAPPER`,
`EVAL_SOURCE_ISOLATION_CAPABILITY_ID`,
`EVAL_SOURCE_ISOLATION_PROFILE_FINGERPRINT`, and
`EVAL_SOURCE_ISOLATION_ROOTS` configured by the operator (alongside the normal
desktop runtime variables). The automatic PR runner deliberately provides none
of those inputs, so it cannot accidentally turn this environment gate into a
deterministic scenario error.

**A reference wrapper ships at
[`evals/tools/source-isolation-wrapper.py`](tools/source-isolation-wrapper.py)**
(macOS). It enforces the deny list with `sandbox-exec`, so a protected root is
unreadable at the kernel level rather than by convention — the attestation
claims the agent *could not* read those paths, and only real denial supports
that. Point `EVAL_CODEX_WRAPPER` at it, set
`EVAL_SOURCE_ISOLATION_PROFILE_FINGERPRINT` to its `sha256`, and list the
roots in `EVAL_SOURCE_ISOLATION_ROOTS`:

```bash
export EVAL_SOURCE_ISOLATION_CAPABILITY_ID='nxd-eval-source-isolation-v1'
export EVAL_CODEX_WRAPPER="$PWD/evals/tools/source-isolation-wrapper.py"
export EVAL_SOURCE_ISOLATION_PROFILE_FINGERPRINT="$(shasum -a256 "$EVAL_CODEX_WRAPPER" | cut -d' ' -f1)"
export EVAL_SOURCE_ISOLATION_ROOTS='{"benchmark_report_history":"…","closure_temp_history":"…","codex_memories":"…/.codex/memories","codex_session_history":"…/.codex/sessions","evaluator_checkout":"…"}'
python3 evals/run.py --scenario desktop-custom-contracts --agent-backend codex --judge-backend codex
```

Three traps worth knowing before you spend an afternoon on them:

- **`evaluator_checkout` must be the checkout the run is launched FROM.** In a
  before/after comparison each arm has its own, and pointing both at one tree
  lets the other arm's copy of the withheld checker stay readable. The
  `withheld-custom-contract-checker` probe catches this and refuses to run.
- **Do not protect the whole temp root.** `run.py` builds the agent's workspace
  under it, so a blanket deny blocks the run itself. Move prior closures into a
  dedicated root instead.
- **A denied read still fails the audit.** For a `root` marker the needle *is*
  the protected path, and `ls: /path: Operation not permitted` contains it — so
  an attempt the sandbox correctly refused is indistinguishable from a
  successful read, and the run errors `access_observed`. That is deliberate: the
  audit does not guess. Re-run rather than reinterpret.

**Coverage gaps this leaves.** `nxd-query-data-product` is covered *only* by
skipped scenarios, so a PR touching it currently gets a green no-op. One more
skill — `nxd-analyze-mesh` — has no scenario at all: a scenario for it was
authored but withdrawn because its fixture rewarded *not* following the skill,
so it detected nothing (see the git history for
`infra-profile-source-discovery`). `nxd-review-closure` is a third: no
scenario's `skills` list names it, because it is dispatched as a subagent
from `nxd-generate-data-product` Step 6b rather than invoked directly — what
a scenario can observe is its EFFECT on the landed closure, which is what the
`no_review_control` arm in `skill-sets.yaml` measures. Three of seventeen
skills are therefore unguarded by CI. A green eval check on those PRs means "nothing
ran", not "nothing regressed".

The three scenarios these gaps used to include — `nxd-add-policies`,
`nxd-toggle-policies`, `nxd-run-evals` — now each have a scenario, though none is
baselined yet: they run and report `new`, and gate only once a measured verdict
is recorded.

**Gating is on regression, not on absolute pass.** `evals/compare_baseline.py`
compares the report against `evals/baselines/public.json` and fails the job only
when a cell recorded `PASS` there now fails. Absolute pass rates are noisy —
agent runs are nondeterministic and some cells fail at baseline for reasons a
given PR did not introduce — so gating on `FAIL` would be both flaky and unfair.
A cell absent from the baseline reports as `NEW` and never fails the build.

**A regression must reproduce to block.** One agent run is too noisy to gate on:
`false-pass-validation` was observed `PASS`, then `FAIL`, then `PASS` again on
unchanged input. So when a cell regresses, CI re-runs just that cell and fails
only if it regresses twice. A cell that passes on retry is reported as
`FLAKY-RUN` and does not block. Only a clean `PASS` rescues — a retry that
`ERROR`s or fails again still gates.

Some cells are unstable enough that even a retry cannot make them meaningful.
Mark those `"flaky": true` in the baseline with a note recording the evidence;
they are still run and reported (as `FLAKY`) but never gate, in either
direction — a flaky cell that happens to pass is not reported as an improvement
either, and `--update` refuses to re-record it. Both matter: recording a flaky
cell's `PASS` is exactly what converts a coin toss into a gating cell.

Two cells are currently marked:

- `generate-semantic-layer-dp-from-schema` — `PASS` when recorded, `FAIL` (3/10
  checks) on an identical re-run. Its checks demand visible evidence for ten
  separate artifacts that a nondeterministic agent does not reliably produce.
- `nxd-setup-headless-auth` — `FAIL` then `PASS` across two CI runs of the same
  commit. Recorded `FAIL`, so it does not gate today; the marker exists to stop
  a later `PASS` from being locked in.

The markers are a stopgap, not a fix: those checks want rewriting into fewer,
more robust assertions that assert on outcomes rather than on wording.

`false-pass-validation` is deliberately **not** marked despite flipping. It is
recorded `PASS`, so exempting it would drop a real check rather than fix it;
retry-once is what holds it.

## Measuring stability

Whether a cell is flaky is a measurement, not a guess — and flakiness has so far
been found by accident, which systematically under-counts it. To measure, run
the suite N times on identical input off the PR path:

Actions → **evals** → Run workflow → `mode: stability`, `repeats: 5`.

The job runs the selected scenarios N times with no cache (a cached transcript
would replay identically and report a flip rate of zero by construction), then
`evals/flakiness.py` reports which cells disagreed with themselves. Run it
locally against saved reports the same way:

```sh
python3 evals/flakiness.py --report run-1.json run-2.json run-3.json
```

Read the output asymmetrically: **a disagreement proves instability, but
agreement only fails to disprove it.** A cell that flips one run in five still
looks stable across two runs most of the time, so the printed graded-run count
is part of the result. This probe never gates — gating on a flakiness measurement
would block PRs for the very nondeterminism it exists to quantify.

When a change legitimately alters a verdict, re-record it in the same PR:

```sh
python3 evals/compare_baseline.py --report eval-report.json --update
```

`ERROR` cells are never written to the baseline: a cell that failed to run
carries no signal about the skill, and recording it would imply coverage that
does not exist.

**A baseline entry is only valid for the scenario content it was recorded
against.** If a PR rewrites a scenario's `prompt.md`, `fixtures/`, or
`checks.json`, the recorded verdict for that cell is stale — and a stale `PASS`
is worse than no entry, because the next PR to touch that skill is reported as a
REGRESSION for a change it did not make. Re-run and re-record any scenario your
branch rewrites, and re-check after rebasing past someone else's rewrite:

```sh
git diff --name-only origin/main...HEAD -- evals/public/
```

## Writing checks that can actually be graded

The judge sees the run trace and the final answer — and tool results in the
trace are truncated. Two failure modes follow, and both were found in real
cells rather than imagined:

**A check about file content cannot be graded from a transcript.** An agent that
writes a correct `models.py` without echoing it back is indistinguishable from
one that wrote nothing, so the check fails for lack of evidence rather than for
being wrong, and it flips run to run with how chatty the agent happened to be.
Declare `workspace_files` in `checks.json` and the harness reads the produced
files out of the workspace and quotes them to the judge as authoritative:

```json
"workspace_files": ["models.py", "spec.py", "**/requirements.txt"]
```

Patterns are workspace-relative globs. A pattern matching nothing produces an
explicit "these files were never written" fact rather than silence, an oversized
file is named as omitted rather than truncated into the prompt, and a cached
transcript reports the files as unavailable — in each case the judge is told
what is unknown instead of inferring it. Note that quoting is a snapshot taken
after the run, so it evidences *what the agent produced*, not *when or how* it
produced it; keep process claims as separate checks graded from the trace.

Two traps, both of which produced confident wrong verdicts before being fixed:

- **The harness stages files into the workspace too.** The skill pack's bundled
  reference data products live under `.skills/` and carry exactly the names a
  scenario asks about, so `**/models.py` matches dozens of files the agent never
  wrote. Staged directories are now skipped and matches are ordered
  shallowest-first, because otherwise those files exhaust the quoting budget and
  starve the agent's own output — the verdict then tracks *where* the agent put
  its files rather than what is in them.
- **A fact that reads too late looks exactly like a true negative.** Collecting
  after the workspace is cleaned up matches nothing and reports "never written"
  with full authority. `workspace_files_fact` now raises if the workspace is
  gone, so absence is only ever reported when absence was measurable.

The general point: a mechanical fact is graded as ground truth, so a bug in one
is worse than the transcript-guessing it replaces — guessing at least fails
visibly. Confirm a newly-declared `workspace_files` list actually quotes what
you expect (`mode: stability` prints the fact into each report) before trusting
a verdict that depends on it.

**One check should test one thing.** `verifies-whoami-and-identity` bundled
three requirements — inspect whoami's output, mention the exit-code-0 caveat,
surface the email — into a single boolean. Two runs whose answers were
substantively identical (both ran whoami, both told the user to confirm the
email, neither mentioned the caveat) graded `FAIL` and `PASS`, because the judge
had to collapse "two of three" into one verdict and landed differently each
time. That is not agent nondeterminism; it is an unanswerable question. Split
such a check per requirement, and drop any clause you are not actually willing
to fail the cell over.

**The baseline is provider-specific.** It was recorded on the `codex` backend,
which is what the PR gate runs. Codex activates skills as staged context rather
than through the `Skill` tool (see "Skill activation differs by provider"
above), so several cells sit at `FAIL` having done the substantive work but not
evidenced every prescribed step. Those `FAIL` entries are a property of the
harness, not proof of a skill defect — do not rewrite a skill to chase one
without first comparing against a `claude`-backend run.

**Manual (`workflow_dispatch`).** Full control over backend, models, skill-set,
and scenario. It reports baseline drift but never fails on it, since an
arbitrary backend/model combination is expected to diverge from the PR gate's
baseline.

**Release (`v*` tag).** The `release-evals` job in `.github/workflows/release.yml`
runs every runnable public scenario on the tagged commit, with the same
retry-then-confirm regression gate the PR path uses. Nothing is published unless
it passes. This is the run whose evidence leaves the repo: the report ships as
the release's `evals.json` asset, and nxd's submodule bump requires it.

It runs the whole runnable set rather than an affected-scenarios subset
deliberately. At release time there is no single "changed skill" to narrow by —
the diff since the previous tag can span the whole pack — and this is the one run
whose result is published as the version's evidence, so it should not be scoped
by a heuristic.

"Runnable" excludes the 19 `ci_skip` scenarios. It has to: `run.py` does not read
`ci_skip` (only `affected_scenarios.py` does), so a bare `--suite public` would
run the scenarios that need a live desktop supervisor or a semantic MCP server,
they would all ERROR, and since none of them are in the baseline
`compare_baseline.py` would report them as ungated `NEW` — the gate would go
green having measured nothing about them. The job therefore asks
`affected_scenarios.py` for the runnable list and passes explicit `--scenario`
flags, which also keeps `ci_skip` defined in exactly one place.

For the same reason the release job additionally fails on any cell that produced
no verdict at all. `compare_baseline.py` treats an ERROR cell as carrying no
signal, which is right for a PR — an infrastructure blip should not red an
unrelated change — and wrong for the run whose report is published as proof that
this version was measured.

Two consequences worth stating plainly. Tagging a release now costs a full
runnable-suite run, which is the point: it is the only place the pack is measured
end to end. And because PR evals are opt-in, a commit can reach `main`
unmeasured; the release gate is what stops it reaching the monorepo, not the PR
gate.

Credentials: both the PR gate and the release gate use the `OPENAI_API_KEY` repo
secret (codex backend). The manual job additionally reads `ANTHROPIC_API_KEY`
when either side is set to the `claude` backend.

## Running a scenario (manual reference)

The manual loop the runner automates, for reference:

1. Start from a clean checkout or temporary working directory.
2. Install the selected skill set from `skill-sets.yaml`.
3. Give the agent only the scenario prompt and artifacts named in the scenario.
4. Capture transcript, changed files, command output, and final answer.
5. Grade with the scenario's success checks.

Do not leak the expected fix or known failure modes into the agent prompt. The point is to measure whether the skills make the agent discover the right path faster.

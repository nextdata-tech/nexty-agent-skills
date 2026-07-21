# Nexty Skill Evals

Use these scenarios to measure how fast and reliably an LLM can complete Nextdata OS data-product work with and without the skill pack.

`evals/` is a measurement harness, not customer-facing skill content. Keep shared scenarios generic. Put customer-specific, commercial-demo, or proprietary artifacts in `evals/private/`, which is ignored by git.

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
the agent's tool surface (pocket-loop withholds `WebFetch`/`TodoWrite` to measure
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
  --label "nxd-setup: <what changed>" \
  --report before-v0.7.0=/tmp/eval-before.json \
  --report after-v0.8.0=/tmp/eval-after.json \
  --notes "<why the change was made>"
```

This appends a before/after entry to `evals/benchmarks/ledger.md` and saves a
compact transcript-free copy of the reports under `evals/benchmarks/records/`.
Commit both in the same PR as the skill change they measure. To produce a
genuine "before" for a scenario that is new in your PR, run it from a worktree
of `main` with the scenario (and `evals/run.py`, for identical metrics) copied
in: `git worktree add /tmp/before origin/main && cp -R evals/public/<scenario>
/tmp/before/evals/public/ && cp evals/run.py /tmp/before/evals/`.
Because agent runs are nondeterministic, treat single-run metric deltas under
~20% as noise — repeat the run (or use `--cache-dir` only for judge iteration,
never for before/after comparisons, since a cache hit replays the old
transcript).

Each scenario should pin down one failure mode we never want to reintroduce
(e.g. `nxd-setup-headless-auth` regression-tests the `nxd-setup` skill's
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

### CI

`.github/workflows/evals.yml` has two entry points.

**Automatic (pull requests).** A PR touching `src/**` or `evals/**` runs only
the scenarios that cover the changed skills, on the `codex` backend with
`current_pack`. Selection is computed by `evals/affected_scenarios.py`, which
inverts the `skills` array each scenario declares in its `checks.json`:

```json
{
  "name": "Duplicate Rows on Every Re-run",
  "skills": ["nxd-debugging-data-products", "nxd-adding-outputs"],
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
Five scenarios are currently skipped:

| Scenario | Why |
|---|---|
| `pocket-loop-serve-query-refine` | needs a live desktop supervisor (`EVAL_POCKET_SUPERVISOR_DIR`) |
| `pharma-cross-dp-mesh-query` | needs a live semantic MCP server reaching lower-env Snowflake |
| `pharma-mesh-query-hard` | same |
| `pharma-mesh-query-loop` | same |
| `semantic-intent-validation` | same |

**Coverage gaps this leaves.** `nxd-data-product-query` is covered *only* by
skipped scenarios, so a PR touching it currently gets a green no-op. Four more
skills — `nxd-adding-policy`, `nxd-policies`, `nxd-mesh-analyzer`,
`nxd-eval-harness` — have no scenario at all. Five of fifteen skills are
therefore unguarded by CI. A green eval check on those PRs means "nothing ran",
not "nothing regressed".

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

Credentials: the PR gate uses the `OPENAI_API_KEY` repo secret (codex backend).
The manual job additionally reads `ANTHROPIC_API_KEY` when either side is set to
the `claude` backend.

## Running a scenario (manual reference)

The manual loop the runner automates, for reference:

1. Start from a clean checkout or temporary working directory.
2. Install the selected skill set from `skill-sets.yaml`.
3. Give the agent only the scenario prompt and artifacts named in the scenario.
4. Capture transcript, changed files, command output, and final answer.
5. Grade with the scenario's success checks.

Do not leak the expected fix or known failure modes into the agent prompt. The point is to measure whether the skills make the agent discover the right path faster.

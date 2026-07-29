# Getting started with the evals

Start here. `evals/` holds **four independent harnesses** with separate
dependencies and separate entry points — this page is the map and the install
guide. Once you know which harness you need, its own README is authoritative.

| Harness | Entry point | Install cost | What it measures |
|---|---|---|---|
| **Scenario suite** | `evals/run.py` | **nothing** (stdlib only) | Does the skill pack make an agent solve a real task faster and more reliably? Judged pass/fail per scenario. This is what CI gates on. |
| **`nxd_eval`** | `uv run --project evals/nxd_eval` | uv project (`inspect_ai` + stats stack) | How reliably an agent answers questions against a data product/mesh — deterministic execution-accuracy plus a judge, with a Wilson/McNemar/FDR statistics contract. |
| **Semantic MCP server** | started *by* `run.py` | uv project + private nxd wheels + Snowflake | Not a harness on its own — it makes the semantic tools real for 4 scenarios in the suite. |
| **Query loop** | `evals/query-loop/run_query_loop.py` | borrows `nxd_eval`'s venv | Multi-turn query refinement against a pharma mesh fixture. |

**If you are new and want to run something today: Tier 0 below needs no
installs and covers 17 of the 23 public scenarios.**

---

## Tier 0 — the scenario suite (zero install)

`evals/run.py` is deliberately dependency-free. It imports only the Python
standard library, and even hand-parses `skill-sets.yaml` with a small
purpose-built reader rather than taking a `pyyaml` dependency. There is no
`pip install` step and no virtualenv to create.

### Requirements

| Need | Check | Notes |
|---|---|---|
| Python ≥ 3.11 | `python3 -VV` | stdlib only |
| `codex` CLI **and/or** `claude` CLI | `codex --version` / `claude --version` | at least one; install both to run cross-provider |
| Credentials for whichever CLI you use | see below | the runner sets **none** of its own |

The runner never handles credentials. It shells out to a CLI and inherits
whatever that CLI already resolved.

```sh
# OpenAI / Codex
export OPENAI_API_KEY=sk-...          # or: codex login

# Anthropic / Claude
export ANTHROPIC_API_KEY=sk-ant-...   # or: claude setup-token
```

### Run it

```sh
# What exists: skill sets and scenarios.
python3 evals/run.py --list
```

Both providers are supported on both sides — the agent-under-test and the
judge each pick a backend independently.

```sh
# --- OpenAI / Codex both sides (what the PR gate runs) ---
python3 evals/run.py \
  --agent-backend codex --judge-backend codex \
  --skill-set current_pack --scenario duplicate-rows-on-rerun

# --- Anthropic / Claude both sides (the default; flags shown for clarity) ---
python3 evals/run.py \
  --agent-backend claude --judge-backend claude \
  --skill-set current_pack --scenario duplicate-rows-on-rerun

# --- Cross-provider: Codex agent graded by the Claude judge ---
python3 evals/run.py \
  --agent-backend codex --judge-backend claude \
  --skill-set current_pack --report /tmp/eval-report.json

# --- Full public suite, parallel, with a report ---
python3 evals/run.py \
  --agent-backend codex --judge-backend codex \
  --skill-set current_pack --concurrency 4 --report /tmp/eval-report.json
```

Model and effort defaults resolve from the backend you choose, so you never
send a Claude model id to Codex:

| Backend | Agent model | Judge model | Agent / judge effort |
|---|---|---|---|
| `claude` (default) | `sonnet` | `opus` | `medium` / `xhigh` |
| `codex` | `gpt-5.6-luna` | `gpt-5.6-terra` | `medium` / `xhigh` |

Override any of them with `--agent-model` / `--judge-model` /
`--agent-effort` / `--judge-effort`. The agent-under-test runs on the cheaper
model because it is what we are measuring; the judge runs on the stronger one
because its grading is the call we most want to trust.

### Faster iteration

```sh
# Cache agent transcripts: re-runs that only change checks.json or the judge
# skip the expensive agent step entirely.
python3 evals/run.py --cache-dir .eval-cache --concurrency 4 \
  --skill-set current_pack --report /tmp/eval-report.json
```

The cache key covers the skill-set, the agent-facing task, the fixtures, the
backend, and the agent model — so a skill or fixture edit invalidates it while
a grading-only edit does not. **Never use the cache for a before/after
benchmark**: a cache hit replays the old transcript, which is exactly the thing
you were trying to re-measure.

### What runs without any further setup

17 of 23 public scenarios. The remaining 6 declare `ci_skip` in their
`checks.json` and need a Tier 2 or Tier 3 install:

| Scenario | Needs |
|---|---|
| `pharma-cross-dp-mesh-query` | semantic MCP server (Tier 2) |
| `pharma-mesh-query-hard` | semantic MCP server (Tier 2) |
| `pharma-mesh-query-loop` | semantic MCP server (Tier 2) |
| `semantic-intent-validation` | semantic MCP server (Tier 2) |
| `pocket-loop-serve-query-refine` | live desktop supervisor (Tier 3) |
| `pocket-loop-export-handoff` | live desktop supervisor (Tier 3) |

Full detail on scenarios, authoring, the baseline, and CI gating:
[`evals/README.md`](README.md).

---

## Tier 1 — `nxd_eval` (Inspect framework)

A separate uv project with its own venv. Everything runs through
`uv run --project evals/nxd_eval` — never a bare `python3`.

```sh
uv sync --project evals/nxd_eval                  # framework + dev group
uv sync --project evals/nxd_eval --extra openai   # + OpenAI SDK
uv sync --project evals/nxd_eval --extra anthropic # + Anthropic SDK
```

Declared dependencies: `inspect_ai==0.3.130`, `statsmodels>=0.14`,
`scipy>=1.11`, `scikit-learn>=1.4`, `mcp>=1.2.0`, `sqlglot>=25`.

Two things to know before you touch the manifest:

- **`inspect_ai` is hard-pinned, not floated.** The comment in
  `pyproject.toml` is explicit: the agent/MCP surface churns across 0.3.x
  releases. Do not relax the pin to chase a newer version without running the
  suite.
- **Provider SDKs are optional extras on purpose.** The framework is
  vendor-agnostic — it passes a `provider/model` string straight to Inspect,
  which routes by prefix. Keeping the SDKs as extras means the stats and
  scoring unit tests install and pass with no vendor SDK at all. Install only
  the extra for the vendor you actually run.

Provider selection here is by **model-string prefix**, not by a `--backend`
flag — the framework passes `provider/model` straight to Inspect, which routes
on the prefix. So the same call runs on either vendor:

```python
inspect_eval(task, model="openai/gpt-5.6-luna")          # OpenAI
inspect_eval(task, model="anthropic/claude-sonnet-4-5")  # Anthropic
```

The project is `package = false`, so there is no console script — the module
entry point is the supported CLI, and it covers reporting/certification rather
than launching runs:

```sh
uv run --project evals/nxd_eval python -m nxd_eval certify \
  --log ./logs/<run>.eval --gate 'accuracy>=0.90'
```

Runs themselves are driven through Inspect (`inspect_eval(...)`) or the query
loop below. You can produce a real `.eval` log with **no provider and no API
key** using Inspect's built-in `mockllm` — see the worked two-terminal example
in [`nxd_eval/README.md`](nxd_eval/README.md).

```sh
# Browse any resulting log.
uv run --project evals/nxd_eval inspect view --log-dir evals/nxd_eval/logs
```

### Query loop

Borrows this venv. Defaults to `openai/gpt-5.4-mini`; pass `--agent-model` with
an `anthropic/...` string to switch vendor.

```sh
python3 evals/query-loop/run_query_loop.py --list
python3 evals/query-loop/run_query_loop.py --agent-model anthropic/claude-sonnet-4-5
```

Methodology, the statistics contract, and the certification gate:
[`evals/nxd_eval/README.md`](nxd_eval/README.md) and
[`METHODOLOGY.md`](nxd_eval/METHODOLOGY.md).

---

## Tier 2 — semantic MCP server (4 scenarios)

This is the one piece of the scenario suite that needs real dependencies. It
lives in its own uv project so `run.py` itself stays stdlib-only — the runner
launches it as a subprocess and never imports any of it.

It exists so the agent must actually *call* `list_models` / `describe_model` /
`run_semantic_query` rather than read a catalog fixture and narrate. Without
it an agent reads `fixtures/catalog.json` and fabricates SQL and result rows,
which the judge correctly fails.

### The private wheel dependency

`run_semantic_query` imports the **genuine** compiler from
`nxd.experimental.semantic`, shipped in the `nxd_data_product` wheel. That
wheel is built from the nxd monorepo and **is not on any public index**.

> A PyPI package named `nxd-data-product` exists and is an **unrelated stub**.
> Do not depend on it.

Provide the real one either way:

```sh
# (a) install a matched wheel set into this project's venv
uv pip install --project evals/mcp \
  <nxd>/components/nxd_py/wheels/nxd_core-<ver>-*.whl \
  <nxd>/components/nxd_py/wheels/nxd_drivers-<ver>-*.whl \
  <nxd>/components/nxd_py/wheels/nxd_data_product-<ver>-*.whl

# (b) or point run.py at an interpreter that already has the matched set
export EVAL_MCP_PYTHON=/path/to/python
```

**All three wheels must share one version.** A stale `nxd_core` against a
newer `nxd_data_product` fails at runtime.

Declared deps (`evals/mcp/pyproject.toml`): `mcp>=1.2.0`,
`snowflake-connector-python>=3.12`, `cryptography>=42`.

### Snowflake

`run_semantic_query` executes against lower-env Snowflake through a governed
executor (masked views). Credentials are read from the environment only and
are never written to disk by the server.

```sh
set -a; source <your snowflake .env>; set +a
```

Needs `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_WAREHOUSE`,
`SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`, `SNOWFLAKE_ROLE`, plus either
`SNOWFLAKE_PRIVATE_KEY` / `SNOWFLAKE_PRIVATE_KEY_PATH` or
`SNOWFLAKE_PASSWORD`. See `evals/mcp/snowflake_conn.py`. Pull the profile from
the `infra-profile-lower-envs` GCP secret.

### Run

```sh
export EVAL_MCP_PYTHON=...
set -a; source <snowflake .env>; set +a
python3 evals/run.py --skill-set current_pack --scenario semantic-intent-validation
```

`run.py` handles the rest: starts the server on a free port, puts a fake `nxd`
on the agent's PATH so `nxd mcp health` discovers it, runs the agent against
the shipped toolchain unchanged, tears the server down after the cell.

Fixture format and the cross-DP mesh model: [`evals/mcp/README.md`](mcp/README.md).

---

## Tier 3 — pocket-loop (2 scenarios)

Needs a live desktop supervisor that CI cannot provision.

```sh
export EVAL_POCKET_SUPERVISOR_DIR=/path/to/supervisor
export EVAL_POCKET_PYTHON=/path/to/python
export NXD_DESKTOP_REPO_ROOT=/path/to/desktop/repo
```

These scenarios also narrow the agent's tool surface (they withhold `WebFetch`
and `TodoWrite` to measure behaviour without a web escape hatch). **Claude
honours that allowlist per-tool; Codex ignores it** and gates with a sandbox
policy instead. A tool-restricted scenario therefore measures a different
thing on each backend — run these on `claude`.

---

## Tier 4 — scenario fixture runtimes (nothing to install)

Data products the agent builds during a scenario pull their own dependencies
(`dlt`, `duckdb`, `pandas`, `sentence_transformers`, `langchain_*`, pgvector)
from per-fixture `requirements.txt` files. These install inside the eval
workspace at run time. Not part of your setup.

---

## Environment variable reference

Set by you:

| Variable | Tier | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | 0 | codex backend auth |
| `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` | 0 | claude backend auth |
| `EVAL_CODEX_AGENT_SANDBOX` | 0 | override the codex sandbox (default `workspace-write`) |
| `EVAL_MCP_PYTHON` | 2 | interpreter carrying the matched nxd wheel set |
| `SNOWFLAKE_*` | 2 | lower-env connection (env only, never written to disk) |
| `EVAL_MCP_CAN_SEE_PII=1` | 2 | bypass the governed PII mask — debugging the executor only |
| `EVAL_POCKET_SUPERVISOR_DIR` | 3 | desktop supervisor location |
| `EVAL_POCKET_PYTHON` | 3 | interpreter for the supervisor |
| `NXD_DESKTOP_REPO_ROOT` | 3 | desktop repo root, read by pocket-loop fixtures |
| `NXD_EVAL_JUDGE_RETEST=1` | 1 | opt-in judge test-retest pass |
| `NXD_CA_BUNDLE` | 1/2 | per-cluster TLS trust store; unset = system store |
| `NXD_SKILL_PYTHON` | — | interpreter for skill-invoked subprocesses |

Injected by `run.py` — **never set these by hand**: `EVAL_MCP_ENDPOINT`,
`EVAL_MCP_DP`, `EVAL_MCP_TOOL_COUNT`, `NXD_POCKET_CHECK_TMPDIR`.

---

## Reading results

Every cell records both correctness and cost, in the console summary and in
`results[].metrics` of the `--report` JSON: `num_turns`, `tool_calls`,
`input_tokens` / `output_tokens`, `total_cost_usd`, `duration_ms`. A skill
edit that keeps `PASS` but doubles the tool calls is a regression too.

Codex reports token usage but not `num_turns` or `total_cost_usd`; those keys
are simply absent from a codex run's metrics.

`run.py` exits non-zero only on infrastructure failure — a graded `FAIL` is a
measured signal, not a runner-level break. CI gates on *regression against the
committed baseline*, not on absolute pass.

### Three cross-provider caveats

These matter enough to repeat, because each has produced a wrong conclusion
before:

1. **Skill activation differs by provider.** Claude loads a skill-set as a
   plugin, so skills activate through the `Skill` tool exactly as in
   production. Codex has no plugin-dir mechanism, so the runner stages the
   pack under `<workspace>/.skills/` and the prompt tells the agent to read
   the matching `SKILL.md`. That measures *skills as context*, not *skill
   invocation*. Report a Codex run as "Codex + skill-set X" — never
   head-to-head against a Claude run's absolute pass rate. The valid
   comparison is always `no_skills` vs `current_pack` vs `candidate_pack` on
   the **same** backend.
2. **The committed baseline is codex-recorded.** Several cells sit at `FAIL`
   there having done the substantive work but not evidenced every prescribed
   step. Those are a property of the harness, not proof of a skill defect — do
   not rewrite a skill to chase one without first comparing against a
   `claude`-backend run.
3. **Agent runs are nondeterministic.** Treat single-run metric deltas under
   ~20% as noise, and repeat the run before believing a regression.

Benchmarking a skill change, recording it in the ledger, the baseline and
flakiness machinery: [`evals/README.md`](README.md).

# nxd_eval — Inspect-based evaluation framework

Isolated uv project (mirrors `evals/mcp/`): heavy deps (`inspect_ai`,
`statsmodels`, `scipy`, `scikit-learn`) live here, never in the root or
`evals/run.py`. Everything runs via `uv run --project evals/nxd_eval …` — never
bare `python`/`pip`.

## Status: P0 substrate spike

This is the **go/no-go spike** on the Inspect substrate. It stands up the project,
a stub MCP server, and one baseline Inspect `@task`, and proves the chain

    Inspect eval() → react() agent → mcp_server_http() → semantic MCP server
    (Streamable-HTTP) → run_semantic_query → real seeded rows → scorer

**Verdict: GO.** The full chain runs end to end with **zero API key**: Inspect's
built-in `mockllm` provider drives the `react()` agent through a real
`run_semantic_query` tool call against the stub, the `includes()` scorer marks it
correct, and a valid `.eval` log lands on disk (`test_eval_log_emitted`). A raw
MCP client gets the true seeded baseline answer (`4` subjects), and Inspect's own
`mcp_server_http()` connects and enumerates the three tools. A live provider
(`ANTHROPIC_API_KEY`) only swaps the model at the top of this exact wiring — it is
not needed to prove the substrate. See "What's proven vs pending".

## The stub MCP server (P0 only)

The shipping server, `evals/mcp/semantic_server.py`, routes `run_semantic_query`
through the genuine `nxd.experimental.semantic` compiler and a governed Snowflake
executor. Neither the nxd wheel nor Snowflake is present in a bare checkout, so
P0 uses an **offline stub**, `stub_mcp/stub_semantic_server.py`: same three
Streamable-HTTP tools, but `run_semantic_query` is backed by the scenario's own
`seed.sql` loaded into in-memory SQLite. No compiler, no cloud. It answers the
single-grain baseline from real rows so the scorer scores something true; it does
**not** model fan-out safety, governance, or the confusable/abstain
discriminators — those ride the genuine server once a matched interpreter is
wired (see `evals/mcp/README.md`, `EVAL_MCP_PYTHON`).

The stub reads the exact same fixture shape as the real server
(`catalog.json` + `semantic.json` + `seed.sql`), so swapping in the genuine
server later is a launch-command change, not a fixture change.

## Run it

### 1. Install / sync

```bash
uv sync --project evals/nxd_eval
```

### 2. Prove the substrate (no model, no API key needed)

```bash
uv run --project evals/nxd_eval --with pytest \
    pytest evals/nxd_eval/tests/test_substrate_spike.py -v
```

Launches the stub server on a free port and asserts (a) the raw MCP client gets
the seeded baseline `4`, (b) Inspect's `mcp_server_http()` enumerates the three
tools, and (c) the full `spike_baseline()` task runs under `mockllm` — a real
`run_semantic_query` tool call against the stub, scored correct, with a non-empty
`.eval` log written and read back (`test_eval_log_emitted`). If (b) or (c) fails,
the Inspect substrate is a NO-GO.

### 3. Emit a real `.eval` log with no API key (mockllm)

The `.eval` log — the P0 go/no-go artifact — is produced without any provider by
scripting the agent turns with Inspect's built-in `mockllm` model. This is
exactly what `test_eval_log_emitted` does; to drive it by hand and keep the log:

```bash
# terminal A — launch the stub MCP server (fixed port)
uv run --project evals/nxd_eval \
    python evals/nxd_eval/stub_mcp/stub_semantic_server.py \
    evals/public/pharma-mesh-query-hard/fixtures \
    --http --host 127.0.0.1 --port 8790 --dp pharma-mesh --rpc-port mcp-api

# terminal B — drive spike_baseline with mockllm; writes a real .eval log
NXD_EVAL_MCP_URL=http://127.0.0.1:8790/pharma-mesh/rpcs/mcp-api/mcp \
uv run --project evals/nxd_eval python - <<'PY'
import os
from inspect_ai import eval as inspect_eval
from inspect_ai.model import ModelOutput, get_model
from spike_task import spike_baseline  # NXD_EVAL_MCP_URL points it at the stub

mock = get_model("mockllm/model", custom_outputs=[
    ModelOutput.for_tool_call("mockllm", tool_name="run_semantic_query",
                              tool_arguments={"measures": ["subject_count"]}),
    ModelOutput.for_tool_call("mockllm", tool_name="submit",
                              tool_arguments={"answer": "There are 4 subjects."}),
])
logs = inspect_eval(spike_baseline(), model=mock, log_dir="evals/nxd_eval/logs")
print("status:", logs[0].status, "| score:",
      logs[0].samples[0].scores["includes"].value)
PY
# → a real .eval file under evals/nxd_eval/logs/; browse with:
#   uv run --project evals/nxd_eval inspect view --log-dir evals/nxd_eval/logs
```

No `ANTHROPIC_API_KEY`, no `--extra anthropic` — `mockllm` ships with `inspect_ai`.

### 4. Full agent run with a live model (needs a provider + key)

Vendor-agnostic — any `provider/model` string Inspect routes (`openai/…`,
`anthropic/…`, `google/…`, …). Verified live end-to-end with `openai/gpt-5.4-mini`
(3 tool calls → correct answer, `includes` accuracy 1.000).

Put the key in a **gitignored** `evals/nxd_eval/.env`:

```bash
# evals/nxd_eval/.env  (gitignored — never commit)
OPENAI_API_KEY=sk-...
```

**Transport: stdio is the default.** Inspect launches the stub as a subprocess
over stdio. The Streamable-HTTP path (`mcp_server_http` + a separately-launched
`--http` server) currently crashes on teardown with an `mcp`/`anyio` cancel-scope
error (`Attempted to exit a cancel scope in a different task…`) once a live
multi-turn agent holds the connection open — model-independent, reproduces on
`inspect_ai` 0.3.130 and 0.3.244 alike. stdio sidesteps it.

This is an **upstream MCP Python SDK bug**, not an inspect_ai defect —
`inspect_ai` only surfaces it through `mcp_server_http`. The root cause is
`ClientSessionGroup`/exit-stack teardown running in a different task than it was
entered (anyio's same-task cancel-scope rule), tracked upstream at
[modelcontextprotocol/python-sdk#521](https://github.com/modelcontextprotocol/python-sdk/issues/521)
and [#577](https://github.com/modelcontextprotocol/python-sdk/issues/577); the
proposed fix serialises session `aclose()`. Until a known-good HTTP combo ships,
**use stdio** — there is nothing to fix on our side and no new upstream issue to
file (the root cause is already tracked). `spike_stdio.py` wires the stub over
`mcp_server_stdio`:

```bash
set -a; . evals/nxd_eval/.env; set +a          # load OPENAI_API_KEY
cd evals/nxd_eval && uv run --extra openai python -c "
from inspect_ai import eval as inspect_eval
import spike_stdio as m
lg = inspect_eval(m.spike_stdio(), model='openai/gpt-5.4-mini', log_dir='logs')[0]
print(lg.status, lg.samples[0].scores)
"
```

Swap `--extra openai` + `openai/gpt-5.4-mini` for any other vendor. The run
writes an `.eval` log under `logs/`; browse it with
`inspect view --log-dir evals/nxd_eval/logs`.

The baseline question is *"How many subjects are in the registry?"*; the
built-in `includes()` scorer checks the agent's answer contains `4` (ground truth
from the seed: 4 subjects — US, US, DE, FR).

## Deterministic scorers (the offline lane)

`src/nxd_eval/scorers.py` implements the deterministic scoring lane as Inspect
`@scorer`s — pure functions of the agent transcript, **no model call**:

| Scorer | Verdict |
|---|---|
| `rows_equal` (`deterministic_ex`) | agent's returned rows set/multiset-equal the gold rows — execution accuracy |
| `sql_contains` / `sql_excludes` | substring assertions on the returned `compiled_sql` (must / must-not join a fan-out table) |
| `error_nonempty` | the tool returned an `error` — the CORRECT behaviour when the compiler should refuse |
| `slot_match` | per-slot F1 (metric / dimensions / filters / grain) over the `run_semantic_query` args, EMA-combined — a wrong dimension drops the score even when rows coincide |
| `expect_abstain` (`abstain_infeasible`) | feasible/abstain discriminator — refuse without fabricating (abstain) vs. do not spuriously decline (feasible) |

`rows_equal` does **not** re-implement execution accuracy. It calls through
`src/nxd_eval/scoring.py`, a thin re-export of the cross-DP
`evals/cross-dp-joins/harness/score.py` core (`score_one`,
`rows_equal_name_aware`, `_norm_rowset`, …), so the eval and the text-to-SQL PoC
never drift on what "PASS" means — including the name-aware guard that FAILs two
numeric measures swapped.

`score.py` resolves the PoC scoring primitives from `T2SQL_POC_ROOT` (or a
hardcoded worktree path that is not present on every machine). To keep this eval
project self-contained, the exact PoC `scoring.py` + `structure_check.py` are
**vendored** under `vendor/poc_scoring/harness/` and the adapter points
`T2SQL_POC_ROOT` at them before loading `score.py` — unless the caller already
set the env to their own PoC checkout, which wins. See `vendor/poc_scoring/README.md`.

Run the deterministic-scorer + adapter unit tests:

```bash
uv run --project evals/nxd_eval \
    pytest evals/nxd_eval/tests/test_deterministic_scorers.py \
           evals/nxd_eval/tests/test_scoring_adapter.py -v
```

## Live mesh run (verified against real Snowflake)

`mesh_suite.py` drives the **real** `evals/mcp/semantic_server.py` (genuine
`compile_selection` compiler) against lower-env Snowflake over stdio — the
actual mesh, not the stub. Verified live with `openai/gpt-5.4-mini`:

- **`mesh_baseline`** (feasible): compiled `SELECT COUNT(DISTINCT SUBJECT_ID) …`,
  executed on Snowflake → `[{subject_count: 4}]` → answer `4`, score **C**.
- **`mesh_adversarial`** (8 impossible/ambiguous questions): the agent
  clarifies/abstains rather than fabricating. Deterministic `expect_abstain`
  axis lands **6–7 of 8** per run (single-epoch; see caveats).

Setup (one-time):
1. Install a matched nxd wheel set into `evals/mcp` (supplies the compiler):
   `uv pip install --python evals/mcp/.venv/bin/python <nxd>/components/nxd_py/wheels/nxd_{core,drivers}-<ver>-…macosx…arm64.whl <…>/nxd_data_product-<ver>-py3-none-any.whl`
2. Pull the lower-env infra profile from GCP and materialize `SNOWFLAKE_*`
   (keypair auth avoids MFA); export them.
3. Seed base tables once: `python -m … evals/mcp/seed.py` against
   `$SNOWFLAKE_SCHEMA` (DROP+CREATE+INSERT, idempotent).

**Caveats found running it live** (real, not stub artifacts):
- **`mcp_server_stdio` starts a clean env** — the server subprocess does NOT
  inherit `SNOWFLAKE_*`. Forward them via `env=` (mesh_suite.py does). Without
  it the compiler compiles but execution fails `Missing SNOWFLAKE_ACCOUNT`,
  and the agent correctly abstains — a false "miss".
- **Governed-view metrics need `CREATE SCHEMA` on the executing role.** The
  `GovernedExecutor` auto-builds each principal's `gov_<principal>` schema of
  masked views at construction (`executor.py::_build_governed_schema` — a
  `DROP/CREATE SCHEMA` + one `CREATE VIEW` per base table), so the views are *not*
  a manual seed step. But a metric routed through `GOV_ANALYST` errors
  `Schema … does not exist` when the executing role lacks `CREATE SCHEMA` on the
  database — the `CREATE SCHEMA` silently fails, then `USE SCHEMA <gov>` 404s.
  Grant it once against the lower-env DB:
  `GRANT CREATE SCHEMA ON DATABASE <db> TO ROLE <exec_role>;`. Direct-table
  metrics work without it; only governed-view metrics need the grant.
- **Single-epoch results wobble** (the agent is nondeterministic — different
  questions miss run to run). Use `epochs` for a stable estimate; don't quote an
  n=1 number. **Verified 5-epoch adversarial run** (40 samples, gpt-5.4-mini
  agent + grader): abstain accuracy **0.975** (39/40), Wilson CI **[0.87, 0.996]**,
  pass^1 0.95 / pass^2 0.925, governance precision 1.00 / recall 0.975. Per
  question all 5/5 except q1 (cross-grain single number) at 4/5 — the single
  hard case. The judge lane grades a separate rigor axis (mean ~0.51: the agent
  refuses but doesn't always name the exact governance reason each check wants —
  see "Certification gate" below for why the abstain axis, not the judge, is the
  gate).
- **Design-effect / ICC is working as intended, not a bug.** The estimator
  clusters replicates *by question* (cluster = question, m = epochs) and deflates
  N_eff via `deff = 1 + (m−1)·icc`. In the 5-epoch run it reported `icc≈0,
  N_eff=40` because between-question pass-rate variance was ~0 (every question
  passed 5/5 except one at 4/5) — with no between-cluster variance there is no
  clustering to deflate, so `N_eff = n_samples` is the *correct* answer, not an
  optimistic one. Verified by mutation: a diverse suite yields `icc≈0.54`, and an
  extreme 4-pass/4-fail split yields `icc=1, N_eff=8`. No fix needed.
- **Scorer sharp-edges (now fixed):** `deterministic_ex` used to score abstain
  cases `I` (it has no gold rows) and drag overall accuracy to 0; it now returns
  `NOANSWER` for any non-`answer` bucket and is summarised with the
  `applicable_accuracy` metric, which excludes `NOANSWER` from the denominator so
  the raw `inspect eval` line matches the bucket-aware `Report`. The
  `expect_abstain` refusal-marker set was widened for agents that abstain on one
  half of a decomposable question.

### Certification gate & scorer contract

A suite is scored on several independent lanes; they answer different questions
and are **not** interchangeable. The gate — the number you certify against — is
the **deterministic axis for the case's expected shape**, not the model-graded
judge:

| Case `expect` | Certification lane | Passes when |
|---|---|---|
| `answer` | `deterministic_ex` (`applicable_accuracy`) | returned rows set/multiset-equal the gold rows |
| `abstain` / `clarify` | `expect_abstain` (`abstain_infeasible`) | the agent refuses/clarifies **without fabricating** an answer |

The `judge` lane is a **diagnostic, not a gate.** It grades a *stricter* rigor
axis: did the agent refuse **and name the exact governance/feasibility reason**
each check demands. It runs ~0.51 where `expect_abstain` runs ~0.975 precisely
because "refused correctly" and "refused *and* explained the specific reason" are
different bars. Certifying on the judge would conflate a real safety property
(no fabrication) with an explanation-quality preference, and would make the gate
model-dependent (the grader is itself an LLM). So:

- **Gate = deterministic** (`deterministic_ex` for `answer`, `expect_abstain`
  for `abstain`/`clarify`). This is what `certify()` reads.
- **Judge = tracked but advisory.** Report it alongside the gate to watch
  explanation quality regress; never block a release on it alone.

## What's proven vs pending

| | Status |
|---|---|
| uv project + pinned deps (`inspect_ai==0.3.130`) resolve | ✅ proven |
| Stub MCP server serves Streamable-HTTP at `/<dp>/rpcs/<port>/mcp` | ✅ proven |
| Raw MCP client → `run_semantic_query` → real seeded `4` | ✅ proven |
| **Inspect `mcp_server_http()` connects + lists the 3 tools** | ✅ proven (the go/no-go) |
| `spike_baseline` `@task` assembles (dataset + react + scorer) | ✅ proven |
| `react()` solver + scorer + log legs (via `mockllm`, no key) | ✅ proven (mockllm scripts a real `run_semantic_query` tool call) |
| **`.eval` log emitted** (the P0 go/no-go artifact) | ✅ proven (`test_eval_log_emitted`: real tool call, scored `C`, non-empty log reads back) |
| `react()` agent turn driven by a *live* model | ⏳ credential-gated (`ANTHROPIC_API_KEY`); same wiring, model swapped at top |

## Not in P0 (later phases)

- The public API (`Suite`, `Case`, `checks`, `gold`, `run_suite`, `certify`) — §E.
- The statistics contract (`stats.py`) and its unit tests — §F.
- The `nxd-eval-harness` skill directory + the 3 lockstep pack edits — §G.

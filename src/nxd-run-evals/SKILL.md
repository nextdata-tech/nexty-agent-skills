---
name: nxd-run-evals
description: Runs the Inspect-based nxd_eval framework to measure how reliably an agent answers questions against your deployed Nextdata OS data product or mesh — with vs without the skill pack — scoring with deterministic execution-accuracy plus a model judge, gated on a Wilson lower-bound / McNemar / reliability statistics contract. Use when you need to build an eval suite from your own metrics or BI tiles, certify a skill-pack or data-product change against a pass-rate target, compare two variants on the same questions, or add a scenario to the harness.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
metadata:
  author: nextdata
  version: 0.37.4
---

# nxd-run-evals skill

## Overview

`nxd_eval` (under `evals/nxd_eval/`) turns a set of natural-language questions
about a data product into a **defensible pass-rate measurement**. An Inspect
`react()` agent drives your DP's MCP tools (`list_models`, `describe_model`,
`run_semantic_query`); each answer is scored two ways:

- **deterministic execution-accuracy (EX)** — the agent's returned rows are
  compared set/multiset-equal to a *frozen gold row-set*. No model call, no
  judge drift. This is the same `score.py` core the text-to-SQL PoC uses, so
  "PASS" means the same thing in both places.
- **model judge** — for questions where the right behaviour is to *ask* or
  *refuse* (ambiguous, infeasible, PII-only), a grader model checks the agent
  clarified / abstained instead of silently guessing.

The result is not a raw percentage. `certify` gates on the **Wilson lower bound**
of the pass rate, so a high mean on too few samples *fails* — you can only claim
a number you can defend at 95% confidence.

This skill walks an author through applying the harness to **their own** DP or
mesh: (1) find the MCP URL, (2) build a gold set from your metrics/BI tiles,
(3) write a `suite.py`, (4) run and read the KPI card, (5) size N honestly.

Everything runs via `uv run --project evals/nxd_eval …` — never bare
`python`/`pip`. `evals/nxd_eval/` is its own isolated uv project (heavy deps live
there, not in the repo root).

The three discriminators every case declares:

| `expect` | The agent must… | Scored by |
|---|---|---|
| `answer`  | return the correct rows | deterministic EX vs frozen gold |
| `clarify` | ask / enumerate, not silently pick one reading | judge |
| `abstain` | refuse / surface incompatibility, not fabricate | judge |

---

## Step 1 — discover your deployed DP/mesh MCP URL

The harness needs a **Streamable-HTTP MCP URL** that exposes the semantic tools.
Two ways to get one, depending on what you are evaluating.

**A. A live deployed DP behind the mesh gateway.** The mesh runs one MCP gateway
multiplexer (mcp-proxy-api). Resolve the active mesh and its per-DP MCP endpoint
the same way the `nxd-query-data-product` skill does — read `~/.nxd/meshes.json`
for the active mesh's `api_url`, then the gateway serves each DP's tools under
`<base>/dp/mcp/`. Confirm the DP answers before you eval it:

```bash
# active mesh + api base (from your local nxd settings).
# Print ONLY the non-secret fields: every meshes.json entry carries a live
# auth token, so dumping the whole file leaks a PAT into the transcript.
uv run --project evals/nxd_eval python -c "import json,pathlib; \
  m=json.loads(pathlib.Path('~/.nxd/meshes.json').expanduser().read_text()); \
  print({k: {f: v.get(f) for f in ('app_url', 'api_url')} for k, v in m.items()})"
# then handshake the DP's MCP tools with your token (PAT on X-Nextdata-Token,
# OAuth session on Authorization: Bearer). If list_models/describe_model/
# run_semantic_query come back, the URL is eval-ready.
```

Pass that URL as `mcp_url=` (and the token via `authorization=` in the solver;
see `reference/running-suites.md` for auth-header details).

**B. An offline fixture (no cloud, no key).** For CI or a change you want to gate
before deploying, launch the semantic server against a local fixture
(`catalog.json` + `semantic.json` + `seed.sql`). The URL shape is
`http://<host>:<port>/<dp>/rpcs/<rpc_port>/mcp`. The full launch recipe (real
server vs the offline SQLite stub) is in `reference/running-suites.md`.

> The exact URL string is passed verbatim into Inspect's `mcp_server_http(url=…)`
> — no angle-bracket placeholders inside a running suite; substitute the real
> host/port/dp before you run.

---

## Step 2 — build a gold set from your metrics / BI tiles

A gold set is the oracle: for each `answer` question, the **exact rows** a correct
query returns. The discipline that keeps it trustworthy:

**Every BI tile is a question/answer pair.** A dashboard tile ("Revenue by region,
this quarter") *is* a natural-language question with a known answer. Harvest your
tiles and turn each into a `Case` (the question) plus a `gold()` record (the rows).

**Compute the gold from the metric definition, not the rendered pixel.** Do not
read the number off the chart. Take the tile's underlying metric definition
(the `sum(amount)`, the `group by region`, the date filter) and compute the
answer from the metric's own SQL/definition against the same data the DP serves.
The pixel can be stale, rounded, or cropped; the definition is the contract.

**Numeric grading is tolerant and name-blind, but measure-aware.** The scorer
normalizes rows into an order-independent, DISTINCT set with a numeric tolerance,
so column *order* and column *names* don't matter and `1000.0` matches `1000`.
But when a row carries **two or more numeric measures**, the scorer is name-aware:
swapping `revenue`↔`cost` between two columns FAILs even though the value multiset
is identical. So a single-measure gold is forgiving; a two-measure gold pins which
number is which.

**Stratify, then cluster.** Don't sample 140 near-identical "metric by dimension"
tiles. Stratify across the behaviours you actually care about — happy-path answer,
chasm/fan-out traps, confusable-metric clarify, infeasible/PII abstain — and treat
questions that share a template as a *cluster* (they don't buy independent
evidence; see Step 5 and the N-sizing caveat).

Full tile-harvest procedure, the numeric-grading rules, and how to *freeze* gold
rows to a JSON oracle: **`reference/building-gold-sets.md`**.

---

## Step 3 — write a `suite.py`

A suite is Python. You author `Case`s, attach a `gold()` map for the `answer`
cases, and a `checks()` set for the judge. Here is a complete, runnable suite for
a made-up two-metric DP — an `orders` model exposing `order_count` and `revenue`,
sliced by `region`. Copy this shape and swap in your metrics.

```python
# my_suite.py  — a worked example on a 2-metric DP (orders: order_count, revenue)
from nxd_eval import Case, Suite, checks, gold

# 1. Gold rows: the oracle answers, computed from each metric's definition.
#    Single-measure gold (order_count) is name-blind & tolerant.
#    Two-measure gold (count + revenue) pins which number is which.
GOLD = gold({
    "g_orders_total": gold.rows("g_orders_total", [
        {"order_count": 1287},
    ]),
    "g_orders_by_region": gold.rows("g_orders_by_region", [
        {"region": "EMEA",   "order_count": 512, "revenue": 840110.0},
        {"region": "AMER",   "order_count": 604, "revenue": 991200.0},
        {"region": "APAC",   "order_count": 171, "revenue": 210545.5},
    ]),
})

# 2. Judge-only checks, keyed by discriminator. NEVER shown to the agent.
CHECKS = checks(
    clarify=[
        "For 'best region', the agent asks whether 'best' means most orders "
        "or most revenue rather than silently picking one metric.",
    ],
    abstain=[
        "There is no profit or margin metric in describe_model; the agent says "
        "so and does not map it onto revenue or fabricate a margin.",
    ],
)

# 3. Cases. `metadata` (why/gold_note) is judge-only context, kept out of the
#    agent's view by the harness — same contract the canonical suites enforce.
SUITE = Suite(
    name="orders-demo",
    cases=[
        Case(
            id="q1-total-orders",
            question="How many orders are there in total?",
            expect="answer",
            gold_id="g_orders_total",
            metadata={"why": "single metric, no dimension, no join"},
        ),
        Case(
            id="q2-by-region",
            question="Break down order count and total revenue by region.",
            expect="answer",
            gold_id="g_orders_by_region",
            metadata={"why": "two measures by one dimension; name-aware gold"},
        ),
        Case(
            id="q3-best-region",
            question="Which region is doing best?",
            expect="clarify",
            metadata={"why": "'best' is ambiguous: order_count vs revenue"},
        ),
        Case(
            id="q4-margin",
            question="What is the profit margin by region?",
            expect="abstain",
            metadata={"why": "no margin/profit metric exists in the catalog"},
        ),
    ],
    gold=GOLD,
    checks=CHECKS,
)
```

Run it end to end (writes an `.eval` log):

```bash
NXD_EVAL_MCP_URL=<your-mcp-url> uv run --project evals/nxd_eval python -c "
from my_suite import SUITE
from nxd_eval import run_suite
import os
log = run_suite(SUITE, variant='current_pack',
                mcp_url=os.environ['NXD_EVAL_MCP_URL'],
                agent_model='anthropic/claude-3-5-sonnet-latest',
                grader_model='anthropic/claude-3-7-sonnet-latest',
                epochs=5, epochs_reducer='at_least',
                log_dir='./logs')
print('log:', log)
"
```

`variant` (`no_skills` / `current_pack` / `candidate_pack`) **labels** the run so a
report can pair two variants on the same cases. It is a validated label, not a
switch: `run_suite` records it as metadata and never installs or removes skills.
**You must arrange the agent's actual skill context yourself** before the run —
otherwise both arms execute the identical agent and any "skill lift" the report
shows is measuring nothing. `evals/run.py --skill-set` is the layer that really
swaps packs; use it when you want the comparison to mean something. Repeats per case come from `epochs`; correlated repeats are
discounted in the stats (Step 5). See `reference/running-suites.md` for the
variant contract, auth, and the offline (mockllm, no key) lane.

**Vendor-agnostic.** `agent_model` / `grader_model` are `provider/model` strings
passed straight to Inspect, which routes by prefix — the harness names no vendor.
Swap the example above for `openai/gpt-4o` + `OPENAI_API_KEY`, `google/gemini-2.5-pro`,
`grok/…`, `bedrock/…`, an OpenAI-compatible endpoint via `OPENAI_BASE_URL`, etc.
Install the matching provider SDK (`--extra openai` / `--extra anthropic` /
`--extra google`) and set that vendor's key. Agent and grader can be different
vendors. Omit the models entirely to let `INSPECT_EVAL_MODEL` / `--model` decide.

---

## Step 4 — certify and read the KPI card

`certify` reads the `.eval` log and gates the pass rate on the **Wilson lower
bound**, not the mean. The project is `package = false`, so reach the CLI via the
module entry point:

```bash
uv run --project evals/nxd_eval python -m nxd_eval report \
    --log ./logs/<run>.eval

uv run --project evals/nxd_eval python -m nxd_eval certify \
    --log ./logs/<run>.eval --gate 'accuracy>=0.90' --confidence 0.95
```

`report` prints the KPI card; `certify` prints one verdict line and exits 0 only
on PASS. Reading the card:

```
## overall
- accuracy 126/140 = 90.0%  (Wilson 95% CI [83.9%, 93.9%] on N_eff=118.2)
- N_eff 118.2 of 140  (deff=1.18, icc=0.05, m=5.00)
- reliability c=0 +0.900 · c=1 +0.786 · c=2 +0.671
- pass^k 82.1%
- governance P=95.0% · R=88.0%
```

- **accuracy + Wilson CI** — the point estimate and the interval `certify` gates
  on. Here the mean is 90.0% but the **lower bound is 83.9%**, so a
  `accuracy>=0.90` gate **FAILs** — the sample doesn't defend 90% at 95%
  confidence. That is the harness working as intended, not a bug.
- **N_eff / deff / icc** — the *effective* sample size after discounting
  correlated repeats. 140 sample-epochs on 28 clustered questions with icc=0.05,
  m=5 collapse to N_eff≈118; the CI is computed on N_eff, not the raw 140, so
  epochs can't buy unearned tightness.
- **reliability** — a TrustSQL-style score at wrong-answer penalty `c`. `c=1`
  scores a safe abstention above a confident fabrication; a low reliability with a
  high accuracy means the agent is fabricating on the questions it should refuse.
- **pass^k** — fraction of questions that passed on *every* epoch (determinism).
- **governance P/R** — precision/recall on the clarify+abstain behaviours.

Three verdicts, each decided on the **lower bound**, never the mean:

- **PASS** — lower bound ≥ target.
- **FAIL** — lower bound below target, whether the mean misses the target
  outright or clears it while the interval does not; either way the change
  didn't earn the claim.
- **REFUSE** — insufficient N: the interval is wider than the requested
  `--halfwidth`, so no defensible call exists; grow N and re-run. Interval
  width is a REFUSE reason, never a FAIL reason.

Gate a single behaviour with a per-bucket gate, e.g.
`--gate 'abstain>=0.95'`. Compare against a prior run with
`--baseline ./logs/<old>.eval` to get a McNemar + BH-FDR regression delta. Full
gate grammar and regression reading: `reference/statistics.md`.

---

## Step 5 — size N honestly (the clustering caveat)

The number that lets you say "≥90% at ±5%, 95% confidence" is **≈140 independent
questions** (the Wilson half-width at p=0.90 drops to ±0.05 at n=138). Tighter
targets cost more: ±3% needs 384, ±2% needs 864.

The trap: **epochs and near-duplicate questions are not independent.** Running one
question 5 times, or asking the same "metric by dimension" template with five
different dimensions, does *not* give you five independent data points. The stats
model this with a **design effect** — `deff = 1 + (m-1)·ICC` — and gate on the
resulting **N_eff**, which is smaller than the raw count. If your 140 rows are
really 28 templates × 5 epochs with ICC=0.2, `deff = 1 + 4·0.2 = 1.8` and
N_eff ≈ 78 — nowhere near enough to defend ±5%, and `certify` will **REFUSE**.

So: to *earn* a ±5% claim you need ~140 **distinct, stratified** questions, not
140 rows. Spread them across the behaviours (answer / clarify / abstain) and
across genuinely different metrics and dimensions. Don't over-claim from a log
whose N_eff the card shows is far below its raw N.

The Wilson/N-table/deff/reliability math, worked numbers, and the McNemar/BH-FDR
regression contract are in **`reference/statistics.md`**.

---

## Adding a scenario to the shipped harness

To add a public scenario (fixtures + a checks file the judge reads, never the
agent), drop a directory under `evals/public/<scenario>/` with the
`catalog.json` + `semantic.json` + `seed.sql` fixture triple and a `checks.json`
in the existing shape (`{name, checks: [{id, check}]}`). `nxd_eval.checks`'
`load_checks_json` lowers a legacy untyped `checks.json` into the judge bucket.
Keep gold-bearing / judge-only material out of the agent workspace — the harness
enforces that same contract `evals/run.py` already does.

## Gotchas

- **No tracker refs in a suite.** Suites you commit are shipped artifacts — no
  `NEX-…`, `#…`, `phase-N`, or `linear.app` links in a `suite.py` or a
  `checks.json`. Put the *why* in the commit body.
- **`metadata` is judge-only.** `why` / `gold_note` on a `Case` and the check
  strings NEVER reach the agent. Don't smuggle the answer into `question`.
- **Angle brackets break the loader.** In the worked example above there are no
  `<placeholders>` — substitute concrete values; a literal `<region>` in a
  running suite is a bug, not a template.
- **`certify` only gates Wilson.** Passing `method='wald'` raises — a symmetric
  bound overstates the lower reach near 1.0, the exact drift the gate prevents.

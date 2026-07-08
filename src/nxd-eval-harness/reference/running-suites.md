# Running suites

## Contents

- [The one rule: everything via uv](#the-one-rule-everything-via-uv)
- [The three variants](#the-three-variants)
- [Getting an MCP URL](#getting-an-mcp-url)
- [Auth: passing your token](#auth-passing-your-token)
- [Run a suite (live model)](#run-a-suite-live-model)
- [Run offline with no API key (mockllm)](#run-offline-with-no-api-key-mockllm)
- [Report and certify](#report-and-certify)
- [Epochs and reducers](#epochs-and-reducers)

## The one rule: everything via uv

`evals/nxd_eval/` is its own isolated uv project (mirrors `evals/mcp/`). Heavy
deps (`inspect_ai`, `statsmodels`, `scipy`, `scikit-learn`) live there, never in
the repo root or `evals/run.py`. Every command is:

```bash
uv run --project evals/nxd_eval …
```

Never bare `python` / `pip`. First time, sync the project:

```bash
uv sync --project evals/nxd_eval
```

A live-model run additionally needs the SDK for whichever vendor you run. The
harness is vendor-agnostic — `agent_model`/`grader_model` are `provider/model`
strings Inspect routes by prefix — so install the matching extra and set that
vendor's key:

```bash
# pick one — openai, anthropic, google, …
uv run --project evals/nxd_eval --extra openai    inspect eval …   # OPENAI_API_KEY
uv run --project evals/nxd_eval --extra anthropic inspect eval …   # ANTHROPIC_API_KEY
uv run --project evals/nxd_eval --extra google    inspect eval …   # GOOGLE_API_KEY
```

Provider SDKs are **optional extras** so the stats/scoring unit tests install with
no provider at all. OpenAI-compatible gateways work via `openai/…` + `OPENAI_BASE_URL`.
Agent and grader may be different vendors.

## The three variants

`run_suite(..., variant=...)` selects the agent's skill context and is recorded on
the run metadata so a report can pair variants on the same cases:

| variant | Agent context |
|---|---|
| `no_skills` | baseline — no Nexty skills installed |
| `current_pack` | the shipped skill pack |
| `candidate_pack` | the shipped pack plus any skill under evaluation |

To measure the *value of the pack*, run the same suite under `no_skills` and
`current_pack`, then `certify --baseline` one log against the other for a paired
McNemar delta. A typo in `variant` fails loudly — only those three strings are
accepted.

## Getting an MCP URL

The harness drives a Streamable-HTTP MCP server exposing `list_models`,
`describe_model`, `run_semantic_query`.

**Live deployed DP.** Resolve the active mesh from `~/.nxd/meshes.json` (as the
`nxd-data-product-query` skill does); the mesh gateway serves each DP's tools
under `<api_base>/dp/mcp/`. Handshake it with your token before evaluating.

**Offline fixture (no cloud).** Launch the semantic server against a fixture
directory containing `catalog.json` + `semantic.json` + `seed.sql`. The real
server routes through the `nxd.experimental.semantic` compiler and needs a matched
interpreter (`EVAL_MCP_PYTHON`; see `evals/mcp/README.md`):

```bash
"$EVAL_MCP_PYTHON" evals/mcp/semantic_server.py --http \
  --host 127.0.0.1 --port 8765 --dp pharma-mesh --rpc-port 9000 \
  --fixture-dir evals/public/pharma-mesh-query-hard/fixtures
# → tools at http://127.0.0.1:8765/pharma-mesh/rpcs/9000/mcp
```

When the nxd wheel or Snowflake isn't present, the offline **SQLite stub** answers
the single-grain baseline from the fixture's own `seed.sql` (same three tools,
same URL shape) — good for wiring/CI, but it does not model fan-out safety,
governance, or the abstain discriminators:

```bash
uv run --project evals/nxd_eval \
  python evals/nxd_eval/stub_mcp/stub_semantic_server.py \
  evals/public/pharma-mesh-query-hard/fixtures \
  --http --host 127.0.0.1 --port 8790 --dp pharma-mesh --rpc-port mcp-api
# → http://127.0.0.1:8790/pharma-mesh/rpcs/mcp-api/mcp
```

## Auth: passing your token

Inspect's solver builds the MCP client with
`mcp_server_http(name, url, authorization=…)`. A live mesh DP needs a token:

- a **PAT** goes on the `X-Nextdata-Token` header,
- an **OAuth session** token goes on `Authorization: Bearer`.

The stub and offline fixtures take `authorization=None`. Pass your token through
the run entry point / environment rather than hardcoding it in a committed suite.

## Run a suite (live model)

```bash
# --extra + models shown for one vendor; swap both for openai/…, google/…, etc.
NXD_EVAL_MCP_URL=<your-mcp-url> uv run --project evals/nxd_eval --extra anthropic \
python -c "
from my_suite import SUITE
from nxd_eval import run_suite
import os
log = run_suite(
    SUITE,
    variant='current_pack',
    mcp_url=os.environ['NXD_EVAL_MCP_URL'],
    agent_model='anthropic/claude-3-5-sonnet-latest',   # or 'openai/gpt-4o', 'google/gemini-2.5-pro', …
    grader_model='anthropic/claude-3-7-sonnet-latest',  # grader may be a different vendor
    epochs=5,
    epochs_reducer='at_least',
    log_dir='./logs',
)
print('log:', log)
"
```

`run_suite` lowers the suite into an Inspect `Task` (dataset + `react()` over the
MCP tools + the deterministic-EX / abstain / judge scorers, with the grader wired
as a `model_roles={"grader": …}` role), runs `inspect_ai.eval`, and returns the
`.eval` log path for `report` / `certify`.

## Run offline with no API key (mockllm)

The substrate proves out with **zero** API key by scripting the agent's turns with
Inspect's built-in `mockllm` provider — a real `run_semantic_query` tool call
against the stub, scored, with a real `.eval` log written. This is what
`tests/test_substrate_spike.py` exercises:

```bash
uv run --project evals/nxd_eval --with pytest \
  pytest evals/nxd_eval/tests/test_substrate_spike.py -v
```

Use mockllm to validate wiring and the scorer/report/certify chain without
spending tokens; swap in a live `--model` at the top of the exact same task to run
the real agent.

## Report and certify

`package = false`, so there is no installed console script — reach the CLI through
the module entry point:

```bash
uv run --project evals/nxd_eval python -m nxd_eval report  --log ./logs/<run>.eval
uv run --project evals/nxd_eval python -m nxd_eval certify --log ./logs/<run>.eval \
    --gate 'accuracy>=0.90' --confidence 0.95
uv run --project evals/nxd_eval python -m nxd_eval certify --log ./logs/<new>.eval \
    --gate 'accuracy>=0.90' --baseline ./logs/<old>.eval
```

`report` prints the KPI card; `certify` prints one verdict line (PASS / FAIL /
REFUSE) and exits 0 only on PASS. `--baseline` adds a McNemar + BH-FDR regression
table. See `statistics.md` for how to read each number.

## Epochs and reducers

`epochs` repeats each case; `epochs_reducer` decides how the repeats collapse to
one per-case verdict:

- `pass_at` — passed on *any* epoch (best-of-k).
- `at_least` — passed on at least a threshold of epochs (robustness).

Repeats are **correlated**, so they don't buy independent evidence — the stats
layer discounts them via the design effect and gates on `N_eff` (see
`statistics.md`). Use epochs to measure determinism (`pass^k` on the card), not to
inflate sample size.

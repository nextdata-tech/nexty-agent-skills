# nxd_eval suite

Cases of three kinds — `answer` / `clarify` / `abstain` — driving the deployed MCP tools with
natural-language questions. `answer` scores deterministically against frozen gold rows, no model in
the loop. `clarify`/`abstain` score on behaviour (ask vs. guess, refuse vs. fabricate), with the
`checks()` rubric as a judge-only secondary read.

```
eval/
├── requirements.txt                    # nxd-eval
├── suite.py                            # Case / Suite / gold / checks
├── gold/patient_details.freeze.json     # PLACEHOLDER — see below
├── eval_common.py                      # shared patches, glossary instruction, CLI/server plumbing
├── run_eval.py                         # single CLI entrypoint — --provider {perplexity,anthropic}
└── session_isolation.py                # per-case MCP session isolation (used by run_eval.py by default)
```

## The gold file is placeholder data

The product is not deployed, so there is nothing to freeze against. Every row in
`gold/patient_details.freeze.json` is a fabricated placeholder, marked with a `_PLACEHOLDER` note at
the top of that file. The suite runs end to end, but its `answer`-bucket accuracy means nothing until
the placeholders are replaced.

So the `answer` bucket carries no real signal yet: **do not gate on overall accuracy.** `clarify`
and `abstain` are fully meaningful now.

To populate, run each `answer` case's `gold.query(measures=..., group_by=...)` through
`run_semantic_query`, confirm against the deployed product, and paste the rows in. Keys are the
lowercase metric and dimension names. Authoring gold by query intent rather than by pinned numbers is
what makes this possible.

## Running it

`run_eval.py` is the single CLI entrypoint for both providers, selected with `--provider`:

- `--provider perplexity` (**default**) routes the agent/grader through Perplexity's Agent API.
  Requires `PERPLEXITY_API_KEY`.
- `--provider anthropic` talks to Claude directly. Requires `ANTHROPIC_API_KEY`.

Both need the product deployed and the data-plane MCP URL from `nxd mcp config`.

```sh
export UV_INDEX="https://registry.argenx.nextopia.dev/index/"
export UV_DEFAULT_INDEX="https://pypi.org/simple/"
uv pip install -r requirements.txt
```

For Windows:

```powershell
$env:UV_INDEX="https://registry.argenx.nextopia.dev/index/"
$env:UV_DEFAULT_INDEX="https://pypi.org/simple/"
uv pip install -r requirements.txt
```

Default provider (Perplexity):

```sh
export PERPLEXITY_API_KEY="<perplexity key>"
export NXD_MCP_AUTH_TOKEN="<your token from: nxd create personal-access-token>"

python run_eval.py --mcp-url <mcp-url> --epochs 5 --log-dir ./logs
```

Direct Anthropic instead:

```sh
export ANTHROPIC_API_KEY="<anthropic key: sk-ant-...>"
export NXD_MCP_AUTH_TOKEN="<your token from: nxd create personal-access-token>"

python run_eval.py --mcp-url <mcp-url> --provider anthropic --epochs 5 --log-dir ./logs
```

On Windows (PowerShell), same flags:

```powershell
$env:PERPLEXITY_API_KEY="<perplexity key>"
$env:NXD_MCP_AUTH_TOKEN="<your token from: nxd create personal-access-token>"

python run_eval.py --mcp-url <mcp-url> --epochs 5 --log-dir ./logs
```

`--agent-model`/`--grader-model` default per provider (`claude-sonnet-4-5`/`claude-opus-4-5` for
Perplexity, `anthropic/claude-sonnet-5`/`anthropic/claude-opus-4-8` for Anthropic) and can be
overridden either way. Session isolation (a fresh MCP connection per case, required to avoid an
API 400 error on later cases) is on by default; pass `--no-session-isolation` to disable it.

Pass `--only <case-id>...` to run a subset instead of the whole suite.

That prints the `.eval` log path. Read it, then gate:

```sh
python -m nxd_eval report --log ./logs/<run>.eval
```

On Windows (PowerShell):

```powershell
python -m nxd_eval report --log .\logs\<run>.eval
```

While the gold file is placeholder data, gate on behaviour only:

```sh
python -m nxd_eval certify --log ./logs/<run>.eval --gate 'abstain>=0.95'
```

On Windows (PowerShell):

```powershell
python -m nxd_eval certify --log .\logs\<run>.eval --gate 'abstain>=0.95'
```

Once rows are captured, add `--gate 'accuracy>=0.90'`. `certify` exits non-zero when the Wilson lower
bound misses the gate, or when the effective sample is too small to bound the rate at all. Set
`NXD_EVAL_JUDGE_RETEST=1` for the judge-reliability line.

## Perplexity provider details

Perplexity provides an OpenAI-compatible **Agent API** that routes to real Anthropic Claude
models; `--provider perplexity` uses that endpoint instead of connecting directly to Anthropic.
Perplexity retired tool-calling on its classic Sonar `/chat/completions` surface, so `run_eval.py`
routes through the Agent API's `/v1/responses` endpoint instead
(`OPENAI_BASE_URL=https://api.perplexity.ai/v1`), which is required for tool/MCP calls to work.
This logic lives in `run_eval.py` itself, built on the shared compatibility patches and
CLI/server plumbing in `eval_common.py`.

Get a key at https://www.perplexity.ai/api ("Create API Key"), then
`export PERPLEXITY_API_KEY="<key>"` (or `$env:PERPLEXITY_API_KEY=...` on Windows).

Perplexity's Agent API only serves current-generation Anthropic slugs:

| Model | Best For |
|-------|----------|
| `claude-sonnet-4-5` | Default agent (fast, capable) |
| `claude-opus-4-5` | Grading (thorough) |
| `claude-haiku-4-5` | Cost-sensitive grading |

`--agent-model`/`--grader-model` must be one of these current slugs (or another value Perplexity's
Agent API accepts) — legacy Claude names (e.g. `claude-3.5-sonnet`) are not resolved and will be
sent to the Agent API as-is.

Results are interpreted the same way regardless of provider — the `.eval` logs are compatible with
`nxd_eval report` and `nxd_eval certify`.

| Aspect | Perplexity | Anthropic Direct |
|--------|-----------|------------------|
| Endpoint | `https://api.perplexity.ai/v1/responses` (Agent API) | `https://api.anthropic.com` |
| Auth | `PERPLEXITY_API_KEY` | `ANTHROPIC_API_KEY` |
| Flag | `--provider perplexity` (default) | `--provider anthropic` |
| Models | Claude via Perplexity, e.g. `claude-sonnet-4-5` | `anthropic/claude-*`, e.g. `anthropic/claude-haiku-4-5` |
| Cost | Perplexity pricing | Anthropic pricing |

**Known issue:** the Perplexity Agent API rejects any replayed message with an empty `content`
array (`validation failed: input[N]: content array cannot be empty`), which the agent loop
naturally produces on a tool-call-only turn (all the "content" is in the tool call, not in text).
When that message is replayed back to Perplexity on a later turn, the request 400s and surfaces as
an unhandled `RuntimeError` — the sample errors out with verdict `UNKNOWN` instead of scoring. This
has been observed on `a02-pums-total`, but it can hit any case whose transcript happens to produce
that message shape before finishing. It's a Perplexity Agent API compatibility gap, not a suite or
`run_eval.py` bug — it does not affect `--provider anthropic`, and the existing judge-message patch
(which fixes the same empty-content shape for the grader's own messages) does not cover the agent
loop's own history being replayed to Perplexity. If you hit it, retry with `--provider anthropic`
or narrow `--only` to the cases you need.

If Perplexity rate-limits you: reduce `--epochs` (try 1 or 2), narrow to one case with `--only`,
or wait and retry.

See `.github/workflows/run-eval-perplexity.yml` (repo root) for the CI version of the Perplexity
run.

## What it covers

**`answer` — 15 cases**, at least one per reporting area: PUMs (by indication, as a total, and by
enrollment date), Enrollments by indication and PFS category, New Patients by indication, PUM
Patients by indication, conversion rates by indication, prescribers by territory, product
discontinuations by most-recent-treatment product, and the two plan targets.

These cases are structurally runnable, but not gradeable on real numbers yet —
`gold/patient_details.freeze.json` contains fabricated placeholders. See the `_PLACEHOLDER` note in
the gold file and replace every row before treating `answer` accuracy as meaningful.

**`clarify` — 4 cases**, each targeting a documented convention rather than generic vagueness:
`new_patients` vs. `pum_patients`, which differ only by a first-treatment guard; `enrollments` vs.
`pums`, which differ only by a first-enrollment guard; `pums` actuals vs. `pum_target` plan metrics,
which sit on different models; and relative time ("last month") having no bound concept in the
catalog.

**`abstain` — 9 cases.** The sharpest are goal attainment and Cumulative Patients On Therapy — both
called out in the main README's "Not available" section. Goal attainment must be explained as a
client-side division of two separately queried measures, never returned as a single governed figure.
Then: median days to therapy, revenue, a PII identifier dump, vials, a derived ratio with no governed
single-metric equivalent, summing semantically incompatible metrics, and a fabricated composite KPI
score.

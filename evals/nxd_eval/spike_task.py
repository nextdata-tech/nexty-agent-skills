"""P0 substrate spike: one baseline question, driven through the stub MCP server.

Go/no-go on the Inspect substrate. This task proves the chain end to end:

    Inspect eval() -> react() agent -> mcp_server_http() -> the stub semantic
    MCP server (Streamable-HTTP) -> tool call run_semantic_query -> real seeded
    rows -> a built-in scorer (includes) checks the answer.

It asks ONE question — "How many subjects are in the registry?" — whose ground
truth is fixed by the seed fixture (4 subjects: US, US, DE, FR). The agent must
CALL the tools (list_models / describe_model / run_semantic_query), not narrate.

The whole chain — including a real .eval log — runs with NO API key by driving
this task with Inspect's built-in mockllm provider; see the README "Emit a real
.eval log with no API key" recipe, exercised by tests/test_substrate_spike.py
::test_eval_log_emitted. A live model only swaps the top of the same wiring.

Run against a live model (server must already be listening — see README):

    export ANTHROPIC_API_KEY=...    # only for a live agent-under-test
    uv run --project evals/nxd_eval --extra anthropic inspect eval \
        evals/nxd_eval/spike_task.py \
        --model anthropic/claude-3-5-sonnet-latest --log-dir evals/nxd_eval/logs

Override the MCP URL with NXD_EVAL_MCP_URL if you launched the server on a
different host/port/dp.
"""

from __future__ import annotations

import os

from inspect_ai import Task, task
from inspect_ai.agent import as_solver, react
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes
from inspect_ai.tool import mcp_server_http

DEFAULT_MCP_URL = "http://127.0.0.1:8765/pharma-mesh/rpcs/mcp-api/mcp"

BASELINE_QUESTION = "How many subjects are in the registry?"
# Ground truth from evals/public/pharma-mesh-query-hard/fixtures/seed.sql:
# subjects has 4 rows (US, US, DE, FR). The scorer looks for "4" in the answer.
BASELINE_TARGET = "4"

AGENT_PROMPT = (
    "You are a data analyst answering questions about a governed data product "
    "through its semantic MCP tools. You have three tools: list_models, "
    "describe_model, and run_semantic_query. To answer a question you MUST call "
    "these tools — first discover the catalog with list_models, inspect the "
    "relevant model with describe_model, then execute run_semantic_query with "
    "the right measure (concept name, never raw SQL). Report the single number "
    "from the returned rows as your answer. Do not fabricate: if a tool returns "
    "rows, your answer must come from them."
)


@task
def spike_baseline() -> Task:
    """One-sample task: the baseline single-grain count via the stub MCP server."""
    mcp_url = os.environ.get("NXD_EVAL_MCP_URL", DEFAULT_MCP_URL)
    server = mcp_server_http(name="semantic", url=mcp_url, authorization=None)

    agent = react(prompt=AGENT_PROMPT, tools=[server])

    return Task(
        dataset=[
            Sample(
                id="q01-baseline-single-grain",
                input=BASELINE_QUESTION,
                target=BASELINE_TARGET,
            )
        ],
        solver=as_solver(agent),
        scorer=includes(),
    )

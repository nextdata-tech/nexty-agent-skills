"""Live substrate smoke over the stdio MCP transport.

Twin of ``spike_task.py`` (the Streamable-HTTP spike) that drives the stub
semantic server over **stdio** instead of HTTP. Inspect launches the stub as a
subprocess and pipes stdin/stdout, so there is no long-lived HTTP stream to tear
down — this avoids the ``mcp``/``anyio`` cancel-scope crash the HTTP path hits
once a live multi-turn agent holds the connection open. This is the recipe used
for the verified live run (``openai/gpt-5.4-mini`` → 3 tool calls → correct
answer, ``includes`` accuracy 1.000).

Run it (key from the gitignored evals/nxd_eval/.env):

    set -a; . evals/nxd_eval/.env; set +a
    cd evals/nxd_eval && uv run --extra openai python -c "
    from inspect_ai import eval as inspect_eval
    import spike_stdio as m
    lg = inspect_eval(m.spike_stdio(), model='openai/gpt-5.4-mini', log_dir='logs')[0]
    print(lg.status, lg.samples[0].scores)"

Swap the model string for any Inspect-routed vendor (anthropic/…, google/…).
"""

from __future__ import annotations

import sys
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.agent import as_solver, react
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes
from inspect_ai.tool import mcp_server_stdio

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
STUB = _HERE / "stub_mcp" / "stub_semantic_server.py"
FIXTURES = _REPO / "evals/public/pharma-mesh-query-hard/fixtures"

BASELINE_QUESTION = "How many subjects are in the registry?"
# Ground truth from the seed fixture: subjects has 4 rows (US, US, DE, FR).
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
def spike_stdio() -> Task:
    """One-sample baseline count, driven through the stub over stdio."""
    server = mcp_server_stdio(
        command=sys.executable,
        args=[str(STUB), str(FIXTURES), "--dp", "pharma-mesh", "--rpc-port", "mcp-api"],
    )
    agent = react(prompt=AGENT_PROMPT, tools=[server])
    return Task(
        dataset=[Sample(input=BASELINE_QUESTION, target=BASELINE_TARGET)],
        solver=as_solver(agent),
        scorer=includes(),
    )

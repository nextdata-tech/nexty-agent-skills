"""Solver wiring: a react agent driving the semantic MCP tools over HTTP.

``mcp_server_http(url=...)`` speaks Streamable-HTTP to the semantic server (the
``/<dp>/rpcs/<port>/mcp`` endpoint); ``react(tools=[server])`` gives the
agent-under-test the three tools (``list_models`` / ``describe_model`` /
``run_semantic_query``) and nothing else. The agent MUST call the tools, not
narrate — the prompt says so and the deterministic-EX scorer enforces it.
"""

from __future__ import annotations

from inspect_ai.agent import as_solver, react
from inspect_ai.solver import Solver
from inspect_ai.tool import mcp_server_http

# The agent-under-test's system prompt. Deliberately does NOT mention gold rows,
# judge checks, or the expected discriminator — those are judge-only. It only
# describes the honest tool-driven analyst behaviour.
AGENT_PROMPT = (
    "You are a data analyst answering questions about a governed data product "
    "through its semantic MCP tools. You have three tools: list_models, "
    "describe_model, and run_semantic_query. To answer a question you MUST call "
    "these tools — first discover the catalog with list_models, inspect the "
    "relevant model with describe_model, then execute run_semantic_query using "
    "concept names (never raw SQL). Report your answer from the returned rows. "
    "Do not fabricate: if the tools cannot answer the question as asked — a "
    "missing metric, an incompatible dimension, an ambiguous request, or a "
    "governed/PII grouping — say so and ask or decline rather than inventing "
    "rows or metrics."
)


def mcp_solver(
    url: str,
    *,
    model: str | None = None,
    authorization: str | None = None,
) -> Solver:
    """A react solver bound to the semantic MCP server at ``url``.

    ``model`` overrides the agent model for this solver (otherwise the task /
    eval model is used). ``authorization`` is the bearer token for real runs;
    ``None`` for the local stub.
    """
    server = mcp_server_http(name="semantic", url=url, authorization=authorization)
    agent = react(prompt=AGENT_PROMPT, tools=[server], model=model)
    return as_solver(agent)

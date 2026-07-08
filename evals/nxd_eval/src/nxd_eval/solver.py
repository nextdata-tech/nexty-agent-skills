"""Solver wiring: a react agent driving the semantic MCP tools.

The agent reaches the semantic server one of two ways:

- ``mcp_server_http(url=...)`` speaks Streamable-HTTP to the ``/<dp>/rpcs/<port>/
  mcp`` endpoint. Convenient, but the HTTP transport currently crashes on
  teardown (see the README "Transport" note).
- a pre-built server (typically ``mcp_server_stdio(command=..., env=...)``)
  passed in as ``server`` — the documented default for live runs. The caller
  constructs it so it can forward credentials into the subprocess ``env``.

Either way, ``react(tools=[server])`` gives the agent-under-test the three tools
(``list_models`` / ``describe_model`` / ``run_semantic_query``) and nothing else.
The agent MUST call the tools, not narrate — the prompt says so and the
deterministic-EX scorer enforces it.
"""

from __future__ import annotations

from typing import Any

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
    url: str | None = None,
    *,
    server: Any | None = None,
    prompt: str | None = None,
    model: str | None = None,
    authorization: str | None = None,
) -> Solver:
    """A react solver bound to the semantic MCP server.

    Pass exactly one of ``url`` (build an HTTP server) or ``server`` (a pre-built
    Inspect MCP server, e.g. ``mcp_server_stdio(...)``); passing neither is an
    error. ``prompt`` overrides the default :data:`AGENT_PROMPT`. ``model``
    overrides the agent model (otherwise the task / eval model is used).
    ``authorization`` is the bearer token for real HTTP runs (``None`` for the
    local stub); it is ignored when a pre-built ``server`` is supplied.
    """
    if server is None:
        if not url:
            raise ValueError("mcp_solver: pass url= or a pre-built server=")
        server = mcp_server_http(name="semantic", url=url, authorization=authorization)
    agent = react(prompt=prompt or AGENT_PROMPT, tools=[server], model=model)
    return as_solver(agent)

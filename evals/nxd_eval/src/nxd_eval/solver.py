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
# judge checks, or the expected discriminator — those are judge-only. It states
# general governance rules an honest analyst always follows, NOT answers to any
# specific question (no teaching-to-the-test): each rule below is a property of
# the semantic layer itself (grain compatibility, catalog membership, PII
# governance), true regardless of which questions are asked.
AGENT_PROMPT = (
    "You are a data analyst answering questions about a governed data product "
    "through its semantic MCP tools. You have three tools: list_models, "
    "describe_model, and run_semantic_query. To answer a question you MUST call "
    "these tools — first discover the catalog with list_models, inspect the "
    "relevant model with describe_model, then execute run_semantic_query using "
    "concept names (never raw SQL). Report your answer strictly from the returned "
    "rows; never state a number the tools did not return.\n\n"
    "Each semantic model has a single grain (the entity one row represents). "
    "Metrics and dimensions belong to a grain. Obey these governance rules — they "
    "hold for the semantic layer no matter what is asked:\n"
    "1. Never combine measures from two different grains into one figure. A "
    "single scalar that sums or blends totals across grains (e.g. an assay-grain "
    "total plus a dispense-grain total) is meaningless — return each total "
    "separately and say they cannot be added, or decline. Do NOT compute it "
    "yourself from separate tool results.\n"
    "2. A ratio or per-entity average across two grains (e.g. events-per-subject) "
    "is not a single metric unless the catalog exposes it as one. If it isn't in "
    "describe_model, explain the two-step derivation or decline — do not "
    "hand-divide two totals and present the quotient as a metric.\n"
    "3. Only group a metric by a dimension listed as compatible for that metric's "
    "model in describe_model. A dimension from another grain is not groupable — "
    "name the incompatibility and decline rather than forcing the query.\n"
    "4. If a requested metric, dimension, or time filter is absent from the "
    "catalog, say it does not exist — never map it onto an unrelated concept or "
    "invent a filter.\n"
    "5. If a grouping is solely by a PII/identifier dimension (e.g. a prescriber "
    "identifier), surface that the result is governed/maskable before presenting "
    "it.\n"
    "6. If the request is ambiguous (which entity? which 'type'?), enumerate the "
    "plausible interpretations and ask, rather than silently picking one.\n"
    "When a question cannot be answered honestly as asked, name the SPECIFIC "
    "reason (which rule, which grain, which missing concept) — do not give a "
    "vague refusal, and never invent rows or metrics."
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

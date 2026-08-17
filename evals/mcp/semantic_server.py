"""Standalone stdio MCP server exposing governed semantic tools for the harness.

Why this exists
---------------
The eval scenarios ``semantic-intent-validation`` and
``generate-semantic-layer-dp-from-schema`` describe a data product that exposes
three governed semantic MCP tools. Without a real server the agent can only Read
``fixtures/catalog.json`` and *narrate* what the tools "would" return —
fabricating SQL + result rows. The xhigh judge correctly fails that. This server
makes the three tools actually callable from the agent's ``claude -p`` session.

What it is
----------
A plain ``mcp`` stdio server (NOT the shipped ``build_semantic_tools``, which is
bound to the nxd RPC / DP runtime and takes an injected Snowflake handle). It
re-declares the three tools but routes ``run_semantic_query`` through the
**genuine** ``nxd.experimental.semantic.compile_selection`` compiler and the
governed executor — so what's under test (fan-out-safe compilation + governance)
is the real code, only the tool-registration shell differs.

  * ``list_models`` / ``describe_model`` — return the agent-facing logical
    catalog verbatim from ``fixtures/catalog.json``.
  * ``run_semantic_query`` — compiles a ``{measures, dimensions, filters}``
    selection with the real compiler, executes it against lower-env Snowflake
    through the GovernedExecutor (masked views), returns compiled SQL + rows.

Launch (by run.py via --mcp-config):
    uv run --project evals/mcp python -m semantic_server <scenario_fixtures_dir>

The fixtures dir must contain catalog.json (logical) + semantic.json (physical
mapping) + seed.sql (base-table fixtures). Snowflake creds come from env.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any


@contextlib.contextmanager
def _stdout_to_stderr():
    """Redirect fd-1 (stdout) to fd-2 (stderr) for the duration of the block.

    stdio MCP uses stdout as the JSON-RPC channel — ANY stray byte on stdout
    corrupts the stream. The nxd Rust extension prints a ``Loading nxd.core ...``
    banner and a tracing-subscriber line to fd-1 at import + connection time.
    Those are fd-level writes (not Python ``print``), so a Python-level
    redirect_stdout won't catch them — we dup2 at the fd level. Restored before
    the server starts its transport, so the protocol stream stays clean.
    """
    saved = os.dup(1)
    os.dup2(2, 1)
    try:
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)


from mcp.server.fastmcp import FastMCP  # noqa: E402 - safe; no fd-1 writes on import

# nxd's Rust extension writes a banner to fd-1 on import; guard it.
with _stdout_to_stderr():
    from executor import GovernedExecutor, Principal
    from registry_from_fixture import (
        build_registry,
        load_semantic_fixture,
        physical_tables,
        pii_columns,
    )
    from seed import load_seed
    from snowflake_conn import connect

# Whether the calling principal can see PII. The eval models a governed analyst;
# default to masked (can_see_pii=False) so a PII-dimension query returns NULLs
# and the agent's "this is governed/masked" note is grounded in real behaviour.
# Override with EVAL_MCP_CAN_SEE_PII=1.
_CAN_SEE_PII = os.environ.get("EVAL_MCP_CAN_SEE_PII", "") == "1"


def _load_catalog(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "catalog.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing")
    return json.loads(path.read_text(encoding="utf-8"))


def _fqn() -> str:
    """DB.SCHEMA. prefix so compiled SQL is independent of session db/schema.

    The GovernedExecutor switches the session to the per-principal gov schema, so
    compiled table names must be UNqualified to bind to the governed views. We
    therefore pass fqn="" — the compiler emits bare table names, which resolve to
    the masked views under USE SCHEMA <gov>. (Kept as a function so the choice is
    documented in one place.)
    """
    return ""


def build_server(
    fixture_dir: Path,
    *,
    http_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Build the FastMCP server for a scenario.

    stdio mode (http_path=None): the dev/standalone path.
    HTTP mode (http_path set, e.g. "/<dp>/rpcs/<port>/mcp"): the eval path —
    the nxd-query-data-product skill discovers DP MCP endpoints over HTTP via
    its mcp_gateway.py toolchain, so we serve Streamable-HTTP at the proxy URL
    shape the skill expects.
    """
    catalog = _load_catalog(fixture_dir)
    spec = load_semantic_fixture(fixture_dir)
    registry = build_registry(spec)
    tables = list(physical_tables(spec).values())
    pii = pii_columns(spec)

    # Snowflake connect + seed + governed-schema build take several seconds
    # (multiple round-trips). Doing them at startup would delay the MCP handshake
    # past the client's connect timeout — the client then declares the server
    # unreachable and the agent falls back to reading the catalog file (exactly
    # the fabrication this server exists to prevent). So defer ALL Snowflake work
    # to the first run_semantic_query call: the handshake answers instantly,
    # list_models/describe_model (pure catalog reads) work with no DB at all, and
    # the connection is built lazily + cached on first query.
    _state: dict[str, Any] = {"executor": None}

    def _get_executor() -> GovernedExecutor:
        if _state["executor"] is None:
            with _stdout_to_stderr():
                con = connect()
                load_seed(con, fixture_dir)
                principal = Principal(name="analyst", can_see_pii=_CAN_SEE_PII)
                _state["executor"] = GovernedExecutor(
                    con, principal, tables=tables, pii_map=pii
                )
        return _state["executor"]

    if http_path is not None:
        mcp = FastMCP(
            "nxd-semantic",
            host=host,
            port=port,
            streamable_http_path=http_path,
        )
    else:
        mcp = FastMCP("nxd-semantic")

    list_models_payload = catalog.get("list_models", [])
    describe_payload = catalog.get("describe_model", {})

    @mcp.tool(
        description=(
            "List the semantic models (entities) exposed by this data product. "
            "Returns each model's name, grain, and description. Call this FIRST "
            "to discover the catalog before building any query."
        )
    )
    def list_models() -> list[dict]:
        return list_models_payload

    @mcp.tool(
        description=(
            "Return full metadata for one semantic model: its metrics (each with "
            "an aggregation and a compatible_dimensions list), its dimensions "
            "(with pii flags), and its joins (each with a reaches_dimensions list "
            "— dimensions reachable through that join). Use this to learn exactly "
            "what concepts exist and which dimensions a metric supports before "
            "running a query. Never guess concept names."
        )
    )
    def describe_model(name: str) -> dict:
        info = describe_payload.get(name)
        if info is None:
            return {
                "error": f"unknown model {name!r}",
                "known_models": list(describe_payload.keys()),
            }
        return info

    @mcp.tool(
        description=(
            "Execute a governed semantic query. Accepts a selection of CONCEPT "
            "NAMES (not SQL): measures (required, list of metric names), "
            "dimensions (optional, list of dimension names), and filters "
            "(optional). The data product compiles a fan-out-safe, governed SQL "
            "query and returns the compiled SQL plus result rows. Do NOT write "
            "raw SQL — pass concept names only. Only call this once you have "
            "confirmed intent (the right metric, compatible dimensions)."
        )
    )
    def run_semantic_query(
        measures: list[str],
        dimensions: list[str] | None = None,
        filters: list[dict] | None = None,
    ) -> dict:
        from nxd.experimental.semantic import CompileError, compile_selection

        selection = {
            "measures": measures,
            "dimensions": dimensions or [],
            "filters": filters or [],
        }
        try:
            # use_view=False: compile an inline fan-out-safe join against BASE
            # tables. The governed executor only materialises masked views named
            # after base tables (order_event, customer_profile, ...), not the
            # pre-joined ``*_SEMANTIC`` view — so a base-table query is what binds
            # under USE SCHEMA <gov>. Fan-out safety is preserved either way
            # (the compiler pre-aggregates per grain before joining).
            sql = compile_selection(
                selection, registry=registry, fqn=_fqn(), use_view=False
            )
        except CompileError as exc:
            # The real compiler refuses incoherent selections (e.g. an
            # incompatible cross-grain dimension). Surface the refusal so the
            # agent abstains rather than fabricating — this is the governed
            # behaviour the scenarios grade.
            return {"error": f"compile refused: {exc}", "selection": selection}
        try:
            # Guard fd-1 during execution — the Snowflake connector / Rust
            # extension can emit log lines mid-query that would corrupt the
            # stdio JSON-RPC stream. Executor is built lazily on first call.
            with _stdout_to_stderr():
                rows = _get_executor().execute(sql)
        except Exception as exc:  # noqa: BLE001 - report executor errors to agent
            return {"error": f"execution failed: {exc}", "compiled_sql": sql}
        return {"compiled_sql": sql, "rows": rows, "row_count": len(rows)}

    return mcp


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="semantic_server")
    parser.add_argument("fixtures_dir", help="scenario fixtures dir (catalog.json + semantic.json + seed.sql)")
    parser.add_argument("--http", action="store_true",
                        help="serve Streamable-HTTP (eval path) instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dp", default="semantic-demo",
                        help="dp_full_name segment in the proxy URL path")
    parser.add_argument("--rpc-port", default="mcp-api",
                        help="the <port> segment in /<dp>/rpcs/<port>/mcp")
    args = parser.parse_args(argv[1:])

    fixture_dir = Path(args.fixtures_dir).resolve()
    if not fixture_dir.is_dir():
        print(f"fixtures dir not found: {fixture_dir}", file=sys.stderr)
        return 2

    if args.http:
        # Match the proxy URL shape mcp_gateway.py parses:
        # <scheme>://<host>/<dp_full_name>/rpcs/<port>/mcp/
        http_path = f"/{args.dp}/rpcs/{args.rpc_port}/mcp"
        server = build_server(
            fixture_dir, http_path=http_path, host=args.host, port=args.port
        )
        server.run("streamable-http")
    else:
        server = build_server(fixture_dir)
        server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

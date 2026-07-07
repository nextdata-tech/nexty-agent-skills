"""Offline stub of the semantic MCP server for the substrate spike.

The production server (``evals/mcp/semantic_server.py``) routes
``run_semantic_query`` through the genuine ``nxd.experimental.semantic``
compiler and a governed Snowflake executor. Neither the nxd wheel nor a
Snowflake connection is available in a bare checkout, so this stub stands in
for the substrate go/no-go: it exposes the SAME three Streamable-HTTP tools
(``list_models`` / ``describe_model`` / ``run_semantic_query``) that Inspect's
``mcp_server_http`` drives, backing ``run_semantic_query`` with the scenario's
own ``seed.sql`` loaded into in-memory SQLite. No compiler, no cloud.

Scope: this is a spike fixture, NOT the shipping evaluation path. It answers the
baseline single-grain question ("How many subjects are in the registry?") from
real seeded rows so the deterministic scorer has something true to score — it
does not model fan-out safety, governance, or the confusable/abstain
discriminators. Those ride the genuine server once a matched interpreter is
wired.

Launch (matches the production URL shape ``/<dp>/rpcs/<port>/mcp``)::

    python stub_semantic_server.py <fixtures_dir> --http \
        --host 127.0.0.1 --port 8765 --dp pharma-mesh --rpc-port mcp-api
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


def _load_catalog(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "catalog.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_semantic(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "semantic.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing")
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_sqlite(fixture_dir: Path) -> sqlite3.Connection:
    """Load seed.sql into a fresh in-memory SQLite db.

    The seed is Snowflake-flavoured DDL/DML but the subset used here (DROP/CREATE
    TABLE with NUMBER/TEXT/BOOLEAN columns + INSERT ... VALUES) parses under
    SQLite once we down-map the types. We rewrite the type keywords and let
    SQLite's permissive typing handle the rest.
    """
    sql = (fixture_dir / "seed.sql").read_text(encoding="utf-8")
    # Down-map Snowflake types to SQLite affinities.
    sql = re.sub(r"\bNUMBER\b", "INTEGER", sql)
    sql = re.sub(r"\bTEXT\b", "TEXT", sql)
    sql = re.sub(r"\bBOOLEAN\b", "INTEGER", sql)
    sql = sql.replace("TRUE", "1").replace("FALSE", "0")
    con = sqlite3.connect(":memory:")
    con.executescript(sql)
    con.commit()
    return con


def _build_selection_sql(
    selection: dict[str, Any], semantic: dict[str, Any]
) -> str:
    """Compile a tiny subset of the selection DSL to SQL against the seed tables.

    Deliberately minimal — this stub only needs to answer the single-grain
    baseline (one COUNT_DISTINCT measure on the spine, no dimensions). Anything
    it can't compile raises, so the stub never fabricates a wrong number.
    """
    measures = selection.get("measures") or []
    dimensions = selection.get("dimensions") or []
    if len(measures) != 1 or dimensions:
        raise ValueError(
            "stub compiler only supports one measure, no dimensions "
            f"(got measures={measures}, dimensions={dimensions})"
        )
    metric_name = measures[0]
    # semantic.json shape: top-level `metrics` reference a `model`; each `model`
    # under `models` maps to a physical `table`.
    tables = {m["name"]: m["table"] for m in semantic.get("models", [])}
    for metric in semantic.get("metrics", []):
        if metric.get("name") != metric_name:
            continue
        agg = (metric.get("agg") or metric.get("aggregation") or "").upper()
        col = metric.get("column") or metric.get("expr")
        table = tables.get(metric.get("model"))
        if table is None:
            raise ValueError(f"metric {metric_name!r} references unknown model "
                             f"{metric.get('model')!r}")
        if agg == "COUNT_DISTINCT":
            return f"SELECT COUNT(DISTINCT {col}) AS {metric_name} FROM {table}"
        if agg == "SUM":
            return f"SELECT SUM({col}) AS {metric_name} FROM {table}"
        if agg == "COUNT":
            return f"SELECT COUNT({col}) AS {metric_name} FROM {table}"
        raise ValueError(f"stub compiler cannot handle aggregation {agg!r}")
    raise ValueError(f"unknown metric {metric_name!r}")


def build_server(
    fixture_dir: Path,
    *,
    http_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> FastMCP:
    catalog = _load_catalog(fixture_dir)
    semantic = _load_semantic(fixture_dir)

    if http_path is not None:
        mcp = FastMCP("nxd-semantic-stub", host=host, port=port,
                      streamable_http_path=http_path)
    else:
        mcp = FastMCP("nxd-semantic-stub")

    list_models_payload = catalog.get("list_models", [])
    describe_payload = catalog.get("describe_model", {})

    # Seed lazily on first query so the MCP handshake answers instantly.
    _state: dict[str, Any] = {"con": None}

    def _con() -> sqlite3.Connection:
        if _state["con"] is None:
            _state["con"] = _seed_sqlite(fixture_dir)
        return _state["con"]

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
            "Return full metadata for one semantic model: metrics (name + "
            "aggregation + compatible dimensions), dimensions (with pii flags), "
            "and joins. Use this to learn which concepts exist before querying."
        )
    )
    def describe_model(name: str) -> dict:
        info = describe_payload.get(name)
        if info is None:
            return {"error": f"unknown model {name!r}",
                    "known_models": list(describe_payload.keys())}
        return info

    @mcp.tool(
        description=(
            "Execute a governed semantic query. Accepts CONCEPT NAMES (not SQL): "
            "measures (required, list of metric names), dimensions (optional). "
            "Returns the result rows. Do NOT write raw SQL — pass concept names."
        )
    )
    def run_semantic_query(
        measures: list[str],
        dimensions: list[str] | None = None,
        filters: list[dict] | None = None,
    ) -> dict:
        selection = {
            "measures": measures,
            "dimensions": dimensions or [],
            "filters": filters or [],
        }
        try:
            sql = _build_selection_sql(selection, semantic)
        except ValueError as exc:
            return {"error": f"compile refused: {exc}", "selection": selection}
        try:
            cur = _con().execute(sql)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001 - report to the agent
            return {"error": f"execution failed: {exc}", "compiled_sql": sql}
        return {"compiled_sql": sql, "rows": rows, "row_count": len(rows)}

    return mcp


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="stub_semantic_server")
    parser.add_argument("fixtures_dir",
                        help="scenario fixtures dir (catalog.json + semantic.json + seed.sql)")
    parser.add_argument("--http", action="store_true",
                        help="serve Streamable-HTTP (Inspect path) instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dp", default="pharma-mesh")
    parser.add_argument("--rpc-port", default="mcp-api")
    args = parser.parse_args(argv[1:])

    fixture_dir = Path(args.fixtures_dir).resolve()
    if not fixture_dir.is_dir():
        print(f"fixtures dir not found: {fixture_dir}", file=sys.stderr)
        return 2

    if args.http:
        http_path = f"/{args.dp}/rpcs/{args.rpc_port}/mcp"
        server = build_server(fixture_dir, http_path=http_path,
                              host=args.host, port=args.port)
        print(f"stub MCP serving at http://{args.host}:{args.port}{http_path}",
              file=sys.stderr)
        server.run("streamable-http")
    else:
        server = build_server(fixture_dir)
        server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

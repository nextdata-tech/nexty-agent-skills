#!/usr/bin/env python3
"""Client-side cross-DP compiler — the deterministic alternative to Bill's LLM-merge.

The IP path, run from the client: assemble ONE semantic registry spanning several
deployed DPs from their declared semantic layer, compile a concept selection to a
SINGLE fan-out-safe cross-DP SQL with the SHIPPED ``nxd.experimental.semantic``
compiler (the same one the DPs serve per-DP), then execute it governed against the
warehouse with a credential leased from a DP port.

This mirrors the single-DP query pattern (pull the semantic layer, compile, run)
generalised across DP boundaries — and is a faithful client stand-in for the
eventual SERVER-SIDE cross-DP endpoint (same registry contract, same compiler).

Flow:
    1. HARVEST   each DP's full registry via its ``semantic_model`` MCP tool
                 (JSON: models + physical columns + join on-keys + data_product).
                 Falls back to ``--registry-json`` for offline / pre-deploy use.
    2. MERGE     every DP's slice into ONE SemanticRegistry. Model names are
                 schema-qualified (``<SCHEMA>.<table>``) so the single-``fqn``
                 compiler emits ``<DB>.<SCHEMA>.<table>`` per model — i.e. real
                 cross-schema SQL in one database. data_product labels are kept so
                 cross-DP hops are diagnosable.
    3. COMPILE   ``compile_selection(selection, registry, dialect, fqn, use_view=False)``
                 → ONE deterministic, fan-out-safe Snowflake SQL.
    4. EXECUTE   (optional, ``--execute``) lease a Snowflake credential from a DP
                 port and run the compiled SQL — rows never leave the warehouse
                 except the final governed result.

GOVERNANCE NOTE (PoC scope, matching the design doc): all mesh DPs live in one
Snowflake database under schemas the leased credential can read, so a single
compiled SELECT is a same-engine cross-schema query. The DP boundary is a
join-PLANNING label here; the per-DP credential/lease isolation story is the
server-side endpoint's job.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# The SHIPPED compiler — same library the DPs serve with.
from nxd.experimental.semantic import (  # type: ignore[import-not-found]
    Agg,
    Cardinality,
    CompileError,
    SemanticRegistry,
    SnowflakeDialect,
    compile_selection,
)

_HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# 1. HARVEST — pull each DP's registry payload via the semantic_model MCP tool
# ---------------------------------------------------------------------------


def harvest_registry(endpoint: str, token_file: str, *, timeout: int = 40) -> dict:
    """Call a DP's ``semantic_model`` MCP tool → its registry payload dict.

    Reuses the skill's ``mcp_call.py`` (Streamable-HTTP + session token + CA).
    """
    out = "/tmp/nxd-semantic-model.json"
    cmd = [
        sys.executable,
        str(_HERE / "mcp_call.py"),
        "--endpoint", endpoint,
        "--tool", "semantic_model",
        "--args", "{}",
        "--token-file", token_file,
        "--out", out,
    ]
    subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
    raw = json.loads(Path(out).read_text(encoding="utf-8"))
    # the tool returns {"payload": "<json string>"}; unwrap.
    payload = raw.get("payload")
    if isinstance(payload, str):
        return json.loads(payload)
    return raw  # already a dict (offline / direct)


# ---------------------------------------------------------------------------
# 2. MERGE — combine per-DP payloads into ONE schema-qualified registry
# ---------------------------------------------------------------------------

_AGG = {a.value: a for a in Agg}
_CARD = {c.value: c for c in Cardinality}


def merge_registry(
    payloads: list[dict], schema_of: dict[str, str], database: str
) -> SemanticRegistry:
    """Merge per-DP registry payloads into one SemanticRegistry.

    Each model keeps its BARE name (used as the CTE alias — must be dot-free) but
    is registered with an explicit ``table=<DB>.<SCHEMA>.<name>`` so the compiler
    emits the model's real cross-schema location while CTE ids stay valid. The
    physical schema comes from the payload's own ``schema``/``database`` (read
    from the DP's storage context) when present, else from ``schema_of`` +
    ``database`` (offline override). data_product labels are preserved.
    """
    reg = SemanticRegistry()
    seen_dims: set[str] = set()
    seen_metrics: set[str] = set()
    seen_joins: set[tuple] = set()

    # PASS 1 — resolve each model name to its BEST definition across ALL payloads.
    # A model appears in several payloads: as the OWN model in its owning DP (with a
    # physical ``table`` from that DP's read context) and as a bare STUB join-target
    # in every consuming DP (no table, only a ``data_product`` label). First-wins
    # would keep whichever was harvested first — often a stub — and the compiler
    # would then fall back to ``<fqn><name>`` with the WRONG schema for the spine /
    # crosswalk. So prefer the definition that carries a real ``table`` (the owner),
    # regardless of harvest order.
    best: dict[str, dict] = {}
    for p in payloads:
        for m in p.get("models", []):
            name = m["name"]
            prev = best.get(name)
            if prev is None:
                best[name] = m
                continue
            # upgrade a tableless stub to the owner definition that has a table
            if not prev.get("table") and m.get("table"):
                best[name] = m

    for name, m in best.items():
        db = m.get("database") or database
        schema = m.get("schema") or schema_of.get(name, "")
        table = m.get("table") or (
            f"{db}.{schema}.{name}" if (db and schema) else (f"{schema}.{name}" if schema else "")
        )
        reg = reg.model(
            name,
            grain=m["grain"],
            description=m.get("description", ""),
            data_product=m.get("data_product", ""),
            table=table,
        )

    for p in payloads:
        for d in p.get("dimensions", []):
            if d["name"] in seen_dims:
                continue
            seen_dims.add(d["name"])
            reg = reg.dimension(
                d["name"],
                model=d["model"],
                column=d["column"],
                type=d.get("type", "string"),
                description=d.get("description", ""),
                pii=d.get("pii", False),
                label_column=d.get("label_column"),
            )
        for mt in p.get("metrics", []):
            if mt["name"] in seen_metrics:
                continue
            seen_metrics.add(mt["name"])
            reg = reg.metric(
                mt["name"],
                model=mt["model"],
                agg=_AGG[mt["agg"]],
                column=mt.get("column", "*"),
                description=mt.get("description", ""),
                boolean=mt.get("boolean", False),
            )
        for j in p.get("joins", []):
            key = (j["left"], j["right"], tuple(tuple(o) for o in j["on"]))
            if key in seen_joins:
                continue
            seen_joins.add(key)
            reg = reg.join(
                left=j["left"],
                right=j["right"],
                on=tuple((a, b) for a, b in j["on"]),
                cardinality=_CARD.get(j.get("cardinality", "many_to_one"), Cardinality.MANY_TO_ONE),
            )
    return reg.build()


# ---------------------------------------------------------------------------
# 3. COMPILE
# ---------------------------------------------------------------------------


def compile_cross_dp(selection: dict, registry, database: str) -> str:
    """Compile a {measures, dimensions, filters} selection to ONE cross-DP SQL.

    ``use_view=False`` forces the inline fan-out-safe base-table assembler (the
    cross-DP path); ``fqn`` is the database prefix (schema is baked into the model
    names). Raises CompileError if the selection is not join-reachable.
    """
    dialect = SnowflakeDialect(view_name="")
    return compile_selection(
        selection,
        registry=registry,
        dialect=dialect,
        fqn=f"{database}." if database else "",
        use_view=False,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(prog="cross_dp_compile")
    p.add_argument("--measures", default="", help="comma-separated metric names")
    p.add_argument("--dimensions", default="", help="comma-separated dimension names")
    p.add_argument("--database", default="", help="Snowflake database (the single fqn prefix)")
    p.add_argument(
        "--dp",
        action="append",
        default=[],
        metavar="ENDPOINT=SCHEMA",
        help="a DP's MCP endpoint and its Snowflake schema, e.g. "
        "http://.../pharma-labs-demo-demo/rpcs/mcp-api/mcp/=PHARMA_LABS_DEMO. Repeat per DP.",
    )
    p.add_argument("--token-file", default="", help="session token file (find_mesh.py)")
    p.add_argument(
        "--registry-json",
        action="append",
        default=[],
        metavar="PATH=SCHEMA",
        help="offline: a per-DP registry payload JSON file + its schema (instead of --dp).",
    )
    p.add_argument("--out", default="/tmp/nxd-cross-dp.sql")
    args = p.parse_args()

    selection = {
        "measures": [m for m in args.measures.split(",") if m],
        "dimensions": [d for d in args.dimensions.split(",") if d],
        "filters": [],
    }
    if not selection["measures"] and not selection["dimensions"]:
        print("error: pass at least one --measures or --dimensions", file=sys.stderr)
        return 2

    payloads: list[dict] = []
    schema_of: dict[str, str] = {}

    # offline path: --registry-json PATH=SCHEMA
    for spec in args.registry_json:
        path, _, schema = spec.partition("=")
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        payloads.append(payload)
        for m in payload.get("models", []):
            schema_of.setdefault(m["name"], schema)

    # live path: --dp ENDPOINT=SCHEMA (needs --token-file)
    for spec in args.dp:
        endpoint, _, schema = spec.partition("=")
        payload = harvest_registry(endpoint, args.token_file)
        payloads.append(payload)
        for m in payload.get("models", []):
            schema_of.setdefault(m["name"], schema)

    if not payloads:
        print("error: pass --dp or --registry-json for at least one DP", file=sys.stderr)
        return 2

    registry = merge_registry(payloads, schema_of, args.database)

    try:
        # fqn="" — every model carries its fully-qualified table, so no prefix.
        sql = compile_cross_dp(selection, registry, "")
    except CompileError as exc:
        print(json.dumps({"error": f"CompileError: {exc}", "selection": selection}))
        return 1

    Path(args.out).write_text(sql, encoding="utf-8")
    print(json.dumps({"selection": selection, "out": args.out, "sql": sql}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Server-side cross-DP query tool — the deterministic compiler, run in-pod.

This is the SERVER-SIDE home of the cross-DP compiler that the client-side
``scripts/cross_dp_compile.py`` stands in for. A single MCP tool,
``run_cross_dp_query``, takes the caller's already-harvested per-DP semantic
registries + a concept selection, merges them into ONE registry, compiles ONE
fan-out-safe cross-schema SQL with the SHIPPED ``nxd.experimental.semantic``
compiler, and executes it in-pod under the DP's injected Snowflake handle.

WHY SERVER-SIDE (the two findings the live eval proved):
  1. EXECUTION LOCUS — a client connecting to the warehouse directly is blocked
     by the account network policy (IP allowlist). The DP pod's egress IS
     allowlisted, so the same compiled SQL runs here when it can't from a laptop.
  2. AUTHORIZATION SCOPE — a per-DP leased credential is scoped to ONE schema; a
     single cross-schema SELECT needs USAGE on EVERY spanned schema. This DP's
     Snowflake service must resolve to a role with cross-schema read across the
     mesh's member schemas (the deploy precondition — see README). The client's
     per-DP lease cannot authorize the join by construction.

WHY THE CALLER PASSES THE REGISTRIES (dynamic, no redeploy):
  The agent already calls each DP's ``semantic_model`` tool to plan a query — it
  holds the aggregate serialized payloads. Passing them in as a tool argument
  means this DP needs NO mesh discovery, NO sibling auth, NO in-pod harvest, and
  — critically — NO redeploy when the mesh changes. A new DP joins the mesh, the
  agent harvests it, and includes its payload in the next call. The registry is
  data, never baked.

GENERIC: nothing here is mesh-specific. The merge/compile/execute logic works for
any set of ``semantic_model`` payloads whose models live in schemas the injected
role can read. Deploy this template onto any mesh by pointing the Snowflake
service at a suitably-scoped role.

SELF-CONTAINED: merge + compile + execute are all inline and import only from the
installed ``nxd.experimental.semantic`` library — there is no flat ``registry.py``
sibling to bundle. ``code(run_cross_dp_query)`` carries this one module.
"""

from __future__ import annotations

import json as _json
from typing import Any

from nxd.drivers.rpc import Request
from nxd.drivers.rpc import Response
from nxd.drivers.rpc import function
from nxd.drivers.rpc import mcp

# Module-level import (NOT lazy/in-body): the rpc `@function` decorator injects a
# context arg by TYPE. A param annotated with a FromContext subclass (`Snowflake`)
# is bound to the resolved handle via `Snowflake.from_context(...)`; a param typed
# `Any` would get a bare `Context` with no `.connector_params()`. `code()`
# extraction copies module-level imports verbatim but does NOT hoist in-body
# imports, so this MUST be top-level for the annotation to resolve in the
# extracted rpc-server script. (regression python.md #64)
from nxd.data_product.context import Snowflake

# The SHIPPED compiler — the same library every per-DP `run_semantic_query`
# serves with. Pure-python; safe to import at module load. (>=0.41.100 carries
# the cross-DP `Model.table` decoupling + `registry_payload` table field.)
from nxd.experimental.semantic import Agg
from nxd.experimental.semantic import Cardinality
from nxd.experimental.semantic import CompileError
from nxd.experimental.semantic import SemanticRegistry
from nxd.experimental.semantic import SnowflakeDialect
from nxd.experimental.semantic import compile_selection

_AGG = {a.value: a for a in Agg}
_CARD = {c.value: c for c in Cardinality}


def _merge_registry(payloads: list[dict]) -> SemanticRegistry:
    """Merge per-DP ``semantic_model`` payloads into ONE SemanticRegistry.

    Two-pass, owner-wins (mirrors ``scripts/cross_dp_compile.py``):

    PASS 1 resolves each model name to its BEST definition across ALL payloads.
    A cross-DP model appears in several payloads — as the OWN model (carrying a
    physical ``table`` from its owner's read context) in its owning DP, and as a
    bare STUB join-target (no ``table``, only a ``data_product`` label) in every
    consuming DP. First-wins would keep whichever was harvested first — often a
    stub — and the compiler would then fall back to ``<fqn><name>`` with the
    WRONG schema for the spine / crosswalk. So prefer the definition that carries
    a real ``table`` (the owner), regardless of payload order.

    PASS 2 builds dimensions / metrics / joins (first definition wins; they do
    not vary by owner).
    """
    best: dict[str, dict] = {}
    for p in payloads:
        for m in p.get("models", []):
            name = m["name"]
            prev = best.get(name)
            if prev is None:
                best[name] = m
            elif not prev.get("table") and m.get("table"):
                best[name] = m

    reg = SemanticRegistry()
    for name, m in best.items():
        db = m.get("database") or ""
        schema = m.get("schema") or ""
        table = m.get("table") or (
            f"{db}.{schema}.{name}"
            if (db and schema)
            else (f"{schema}.{name}" if schema else "")
        )
        reg = reg.model(
            name,
            grain=m["grain"],
            description=m.get("description", ""),
            data_product=m.get("data_product", ""),
            table=table,
        )

    seen_dims: set[str] = set()
    seen_metrics: set[str] = set()
    seen_joins: set[tuple] = set()
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
                cardinality=_CARD.get(
                    j.get("cardinality", "many_to_one"), Cardinality.MANY_TO_ONE
                ),
            )
    return reg.build()


@function(name="run_cross_dp_query")
@mcp.tool(
    name="run_cross_dp_query",
    description=(
        "Answer a question that spans MULTIPLE data products with ONE governed, "
        "fan-out-safe cross-schema SQL — the deterministic cross-DP compiler, run "
        "server-side. You name CONCEPTS across DPs; this tool merges their semantic "
        "registries, compiles ONE SQL, and executes it in-pod. You never write SQL.\n\n"
        "ARGS:\n"
        "- registry_payloads (REQUIRED): list of the member DPs' `semantic_model` "
        "payloads. Call `semantic_model` on each DP that owns a model/metric/dimension "
        "your question touches, and pass every payload here. Each entry may be the "
        "payload dict or its JSON string. The set is dynamic — include whichever DPs "
        "the question spans; no redeploy is needed when the mesh changes.\n"
        "- measures (REQUIRED): list of metric names (from any included DP).\n"
        "- dimensions (optional): list of dimension names to group by. Omit (or []) "
        "for a grand total.\n"
        '- filters (optional): list of {"dimension": <name>, "op": <symbol>, '
        "\"value\": <val>}. 'op' MUST be one of '=', '!=', '>', '>=', '<', '<=', "
        "'IN', 'LIKE', 'ILIKE'.\n\n"
        "The compiler pre-aggregates each measure at its model's grain before any "
        "join, so a measure spanning a 1:N cross-DP relationship is NOT double-counted "
        "(the chasm trap). An unreachable / mixed-grain selection returns an error "
        "rather than a wrong number."
    ),
)
def run_cross_dp_query(snowflake: Snowflake, request: Request) -> Response:
    from snowflake import connector  # type: ignore[import-not-found]

    cap = 200

    def _error(message: str, sql: str = "") -> Response:
        return Response(
            {
                "compiled_sql": sql,
                "row_count": 0,
                "truncated": False,
                "columns": [],
                "rows": [],
                "error": message,
            }
        )

    # The caller hands us the already-harvested per-DP registries. Accept either
    # parsed dicts or JSON strings (the `semantic_model` tool returns the payload
    # as a JSON string under "payload"; agents may forward that verbatim).
    raw_payloads = request.get("registry_payloads") or []
    payloads: list[dict] = []
    for item in raw_payloads:
        if isinstance(item, str):
            try:
                item = _json.loads(item)
            except _json.JSONDecodeError as e:
                return _error(f"registry_payloads entry is not valid JSON: {e}")
        if isinstance(item, dict) and "payload" in item and "models" not in item:
            # an un-unwrapped `semantic_model` response: {"payload": "<json>"}
            inner = item["payload"]
            item = _json.loads(inner) if isinstance(inner, str) else inner
        if not isinstance(item, dict) or "models" not in item:
            return _error(
                "each registry_payloads entry must be a semantic_model payload "
                "(a dict with a 'models' key), or its JSON string."
            )
        payloads.append(item)

    if not payloads:
        return _error(
            "No registry_payloads provided. Call `semantic_model` on each DP your "
            "question spans and pass the payloads in 'registry_payloads'."
        )

    selection: dict[str, Any] = {
        "measures": request.get("measures") or [],
        "dimensions": request.get("dimensions") or [],
        "filters": request.get("filters") or [],
    }
    if not selection["measures"]:
        return _error(
            "No measures selected. Provide at least one metric name in 'measures'."
        )

    if snowflake is None:
        return _error("No Snowflake connection is available.")

    try:
        registry = _merge_registry(payloads)
    except (KeyError, ValueError) as e:
        return _error(f"Failed to merge registries: {e}")

    # Every model carries its fully-qualified `table` (DB.SCHEMA.TABLE) from the
    # owner's payload, so the compiler needs no fqn prefix. `use_view=False` forces
    # the inline fan-out-safe base-table assembler (the cross-DP path; a single
    # pre-joined view cannot represent a multi-DP selection).
    dialect = SnowflakeDialect(view_name="")
    try:
        sql = compile_selection(
            selection, registry=registry, dialect=dialect, fqn="", use_view=False
        )
    except CompileError as e:
        return _error(f"Invalid cross-DP selection: {e}")
    except Exception as e:  # noqa: BLE001 — surface any compile failure as a tool error
        return _error(f"Compile failed: {e}")

    # Execute in-pod under the injected handle. The handle's role must have USAGE
    # across every schema the compiled SQL spans (the deploy precondition); a
    # per-DP-scoped role returns Snowflake 002003 (schema not authorized).
    wrapped = ""
    try:
        conn: Any = connector.connect(
            user=snowflake.user,
            account=snowflake.account,
            warehouse=snowflake.warehouse,
            role=snowflake.role,
            database=snowflake.database,
            schema=snowflake.schema,
            ocsp_fail_open=True,
            session_parameters={"STATEMENT_TIMEOUT_IN_SECONDS": 60},
            **snowflake.connector_params(),
        )
        try:
            with conn.cursor() as cur:
                wrapped = f"SELECT * FROM (\n{sql}\n) AS _capped LIMIT {cap + 1}"
                cur.execute(wrapped)
                rows: list[Any] = list(cur.fetchall())
                columns: list[str] = [str(c[0]) for c in cur.description]
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 — surface execution failure as a tool error
        return _error(f"Query failed: {e}", sql=wrapped)

    truncated = len(rows) > cap
    if truncated:
        rows = rows[:cap]

    return Response(
        {
            "compiled_sql": wrapped,
            "row_count": len(rows),
            "truncated": truncated,
            "columns": columns,
            "rows": [_json.dumps(list(r), default=str) for r in rows],
            "error": "",
        }
    )

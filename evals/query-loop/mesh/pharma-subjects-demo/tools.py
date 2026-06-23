"""Module-level MCP tool wrappers for the semantic-smoke data product.

The underlying compiler and query logic live in ``nxd.experimental.semantic``
(the installed library). This module exposes the same three tools as top-level
functions so that ``code(list_models)`` / ``code(describe_model)`` /
``code(run_semantic_query)`` can be resolved by the NXD spec builder.

At runtime every function re-derives the registry, dialect, and compiled SQL
from the library — no logic is duplicated here.
"""

from __future__ import annotations

import json as _json
from typing import Any

from nxd.drivers.rpc import Request
from nxd.drivers.rpc import Response
from nxd.drivers.rpc import function
from nxd.drivers.rpc import mcp

# Module-level import (NOT lazy/in-body): the rpc `@function` decorator injects a
# context arg by TYPE. It reads the resolved signature (get_type_hints) at
# registration time and, for a param whose annotation `is_from_context(...)` is
# True (i.e. a FromContext subclass like Snowflake), calls
# `Snowflake.from_context(context_data)` and binds the resulting Snowflake handle.
# A param typed `Any` is NOT a FromContext subclass, so the framework falls back
# to injecting a raw `Context` (no `.connector_params()` / `.user` / `.database`).
# `code()` extraction copies module-level imports verbatim but does NOT hoist
# in-body imports, so this MUST be a top-level import for the `Snowflake`
# annotation to resolve in the extracted rpc-server script.
from nxd.data_product.context import Snowflake

# Flat sibling import — registry.py is bundled as a sibling of the extracted
# tool scripts, and the script's own directory is the only thing guaranteed on
# sys.path in the RPC subprocess. A package-qualified `transform.registry`
# import requires the DP root on sys.path and fails at runtime.
from registry import REGISTRY

# Imports from the installed library (nxd.data_product wheel ships
# nxd.experimental.semantic). Pure-python; safe to import at module load.
from nxd.experimental.semantic.compiler import CompileError
from nxd.experimental.semantic.compiler import compile_selection
from nxd.experimental.semantic.compiler import semantic_view_query
from nxd.experimental.semantic.dialect import SnowflakeDialect
from nxd.experimental.semantic.mcp_tools import registry_payload

# IMPORTANT — rpc-tool extraction footgun (audit P1-#7): `code(fn)` carries a
# tool function's IMPORTS and any top-level def/class it calls, but it DROPS
# module-level `=` assignments. So a `@mcp.tool(description=_CONST)` referencing a
# module constant, or a function body referencing a module-level singleton like a
# pre-built `_DIALECT`, raises NameError at rpc-server load → the tool fails to
# register → tools/list is []. FIX: inline description literals into the decorator
# and build per-call state (the dialect) INSIDE each function body.


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


@function(name="semantic_model")
@mcp.tool(name="semantic_model", description="Return this data product's FULL semantic registry as a JSON payload — every model (grain + owning data_product + its physical DB.SCHEMA.TABLE), dimension (physical column, type, pii), metric (aggregation, physical column, boolean), and join (on-key pairs + cardinality). A client merges each DP's payload into ONE registry to plan/compile a cross-DP join against the live mesh.")
def semantic_model(snowflake: Snowflake, request: Request) -> Response:
    payload = registry_payload(REGISTRY)
    db: Any = snowflake.database
    schema: Any = snowflake.schema
    own = {m.name for m in REGISTRY.models if not getattr(m, "data_product", "")}
    for m in payload["models"]:
        if m["name"] in own and db and schema:
            m["database"] = db
            m["schema"] = schema
            m["table"] = f"{db}.{schema}.{m['name']}"
    return Response({"payload": _json.dumps(payload)})


@function(name="list_models")
@mcp.tool(
    name="list_models",
    description=(
        "List every semantic model (grain) this data product exposes — each with "
        "its grain definition, metric count, dimension count, and join topology. "
        "A MODEL is the fundamental unit: every metric and every dimension lives "
        "under exactly one model. "
        "Call this first to orient yourself, then call describe_model on the model "
        "whose grain matches your question."
    ),
)
def list_models(request: Request) -> Response:
    out: list[dict[str, object]] = []
    for m in REGISTRY.models:
        joins: list[dict[str, object]] = [
            {"to": j.right, "cardinality": j.cardinality.value}
            for (j, _reached) in REGISTRY.joins_of(m.name)
        ]
        out.append(
            {
                "name": m.name,
                "grain": m.grain,
                "description": m.description,
                "metric_count": len(REGISTRY.metrics_of(m.name)),
                "dimension_count": len(REGISTRY.dimensions_of(m.name)),
                "joins": joins,
            }
        )
    return Response({"models": out})


# ---------------------------------------------------------------------------
# describe_model
# ---------------------------------------------------------------------------

@function(name="describe_model")
@mcp.tool(
    name="describe_model",
    description=(
        "Describe a single semantic model in full: its grain, every metric it owns "
        "(with aggregation, description, and the exact set of dimensions each metric "
        "can be sliced by), every own dimension (type, PII flag, description), and "
        "every documented join with the set of dimensions it makes reachable. "
        "CHASM-TRAP RULE: metrics from two different models must NEVER be combined "
        "in one run_semantic_query call. "
        "Call describe_model before run_semantic_query to pick a valid "
        "metric + dimension combination from the same model."
    ),
)
def describe_model(request: Request) -> Response:
    name = request.get("name") or ""
    model_obj = REGISTRY.model_of(name)
    if model_obj is None:
        known = ", ".join(m.name for m in REGISTRY.models)
        return Response(
            {
                "name": name,
                "grain": "",
                "description": "",
                "metrics": [],
                "dimensions": [],
                "joins": [],
                "error": f"unknown model {name!r}. Known models: {known}.",
            }
        )
    metrics_out: list[dict[str, object]] = []
    for met in REGISTRY.metrics_of(name):
        metrics_out.append(
            {
                "name": met.name,
                "aggregation": met.agg.value,
                "description": REGISTRY.metric_description(met),
                "compatible_dimensions": [
                    d.name for d in REGISTRY.compatible_dimensions(met)
                ],
            }
        )
    dimensions_out: list[dict[str, object]] = []
    for d in REGISTRY.dimensions_of(name):
        dimensions_out.append(
            {
                "name": d.name,
                "type": d.type,
                "pii": bool(d.pii),
                "description": REGISTRY.column_description(
                    d.model, d.column, d.description
                ),
            }
        )
    joins_out: list[dict[str, object]] = []
    for j, reached in REGISTRY.joins_of(name):
        joins_out.append(
            {
                "to": j.right,
                "cardinality": j.cardinality.value,
                "reaches_dimensions": list(reached),
            }
        )
    return Response(
        {
            "name": model_obj.name,
            "grain": model_obj.grain,
            "description": model_obj.description,
            "metrics": metrics_out,
            "dimensions": dimensions_out,
            "joins": joins_out,
            "error": "",
        }
    )


# ---------------------------------------------------------------------------
# run_semantic_query
# ---------------------------------------------------------------------------

@function(name="run_semantic_query")
@mcp.tool(
    name="run_semantic_query",
    description=(
        "THE DEFAULT, SAFE way to answer a question about this data product. "
        "Name CONCEPTS and the data product writes correct, governed SQL — "
        "you never write SQL on this path.\n\n"
        "ARGS:\n"
        "- measures (REQUIRED): list of metric names from describe_model.\n"
        "- dimensions (optional): list of dimension names from describe_model "
        "to group by. OMIT IT (or pass []) for a grand total.\n"
        '- filters (optional): list of {"dimension": <name>, "op": <symbol>, '
        "\"value\": <val>}. The 'op' field MUST be one of: '=', '!=', '>', '>=', "
        "'<', '<=', 'IN', 'LIKE', 'ILIKE'.\n\n"
        "Do not mix metrics from different models in one call."
    ),
)
def run_semantic_query(snowflake: Snowflake, request: Request) -> Response:
    from snowflake import connector  # type: ignore[import-not-found]

    # `snowflake` is injected by the rpc `@function` decorator as a real
    # `Snowflake` handle: the param name matches the DP's `snowflake` storage
    # output port, and the `Snowflake` annotation (a FromContext subclass) makes
    # the framework call `Snowflake.from_context(context_data)` and bind the
    # result. No in-body Context->Snowflake conversion is needed.

    # Built per-call inside the body: a module-level `_DIALECT` singleton would be
    # dropped by code() extraction (audit P1-#7). Resolves the same view name the
    # provision step creates (<FIRST_MODEL_UPPER>_SEMANTIC) so the native-view
    # probe matches (regression python.md #62).
    _DIALECT = SnowflakeDialect(view_name=SnowflakeDialect.default_view_name(REGISTRY))

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

    selection: dict[str, Any] = {
        "measures": request.get("measures") or [],
        "dimensions": request.get("dimensions") or [],
        "filters": request.get("filters") or [],
    }
    if not selection["measures"]:
        return _error(
            "No measures selected. Provide at least one metric name "
            "from describe_model in 'measures'."
        )

    if snowflake is None:
        return _error("No Snowflake connection is available.")

    sf_database: Any = snowflake.database
    sf_schema: Any = snowflake.schema
    fqn = f"{sf_database}.{sf_schema}." if sf_database else f"{sf_schema}."

    wrapped = ""
    try:
        conn: Any = connector.connect(
            user=snowflake.user,
            account=snowflake.account,
            warehouse=snowflake.warehouse,
            role=snowflake.role,
            database=sf_database,
            schema=sf_schema,
            ocsp_fail_open=True,
            session_parameters={"STATEMENT_TIMEOUT_IN_SECONDS": 60},
            **snowflake.connector_params(),
        )
        try:
            with conn.cursor() as cur:
                try:
                    native = _DIALECT.supports_native_semantic_view(cur, fqn=fqn)
                except Exception:
                    native = False
                try:
                    if native:
                        sql = semantic_view_query(
                            selection,
                            registry=REGISTRY,
                            dialect=_DIALECT,
                            fqn=fqn,
                        )
                    else:
                        try:
                            # Single-DP selections compile against the pre-joined
                            # <MODEL>_SEMANTIC view. A cross-DP / multi-hop
                            # selection cannot be represented by that single-table
                            # view; the compiler raises CompileError telling us to
                            # compile against base tables. Auto-fall back to
                            # use_view=False so the multi-hop join resolves at
                            # query time against the live mesh tables.
                            sql = compile_selection(
                                selection,
                                registry=REGISTRY,
                                dialect=_DIALECT,
                                fqn=fqn,
                                use_view=True,
                            )
                        except CompileError as ve:
                            if "use_view=False" not in str(ve):
                                raise
                            sql = compile_selection(
                                selection,
                                registry=REGISTRY,
                                dialect=_DIALECT,
                                fqn=fqn,
                                use_view=False,
                            )
                except CompileError as e:
                    return _error(f"Invalid selection: {e}")
                except Exception as e:
                    return _error(f"Compile failed: {e}")

                wrapped = f"SELECT * FROM (\n{sql}\n) AS _capped LIMIT {cap + 1}"
                cur.execute(wrapped)
                rows: list[Any] = list(cur.fetchall())
                columns: list[str] = [str(c[0]) for c in cur.description]
        finally:
            conn.close()
    except Exception as e:
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

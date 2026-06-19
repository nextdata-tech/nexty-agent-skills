"""MCP tool factory for the NXD semantic-layer stopgap (NEX-620).

Exposes three governed MCP tools over a
:py:class:`~nxd.experimental.semantic.registry.CompiledRegistry`:

- ``list_models``        — enumerate available semantic models (grains) with
                           metric/dimension counts and join topology.
- ``describe_model``     — detail one model: all its metrics (with compatible
                           dimensions), own dimensions, and join-reachable dims.
- ``run_semantic_query`` — THE default path: name concepts → deterministic SQL
                           → governed execution → rows (200-row cap).

This module imports ``nxd.drivers.rpc`` (``Request``, ``Response``, ``function``,
``mcp``) and ``nxd.spec`` (``semantic_model``, data_types). It is gated behind
the existing ``rpc`` extra — importing :py:mod:`nxd.experimental.semantic` without
that extra still works (the ``__init__`` guards this import in a try/except).

Tool descriptions are generic (no domain-specifics). Concepts and table names are
derived from the registry at build time.

:py:func:`build_semantic_tools` returns a ``list[SemanticTool]`` — NOT a list of
bare callables. Each :py:class:`SemanticTool` carries the callable (``.fn``), its
``request_model`` and ``response_model`` :py:class:`~nxd.spec.SemanticModelSpec`
instances, and the tool ``description`` string. A ``spec.py`` wires them like::

    from nxd.spec import data_product_rpc_output, rpc_function, rpc_server, code
    from semantic import build_semantic_tools

    REGISTRY = ...  # CompiledRegistry

    out = data_product_rpc_output()
    for t in build_semantic_tools(REGISTRY):
        out = out.function(
            rpc_function(code(t.fn), t.request_model, t.response_model)
            .description(t.description)
        )
    out = out.port("mcp-api", rpc_server("<service-ref>").enable_endpoints().mcp_path("/mcp"))

Do NOT accumulate the result as a bare ``tools = build_semantic_tools(REGISTRY)``
list passed to nothing — that exposes zero MCP tools. The list is only useful
when iterated and wired via ``rpc_function`` as shown above.

See: (ADR under review in nxd PR #6893: docs/architecture/adrs/026-semantic-layer-first-class.md)
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any

from nxd.core.yaml_schemas import DataType
from nxd.core.yaml_schemas import Field
from nxd.drivers.rpc import Request
from nxd.drivers.rpc import Response
from nxd.drivers.rpc import function
from nxd.drivers.rpc import mcp
from nxd.spec import semantic_model
from nxd.spec._model import AttributeSpec
from nxd.spec.data_types import boolean
from nxd.spec.data_types import int64
from nxd.spec.data_types import list as _list
from nxd.spec.data_types import string
from nxd.spec.data_types import struct

if TYPE_CHECKING:
    from .dialect import Dialect
    from .registry import CompiledRegistry


# ---------------------------------------------------------------------------
# SemanticTool descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticTool:
    """Descriptor for one semantic MCP tool produced by :py:func:`build_semantic_tools`.

    Attributes
    ----------
    name:
        The MCP tool name (e.g. ``"list_models"``).
    fn:
        The ``@function`` / ``@mcp.tool``-decorated callable.  Pass to
        ``code(t.fn)`` when wiring via ``rpc_function``.
    request_model:
        The :py:class:`~nxd.spec.SemanticModelSpec` describing the tool's
        request schema.  Pass as the second positional argument to
        ``rpc_function(code(t.fn), t.request_model, t.response_model)``.
    response_model:
        The :py:class:`~nxd.spec.SemanticModelSpec` describing the tool's
        response schema.  Pass as the third positional argument.
    description:
        Plain-language MCP tool description (the same string passed to
        ``@mcp.tool(description=...)``).  Pass to ``.description(t.description)``
        on the ``RpcFunctionSpec``.
    """

    name: str
    fn: object
    request_model: object
    response_model: object
    description: str


# ---------------------------------------------------------------------------
# Shared schema helpers (ported verbatim from PoC mcp_tools.py)
# ---------------------------------------------------------------------------


def _field(name: str, data_type: DataType, description: str | None = None) -> Field:
    return Field(
        data_type=data_type,
        name=name,
        description=description,
        metadata=None,
        constraints=None,
        relates_to=[],
        semantic_tags=None,
    )


def _row_list(item_name: str, fields: list[Field], description: str) -> tuple[DataType, str]:
    return (_list(_field(item_name, struct(fields))), description)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_semantic_tools(
    registry: CompiledRegistry,
    *,
    view_name: str | None = None,
    dialect: Dialect | None = None,
) -> list[SemanticTool]:
    """Build and return three :py:class:`SemanticTool` descriptors for *registry*.

    Each descriptor carries the decorated callable (``.fn``), its
    ``request_model`` and ``response_model`` :py:class:`~nxd.spec.SemanticModelSpec`
    instances, and the ``description`` string.

    Parameters
    ----------
    registry:
        Compiled semantic registry (from :py:meth:`SemanticRegistry.build`).
    view_name:
        Optional override for the semantic view / plain view name. When ``None``,
        the dialect derives a name from the registry (default: first model name
        + ``_SEMANTIC``).
    dialect:
        SQL dialect. Defaults to :py:class:`~nxd.experimental.semantic.dialect.SnowflakeDialect`.

    Returns
    -------
    list[SemanticTool]
        Three :py:class:`SemanticTool` descriptors (in order):
        ``[list_models, describe_model, run_semantic_query]``.

        Wire them in a ``spec.py`` via::

            out = data_product_rpc_output()
            for t in build_semantic_tools(REGISTRY):
                out = out.function(
                    rpc_function(code(t.fn), t.request_model, t.response_model)
                    .description(t.description)
                )

        Do NOT use the return value as a bare ``tools`` list passed to nothing —
        that exposes zero MCP tools.
    """
    from .compiler import CompileError
    from .compiler import compile_selection
    from .compiler import semantic_view_query

    if dialect is None:
        from .dialect import SnowflakeDialect

        # Pre-resolve the view name from the registry so the dialect's
        # _view_name is always populated. Otherwise supports_native_semantic_view
        # would fall back to the literal "SEMANTIC_VIEW" while the rest of the
        # dialect provisions/queries "<FIRST_MODEL_UPPER>_SEMANTIC" — the
        # existence probe would never match and the native semantic-view path
        # would be silently unreachable on the default scaffold (view_name="").
        resolved_view_name = view_name or SnowflakeDialect(view_name="").view_name(registry)
        dialect = SnowflakeDialect(view_name=resolved_view_name)
    elif view_name is not None:
        raise ValueError(
            "Provide either 'view_name' or a pre-configured 'dialect', not both. "
            "To override the view name on a custom dialect, set it when constructing "
            "the dialect (e.g. SnowflakeDialect(view_name='MY_VIEW')) and pass only "
            "the dialect argument."
        )

    # Derive human-readable table list for tool descriptions.
    model_summary = "; ".join(f"{m.name} (grain: {m.grain})" for m in registry.models)

    # ---------------------------------------------------------------------------
    # Tool descriptions — defined ONCE; referenced in both @mcp.tool and the
    # SemanticTool descriptor returned to the caller.  This avoids the drift
    # risk of keeping two copies in sync.
    # ---------------------------------------------------------------------------

    _list_models_desc = (
        "List every semantic model (grain) this data product exposes — each with "
        "its grain definition, metric count, dimension count, and join topology. "
        "A MODEL is the fundamental unit: every metric and every dimension lives "
        "under exactly one model, and a model corresponds to one grain (what "
        "one row represents, e.g. 'one person', 'one event'). "
        "Call this first to orient yourself: which models exist, how many metrics "
        "each has, and which models are join-reachable from which. "
        "Then call describe_model on the model whose grain matches your question."
    )
    _describe_model_desc = (
        "Describe a single semantic model in full: its grain, every metric it "
        "owns (with aggregation, description, and the exact set of dimensions "
        "each metric can be sliced by), every own dimension (type, PII flag, "
        "description), and every documented join with the set of dimensions "
        "it makes reachable. "
        "This replaces the need for separate list_metrics / list_dimensions / "
        "describe_metric calls — all vocabulary for one grain is returned together. "
        "CHASM-TRAP RULE: metrics from two different models must NEVER be combined "
        "in one run_semantic_query call. This tool makes that structural: you must "
        "call describe_model separately for each grain, which surfaces the "
        "incompatibility before you attempt the query. "
        "Call describe_model before run_semantic_query to pick a valid "
        "metric + dimension combination from the same model."
    )
    _run_semantic_query_desc = (
        "THE DEFAULT, SAFE way to answer a question about this data product. "
        "Name CONCEPTS and the data product writes correct, governed SQL — "
        "you never write SQL on this path.\n\n"
        f"Data models: {model_summary}.\n\n"
        "ARGS:\n"
        "- measures (REQUIRED): list of metric names from describe_model.\n"
        "- dimensions (optional): list of dimension names from describe_model "
        "to group by. OMIT IT (or pass []) for a grand total.\n"
        '- filters (optional): list of {"dimension": <name>, "op": <symbol>, '
        "\"value\": <val>}. The 'op' field (named 'op', NOT 'operator') MUST be "
        "one of these EXACT symbols: '=', '!=', '>', '>=', '<', '<=', 'IN', "
        "'LIKE', 'ILIKE' — use the symbol '=', NOT the word 'eq'/'equals'. "
        'Example: {"dimension": "status", "op": "=", "value": "Active"}.\n\n'
        "It DETERMINISTICALLY compiles the selection into a safe, aggregated, "
        "read-only query against the curated semantic view, runs it under "
        "governance, and returns the rows plus the compiled SQL. "
        "Use list_models / describe_model to discover valid models, metrics, "
        "and dimensions. Do not mix metrics from different models in one call."
    )

    # ---------------------------------------------------------------------------
    # list_models
    # ---------------------------------------------------------------------------

    _list_models_request = semantic_model(
        name="list_models_request",
        description="No arguments; lists every semantic model the data product exposes.",
    ).schema({})

    _list_models_response = semantic_model(
        name="list_models_response",
        description="The semantic models (grains) available on this data product.",
    ).schema(
        {
            "models": _row_list(
                "models",
                [
                    _field("name", string(), "Semantic model name."),
                    _field("grain", string(), "One-row-per grain of this model."),
                    _field("description", string(), "What the model represents."),
                    _field("metric_count", int64(), "Number of metrics owned by this model."),
                    _field("dimension_count", int64(), "Number of dimensions owned by this model."),
                    _field(
                        "joins",
                        _list(
                            _field(
                                "joins",
                                struct(
                                    [
                                        _field("to", string(), "Right-side model name."),
                                        _field("cardinality", string(), "Join cardinality."),
                                    ]
                                ),
                            )
                        ),
                        "Joins where this model is the left (MANY-side) endpoint.",
                    ),
                ],
                "One row per semantic model.",
            )
        }
    )

    @function(name="list_models")
    @mcp.tool(
        name="list_models",
        description=_list_models_desc,
    )
    def list_models(request: Request) -> Response:
        out: list[dict[str, object]] = []
        for m in registry.models:
            joins: list[dict[str, object]] = [
                {"to": j.right, "cardinality": j.cardinality.value} for (j, _reached) in registry.joins_of(m.name)
            ]
            out.append(
                {
                    "name": m.name,
                    "grain": m.grain,
                    "description": m.description,
                    "metric_count": len(registry.metrics_of(m.name)),
                    "dimension_count": len(registry.dimensions_of(m.name)),
                    "joins": joins,
                }
            )
        return Response({"models": out})

    # ---------------------------------------------------------------------------
    # describe_model
    # ---------------------------------------------------------------------------

    _describe_model_request = semantic_model(
        name="describe_model_request",
        description="The model to describe.",
    ).schema(
        {
            "name": (string(), "Model name (see list_models)."),
        }
    )

    _describe_model_response = semantic_model(
        name="describe_model_response",
        description=(
            "Full detail for one semantic model: grain, metrics (each with "
            "compatible dimensions), own dimensions, and join topology."
        ),
    ).schema(
        {
            "name": (string(), "Semantic model name."),
            "grain": (string(), "One-row-per grain of this model."),
            "description": (string(), "What the model represents."),
            "metrics": _row_list(
                "metrics",
                [
                    _field("name", string(), "Metric concept name."),
                    _field("aggregation", string(), "Aggregation applied."),
                    _field("description", string(), "Plain-language meaning."),
                    _field(
                        "compatible_dimensions",
                        _list(_field("compatible_dimensions", string())),
                        "Dimension names this metric can be grouped/filtered by.",
                    ),
                ],
                "Metrics owned by this model.",
            ),
            "dimensions": _row_list(
                "dimensions",
                [
                    _field("name", string(), "Dimension concept name."),
                    _field("type", string(), "Logical type."),
                    _field("pii", boolean(), "True if this dimension is PII (governed)."),
                    _field("description", string(), "What the dimension means."),
                ],
                "Dimensions physically owned by this model.",
            ),
            "joins": _row_list(
                "joins",
                [
                    _field("to", string(), "Right-side model name."),
                    _field("cardinality", string(), "Join cardinality."),
                    _field(
                        "reaches_dimensions",
                        _list(_field("reaches_dimensions", string())),
                        "Non-PII dimension names on the right model unlocked by this join "
                        "(a structural property of the join itself). For the authoritative, "
                        "per-metric slice list use each metric's compatible_dimensions above — "
                        "a metric with an explicit extra_dimensions override may reach a "
                        "narrower set than the join structurally unlocks.",
                    ),
                ],
                "Joins where this model is the left (MANY-side) endpoint.",
            ),
            "error": (string(), "Set if the model is unknown; empty otherwise."),
        }
    )

    @function(name="describe_model")
    @mcp.tool(
        name="describe_model",
        description=_describe_model_desc,
    )
    def describe_model(request: Request) -> Response:
        name = request.get("name") or ""
        model_obj = registry.model_of(name)
        if model_obj is None:
            known = ", ".join(m.name for m in registry.models)
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
        for met in registry.metrics_of(name):
            metrics_out.append(
                {
                    "name": met.name,
                    "aggregation": met.agg.value,
                    "description": registry.metric_description(met),
                    "compatible_dimensions": [d.name for d in registry.compatible_dimensions(met)],
                }
            )
        dimensions_out: list[dict[str, object]] = []
        for d in registry.dimensions_of(name):
            dimensions_out.append(
                {
                    "name": d.name,
                    "type": d.type,
                    "pii": bool(d.pii),
                    "description": registry.column_description(d.model, d.column, d.description),
                }
            )
        joins_out: list[dict[str, object]] = []
        for j, reached in registry.joins_of(name):
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

    _run_semantic_query_request = semantic_model(
        name="run_semantic_query_request",
        description=(
            "A semantic selection: which metrics, sliced by which dimensions, "
            "optionally filtered. The data product compiles this to safe SQL — "
            "you never write SQL yourself on this path."
        ),
    ).schema(
        {
            # measures is the only required field.
            "measures": (
                _list(_field("measures", string())),
                "Metric concept names to compute (see describe_model). Required.",
            ),
            # dimensions / filters are OPTIONAL. They are marked nullable AND left
            # without a field-level description on purpose: the RPC->pydantic
            # converter re-marks a field as REQUIRED whenever it carries a
            # description (it rebuilds the field with Field(description=...) and no
            # default). A nullable field with no description stays Optional and drops
            # out of the schema's `required` set, so an agent can call with just
            # {"measures": [...]}. The usage guidance (incl. the exact filter `op`
            # symbols) lives in the TOOL description instead, where the agent reads it.
            "dimensions": AttributeSpec(name="", data_type=_list(_field("dimensions", string()))).constraints(
                nullable=True
            ),
            "filters": AttributeSpec(
                name="",
                data_type=_list(
                    _field(
                        "filters",
                        struct(
                            [
                                _field("dimension", string()),
                                _field("op", string()),
                                _field("value", string()),
                            ]
                        ),
                    )
                ),
            ).constraints(nullable=True),
        }
    )

    _run_semantic_query_response = semantic_model(
        name="run_semantic_query_response",
        description=("Governed result: the compiled SQL (for transparency), the rows, and metadata."),
    ).schema(
        {
            "compiled_sql": (string(), "The SQL the data product generated and executed."),
            "row_count": (int64(), "Number of rows returned (after the row cap)."),
            "truncated": (boolean(), "True if capped at the row limit."),
            "columns": (
                _list(_field("columns", string())),
                "Result column names, in order.",
            ),
            "rows": (
                _list(_field("rows", string())),
                "Result rows; each a JSON-encoded array of that row's values.",
            ),
            "error": (string(), "Set if the selection was invalid or execution failed."),
        }
    )

    @function(name="run_semantic_query")
    @mcp.tool(
        name="run_semantic_query",
        description=_run_semantic_query_desc,
    )
    def run_semantic_query(snowflake: Any, request: Request) -> Response:
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

        selection: dict[str, Any] = {
            "measures": request.get("measures") or [],
            "dimensions": request.get("dimensions") or [],
            "filters": request.get("filters") or [],
        }
        if not selection["measures"]:
            return _error("No measures selected. Provide at least one metric name from describe_model in 'measures'.")

        if snowflake is None:
            return _error("No Snowflake connection is available.")

        sf_database: Any = snowflake.database  # pyright: ignore[reportUnknownMemberType]
        sf_schema: Any = snowflake.schema  # pyright: ignore[reportUnknownMemberType]
        fqn = f"{sf_database}.{sf_schema}." if sf_database else f"{sf_schema}."

        wrapped = ""
        try:
            conn: Any = connector.connect(  # pyright: ignore[reportUnknownMemberType]
                user=snowflake.user,  # pyright: ignore[reportUnknownMemberType]
                account=snowflake.account,  # pyright: ignore[reportUnknownMemberType]
                warehouse=snowflake.warehouse,  # pyright: ignore[reportUnknownMemberType]
                role=snowflake.role,  # pyright: ignore[reportUnknownMemberType]
                database=sf_database,
                schema=sf_schema,
                ocsp_fail_open=True,
                session_parameters={"STATEMENT_TIMEOUT_IN_SECONDS": 60},
                **snowflake.connector_params(),  # pyright: ignore[reportUnknownMemberType]
            )
            try:
                with conn.cursor() as cur:
                    # Prefer NATIVE Snowflake semantic view when provisioned;
                    # fall back to compiled base-table / plain-view path.
                    try:
                        native = dialect.supports_native_semantic_view(cur, fqn=fqn)
                    except Exception:
                        native = False
                    try:
                        if native:
                            sql = semantic_view_query(selection, registry=registry, dialect=dialect, fqn=fqn)
                        else:
                            sql = compile_selection(
                                selection,
                                registry=registry,
                                dialect=dialect,
                                fqn=fqn,
                                use_view=True,
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

    return [
        SemanticTool(
            name="list_models",
            fn=list_models,
            request_model=_list_models_request,
            response_model=_list_models_response,
            description=_list_models_desc,
        ),
        SemanticTool(
            name="describe_model",
            fn=describe_model,
            request_model=_describe_model_request,
            response_model=_describe_model_response,
            description=_describe_model_desc,
        ),
        SemanticTool(
            name="run_semantic_query",
            fn=run_semantic_query,
            request_model=_run_semantic_query_request,
            response_model=_run_semantic_query_response,
            description=_run_semantic_query_desc,
        ),
    ]

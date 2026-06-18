"""Deterministic concept-to-SQL compiler for the NXD semantic-layer stopgap (NEX-620).

Turns a selection ``{measures, dimensions, filters}`` (concept names from a
:py:class:`~nxd.experimental.semantic.registry.CompiledRegistry`) into a single
read-only, aggregated SQL query. The routing and validation logic is
dialect-independent; leaf SQL generation delegates to the
:py:class:`~nxd.experimental.semantic.dialect.Dialect` implementation.

Three compile paths (matching the PoC ``semantic_compile.py``):

- **single-model**: all metrics + dimensions live on one table → GROUP BY + agg.
- **cross-model N:1 join**: metric on the MANY side, dimension on the ONE side →
  plain join, then GROUP BY + agg (grain preserved; no fan-out).
- **native semantic view**: delegates to ``dialect.native_view_query`` via
  :py:func:`semantic_view_query`.

Chasm-trap defence is the load-bearing correctness property: metrics from
different fact grains in one selection raise :py:exc:`CompileError` with an
actionable message telling the caller to split into separate queries.

See: docs/architecture/adrs/020-semantic-layer-first-class.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from .dialect import Dialect
    from .registry import CompiledRegistry
    from .registry import Dimension
    from .registry import Metric


class CompileError(ValueError):
    """Raised when a selection cannot be compiled.

    The message is surfaced to the calling LLM so it can correct its selection
    (unknown concept, incompatible metric/dimension, mixed grain, etc.).
    """


# ---------------------------------------------------------------------------
# Literal escaping
# ---------------------------------------------------------------------------


def _lit(v: Any) -> str:
    """Render a Python value as a SQL literal (single-quoted string or number)."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Filter rendering
# ---------------------------------------------------------------------------


def _filter_sql(f: dict[str, Any], registry: CompiledRegistry) -> str:
    """Render one filter dict ``{dimension, op, value}`` as a SQL predicate.

    Resolves the dimension name via *registry*; uses the physical column name in
    the predicate (for base-table queries). Raises :py:exc:`CompileError` on an
    unknown dimension or unsupported operator.
    """
    dim_name = f.get("dimension") or f.get("name")
    op = (f.get("op") or "=").upper()
    val = f.get("value")
    dim = registry.find_dimension(dim_name) if dim_name else None
    if dim is None:
        raise CompileError(f"unknown filter dimension {dim_name!r}")
    col = dim.column
    if op in ("IN", "NOT IN") and isinstance(val, (list, tuple)):
        from typing import cast

        val_seq: list[Any] = cast(list[Any], val)
        rendered = ", ".join(_lit(v) for v in val_seq)
        return f"{col} {op} ({rendered})"
    if op in ("=", "!=", "<>", ">", ">=", "<", "<=", "LIKE", "ILIKE"):
        return f"{col} {op} {_lit(val)}"
    raise CompileError(
        f"unsupported filter op {op!r}. op MUST be one of these EXACT symbols: "
        "'=', '!=', '<>', '>', '>=', '<', '<=', 'LIKE', 'ILIKE', 'IN', 'NOT IN'."
    )


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def _resolve(
    measures: list[str],
    dimensions: list[str],
    registry: CompiledRegistry,
) -> tuple[list[Metric], list[Dimension]]:
    if not measures:
        raise CompileError("at least one metric is required")
    mets: list[Metric] = []
    for name in measures:
        m = registry.find_metric(name)
        if m is None:
            known = ", ".join(x.name for x in registry.metrics)
            raise CompileError(f"unknown metric {name!r}. Known metrics: {known}.")
        mets.append(m)
    dims: list[Dimension] = []
    for name in dimensions or []:
        d = registry.find_dimension(name)
        if d is None:
            known = ", ".join(x.name for x in registry.dimensions)
            raise CompileError(f"unknown dimension {name!r}. Known dimensions: {known}.")
        dims.append(d)
    return mets, dims


def _validate_selection(
    mets: list[Metric],
    dims: list[Dimension],
    registry: CompiledRegistry,
) -> str:
    """Validate + return the single fact-grain model name.

    Raises :py:exc:`CompileError` on:
    - Multiple metric models (chasm-trap).
    - A dimension incompatible with any selected metric.
    - Dimensions spanning more than one foreign model (star-schema fan-out guard).
      The single N:1 join case (all foreign dims from ONE other model) is allowed.
      See ADR-020 line ~229 ("the fallback join path must enforce it in the
      compiler"). Full multi-join generalisation is future work.
    """
    metric_models = {m.model for m in mets}
    if len(metric_models) > 1:
        raise CompileError(
            "metrics span multiple grains "
            f"({', '.join(sorted(metric_models))}); query one grain at a time "
            "to avoid fan-out double-counting. Split into separate queries."
        )
    metric_model = next(iter(metric_models))

    for m in mets:
        ok = {d.name for d in registry.compatible_dimensions(m)}
        for d in dims:
            if d.name not in ok:
                raise CompileError(
                    f"dimension {d.name!r} is not compatible with metric "
                    f"{m.name!r} (not on its model and no documented join)"
                )

    # Star-schema fan-out guard: dimensions must not span more than ONE foreign
    # model (i.e. a model other than the metric's own model). Two or more foreign
    # dimension models would require separate joins whose SQL the single-join
    # _compile_cross path cannot emit correctly — it picks only the first join
    # and silently qualifies every non-metric dim to that alias, producing wrong
    # or missing columns. Reject here with an actionable message so the caller
    # knows to split into separate queries or restrict to one foreign model.
    foreign_dim_models = {d.model for d in dims} - {metric_model}
    if len(foreign_dim_models) > 1:
        raise CompileError(
            f"dimensions span multiple models reachable only via separate joins "
            f"({', '.join(sorted(foreign_dim_models))}); slice by dimensions from "
            "at most one other model per query."
        )

    return metric_model


# ---------------------------------------------------------------------------
# SQL fragment helpers
# ---------------------------------------------------------------------------


def _select_list(mets: list[Metric], dims: list[Dimension], dialect: Dialect, qualify: str = "") -> str:
    parts = [f"{qualify}{d.column} AS {d.name}" for d in dims]
    parts += [f"{dialect.agg_expr(m)} AS {m.name}" for m in mets]
    return ",\n  ".join(parts)


def _group_by(dims: list[Dimension], qualify: str = "") -> str:
    if not dims:
        return ""
    return "\nGROUP BY " + ", ".join(f"{qualify}{d.column}" for d in dims)


def _where(filters: list[dict[str, Any]], registry: CompiledRegistry) -> str:
    if not filters:
        return ""
    return "\nWHERE " + " AND ".join(_filter_sql(f, registry) for f in filters)


# ---------------------------------------------------------------------------
# Compile paths
# ---------------------------------------------------------------------------


def _compile_single(
    model: str,
    mets: list[Metric],
    dims: list[Dimension],
    filters: list[dict[str, Any]],
    fqn: str,
    dialect: Dialect,
    registry: CompiledRegistry,
) -> str:
    table = f"{fqn}{model}"
    return f"SELECT\n  {_select_list(mets, dims, dialect)}\nFROM {table}{_where(filters, registry)}{_group_by(dims)}"


def _compile_cross(
    mets: list[Metric],
    dims: list[Dimension],
    filters: list[dict[str, Any]],
    fqn: str,
    dialect: Dialect,
    registry: CompiledRegistry,
    metric_model: str,
) -> str:
    """Cross-model: metric on the MANY side sliced by ONE-side dimensions.

    Finds the first MANY_TO_ONE join that connects the metric's model (MANY) to
    the dimension's model (ONE). The join keeps the MANY-side grain intact
    (no fan-out). Raises :py:exc:`CompileError` if no suitable join is found.
    """
    from .registry import Cardinality

    dim_models = {d.model for d in dims} - {metric_model}

    # Find the appropriate join(s) — metric model must be on the left (MANY) side.
    join = None
    for j in registry.joins:
        if j.left == metric_model and j.right in dim_models and j.cardinality == Cardinality.MANY_TO_ONE:
            join = j
            break

    if join is None:
        raise CompileError(
            f"no MANY_TO_ONE join found from metric model {metric_model!r} to "
            f"dimension model(s) {sorted(dim_models)}. "
            "Verify that the join is declared in the registry with the correct cardinality."
        )

    left_table = f"{fqn}{join.left}"
    right_table = f"{fqn}{join.right}"
    on = " AND ".join(f"l.{lc} = r.{rc}" for lc, rc in join.on)

    def qualify(d: Dimension) -> str:
        return "l." if d.model == join.left else "r."

    sel_parts = [f"{qualify(d)}{d.column} AS {d.name}" for d in dims]
    sel_parts += [f"{dialect.agg_expr(m)} AS {m.name}" for m in mets]
    grp = ""
    if dims:
        grp = "\nGROUP BY " + ", ".join(f"{qualify(d)}{d.column}" for d in dims)

    return (
        "SELECT\n  "
        + ",\n  ".join(sel_parts)
        + f"\nFROM {left_table} l\nJOIN {right_table} r ON {on}"
        + _where(filters, registry)
        + grp
    )


def _compile_against_view(
    mets: list[Metric],
    dims: list[Dimension],
    filters: list[dict[str, Any]],
    fqn: str,
    dialect: Dialect,
    registry: CompiledRegistry,
    view_name: str,
) -> str:
    """Project all concepts from the plain denormalised VIEW (pre-joined).

    Column names in the view must match the physical column names of the source
    tables (as ensured by :py:func:`plain_view_ddl`).
    """
    table = f"{fqn}{view_name}"
    return f"SELECT\n  {_select_list(mets, dims, dialect)}\nFROM {table}{_where(filters, registry)}{_group_by(dims)}"


def _plain_view_name(dialect: Dialect, registry: CompiledRegistry) -> str:
    """Derive the plain-view name consistently across compile paths."""
    if hasattr(dialect, "_resolve_view_name"):
        return dialect._resolve_view_name(registry)  # type: ignore[attr-defined]
    if registry.models:
        return f"{registry.models[0].name.upper()}_SEMANTIC"
    return "SEMANTIC_VIEW"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile_selection(
    selection: dict[str, Any],
    *,
    registry: CompiledRegistry,
    dialect: Dialect | None = None,
    fqn: str = "",
    use_view: bool = True,
) -> str:
    """Compile a ``{measures, dimensions, filters}`` selection to SQL.

    Parameters
    ----------
    selection:
        Dict with keys ``measures`` (list[str], required), ``dimensions``
        (list[str], optional), ``filters`` (list[dict], optional).
    registry:
        Compiled semantic registry.
    dialect:
        SQL dialect implementation. Defaults to :py:class:`~nxd.experimental.semantic.dialect.SnowflakeDialect`.
    fqn:
        Optional fully-qualified prefix (e.g. ``DB.SCHEMA.``) prepended to
        table/view names so the query runs independently of session database/schema.
    use_view:
        When True and a cross-model join is required, compile against the
        pre-joined view (same name as the native semantic view). When False,
        compile an inline JOIN query against base tables. Single-model selections
        always compile against the base table regardless.

    Raises
    ------
    CompileError
        On unknown concepts, mixed-grain metrics, or incompatible dimension/metric
        combinations.
    """
    if dialect is None:
        from .dialect import SnowflakeDialect

        dialect = SnowflakeDialect()

    measures = list(selection.get("measures") or [])
    dimensions = list(selection.get("dimensions") or [])
    filters = list(selection.get("filters") or [])

    mets, dims = _resolve(measures, dimensions, registry)
    metric_model = _validate_selection(mets, dims, registry)

    dim_models = {d.model for d in dims}
    needs_join = bool(dim_models - {metric_model})

    if not needs_join:
        return _compile_single(metric_model, mets, dims, filters, fqn, dialect, registry)
    if use_view:
        view_name = _plain_view_name(dialect, registry)
        return _compile_against_view(mets, dims, filters, fqn, dialect, registry, view_name)
    return _compile_cross(mets, dims, filters, fqn, dialect, registry, metric_model)


def semantic_view_query(
    selection: dict[str, Any],
    *,
    registry: CompiledRegistry,
    dialect: Dialect | None = None,
    fqn: str = "",
) -> str:
    """Build a native ``SEMANTIC_VIEW(...)`` query for *selection*.

    Applies the same up-front validation as :py:func:`compile_selection`
    (mixed-grain, incompatible-dimension) so the caller gets identical errors
    regardless of execution path. Delegates SQL rendering to ``dialect.native_view_query``.

    Raises :py:exc:`CompileError` if the dialect does not support native semantic
    views (returns ``None``).
    """
    if dialect is None:
        from .dialect import SnowflakeDialect

        dialect = SnowflakeDialect()

    measures = list(selection.get("measures") or [])
    dimensions = list(selection.get("dimensions") or [])
    filters = list(selection.get("filters") or [])

    mets, dims = _resolve(measures, dimensions, registry)
    _validate_selection(mets, dims, registry)

    # Validate filter dimensions
    for f in filters:
        fname = f.get("dimension") or f.get("name") or ""
        if fname and registry.find_dimension(fname) is None:
            raise CompileError(f"unknown filter dimension {fname!r}")

    sql = dialect.native_view_query(registry, selection, fqn)
    if sql is None:
        raise CompileError("The current dialect does not support native semantic views.")
    return sql


def native_semantic_view_ddl(
    registry: CompiledRegistry,
    *,
    dialect: Dialect | None = None,
    fqn: str = "",
) -> str | None:
    """Return backend DDL for the native semantic object, or ``None`` if unsupported.

    Delegates to ``dialect.native_view_ddl``.
    """
    if dialect is None:
        from .dialect import SnowflakeDialect

        dialect = SnowflakeDialect()
    return dialect.native_view_ddl(registry, fqn)


def plain_view_ddl(
    registry: CompiledRegistry,
    *,
    dialect: Dialect | None = None,
    fqn: str = "",
) -> str:
    """Return a generic ``CREATE OR REPLACE VIEW`` DDL joining all models.

    Dialect-independent: uses a plain SQL JOIN. Column names match physical
    column names from the source tables (so the same SELECT works against either
    the native semantic view or this stand-in).

    Only the first MANY_TO_ONE join is used. Raises :py:exc:`CompileError` when
    the registry has no joins.
    """
    from .registry import Cardinality

    if dialect is None:
        from .dialect import SnowflakeDialect

        dialect = SnowflakeDialect()

    view_name = _plain_view_name(dialect, registry)

    # Use the first MANY_TO_ONE join.
    join = next((j for j in registry.joins if j.cardinality == Cardinality.MANY_TO_ONE), None)
    if join is None:
        if not registry.joins:
            raise CompileError("plain_view_ddl requires at least one join in the registry.")
        join = registry.joins[0]

    on = " AND ".join(f"l.{lc} = r.{rc}" for lc, rc in join.on)

    # Collect unique physical columns from all dimensions and metrics.
    cols: list[str] = []
    seen: set[str] = set()
    for d in registry.dimensions:
        col = d.column
        if col in seen:
            continue
        seen.add(col)
        side = "l" if d.model == join.left else "r"
        cols.append(f"{side}.{col}")
    for m in registry.metrics:
        col = m.column
        if col == "*" or col in seen:
            continue
        seen.add(col)
        side = "l" if m.model == join.left else "r"
        cols.append(f"{side}.{col}")

    col_sql = ",\n  ".join(cols)
    return (
        f"CREATE OR REPLACE VIEW {fqn}{view_name} AS\n"
        f"SELECT\n  {col_sql}\n"
        f"FROM {fqn}{join.left} l\n"
        f"JOIN {fqn}{join.right} r ON {on}"
    )

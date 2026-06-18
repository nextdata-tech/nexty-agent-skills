"""SQL dialect abstraction for the NXD semantic-layer stopgap (NEX-620).

The :py:class:`Dialect` Protocol defines the seam between the
dialect-independent routing logic in ``compiler.py`` and backend-specific SQL
generation. :py:class:`SnowflakeDialect` implements the Snowflake backend,
lifting the exact SQL grammar verified live against a real Snowflake account
(NEX-620 PoC ``semantic_compile.py``).

See: docs/architecture/adrs/026-semantic-layer-first-class.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol
from typing import runtime_checkable

if TYPE_CHECKING:
    from .registry import CompiledRegistry
    from .registry import Metric


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Dialect(Protocol):
    """SQL dialect seam. Implement this Protocol to add a new backend."""

    def agg_expr(self, metric: Metric) -> str:
        """Return the SQL aggregation expression for *metric* (e.g. ``COUNT(*)``).

        For use in compiled base-table queries (``compile_selection``) where the
        compiler controls column qualification.
        """
        ...

    def native_view_ddl(self, registry: CompiledRegistry, fqn: str) -> str | None:
        """Return the backend DDL to create a native semantic object, or ``None``
        if the backend does not support one."""
        ...

    def native_view_query(self, registry: CompiledRegistry, selection: dict[str, Any], fqn: str) -> str | None:
        """Return a query against the native semantic object for *selection*, or
        ``None`` if unsupported."""
        ...

    def supports_native_semantic_view(self, cursor: Any, fqn: str) -> bool:
        """Return True if the native semantic object currently exists in the
        session and can be queried."""
        ...

    def view_name(self, registry: CompiledRegistry) -> str:
        """Return the view / semantic-view name to use for *registry*.

        Used by :py:func:`~nxd.experimental.semantic.compiler._plain_view_name`
        so that cross-compile-path name derivation never calls a private
        ``_resolve_view_name`` method via ``hasattr`` + ``type: ignore``.
        """
        ...


# ---------------------------------------------------------------------------
# Snowflake implementation
# ---------------------------------------------------------------------------


class SnowflakeDialect:
    """Snowflake SQL dialect for :py:class:`~nxd.experimental.semantic.compiler.compile_selection`.

    Produces:
    - ``CREATE OR REPLACE SEMANTIC VIEW`` DDL (``native_view_ddl``).
    - ``SELECT * FROM SEMANTIC_VIEW(...)`` query (``native_view_query``).
    - ``SHOW SEMANTIC VIEWS`` existence probe (``supports_native_semantic_view``).
    - ``agg_expr`` robust to physical typing via VARCHAR cast and boolean CASE.

    SQL grammar verified live against Snowflake lower-env (NEX-620, PoC
    ``semantic_compile.py``).
    """

    def __init__(self, view_name: str = "") -> None:
        """
        Parameters
        ----------
        view_name:
            The identifier of the Snowflake SEMANTIC VIEW / VIEW to create/query.
            When empty the registry's first model name + ``_SEMANTIC`` suffix is
            used as the default.
        """
        self._view_name = view_name

    def _resolve_view_name(self, registry: CompiledRegistry) -> str:
        if self._view_name:
            return self._view_name
        if registry.models:
            base = registry.models[0].name.upper()
            return f"{base}_SEMANTIC"
        return "SEMANTIC_VIEW"

    def view_name(self, registry: CompiledRegistry) -> str:
        """Return the semantic / plain view name for *registry*.

        Implements :py:meth:`~nxd.experimental.semantic.dialect.Dialect.view_name`.
        """
        return self._resolve_view_name(registry)

    # -- aggregation expressions ----------------------------------------------

    def agg_expr(self, metric: Metric) -> str:
        """Aggregation SQL for a metric in a base-table query.

        - COUNT(*) for bare COUNT.
        - COUNT(DISTINCT col) for COUNT_DISTINCT.
        - Boolean-flag SUM: ``SUM(CASE WHEN CAST(col AS VARCHAR) IN (truthy) THEN 1 ELSE 0 END)``.
        - Numeric aggs: ``AGG(TRY_CAST(CAST(col AS VARCHAR) AS DOUBLE))`` —
          robust to NUMBER/FLOAT/VARCHAR physical types and tolerant of staging
          text copies. TRY_CAST yields NULL (ignored by agg) on parse failures.
        """
        from .registry import Agg

        col = metric.column
        if metric.agg is Agg.COUNT and col == "*":
            return "COUNT(*)"
        if metric.agg is Agg.COUNT_DISTINCT:
            return f"COUNT(DISTINCT {col})"
        if metric.agg is Agg.COUNT:
            return f"COUNT({col})"
        if metric.boolean:
            truthy = "'true','TRUE','True','t','1','yes','YES'"
            return f"SUM(CASE WHEN CAST({col} AS VARCHAR) IN ({truthy}) THEN 1 ELSE 0 END)"
        return f"{metric.agg.value.upper()}(TRY_CAST(CAST({col} AS VARCHAR) AS DOUBLE))"

    # -- native semantic view DDL --------------------------------------------

    def _agg_expr_native(self, metric: Metric) -> str:
        """Aggregation expression inside ``CREATE SEMANTIC VIEW``.

        Column refs are unqualified (they resolve within the metric's logical
        table inside the DDL). COUNT_DISTINCT uses ``COUNT(DISTINCT col)`` (not
        ``COUNT_DISTINCT``).
        """
        from .registry import Agg

        col = metric.column
        if metric.agg is Agg.COUNT_DISTINCT:
            return f"COUNT(DISTINCT {col})"
        if metric.agg is Agg.COUNT:
            return "COUNT(*)" if col == "*" else f"COUNT({col})"
        if metric.boolean:
            return f"SUM(CASE WHEN {col} THEN 1 ELSE 0 END)"
        return f"{metric.agg.value.upper()}({col})"

    def _sv_alias(self, model_name: str) -> str:
        """Logical table alias for a model inside the SEMANTIC VIEW DDL.

        Strips common suffixes (_v, _fact, _dim) and lowercases for a clean
        alias, falling back to the full model name.
        """
        name = model_name.lower()
        for suffix in ("_view", "_fact", "_dim", "_v"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        return name

    def native_view_ddl(self, registry: CompiledRegistry, fqn: str = "") -> str | None:
        """Return ``CREATE OR REPLACE SEMANTIC VIEW`` DDL driven by *registry*.

        Verified grammar (NEX-620 PoC):
        - METRICS live in a ``METRICS (...)`` clause; metric/dimension names are
          table-qualified: ``alias.name AS AGG(COLUMN)``.
        - COUNT_DISTINCT renders as ``COUNT(DISTINCT col)`` (not ``COUNT_DISTINCT``).
        - RELATIONSHIPS reference the target table by logical alias (PK implicit):
          ``alias (col) REFERENCES other_alias``.
        - PRIMARY KEY is declared on the grain column of the TABLES entry.
        """
        from .registry import Cardinality

        sv_name = self._resolve_view_name(registry)

        # Build alias map: model_name -> sv_alias
        alias = {m.name: self._sv_alias(m.name) for m in registry.models}

        # TABLES clause: each model as "alias AS fqn_table PRIMARY KEY (grain)"
        table_entries: list[str] = []
        for m in registry.models:
            al = alias[m.name]
            grain_cols = ", ".join(c.strip() for c in m.grain.split(","))
            table_entries.append(f"    {al} AS {fqn}{m.name} PRIMARY KEY ({grain_cols})")
        tables_clause = "TABLES (\n" + ",\n".join(table_entries) + "\n  )"

        # RELATIONSHIPS clause: only N:1 joins become relationships
        rel_entries: list[str] = []
        for j in registry.joins:
            if j.cardinality is not Cardinality.MANY_TO_ONE:
                continue
            join_cols = ", ".join(lc for lc, _ in j.on)
            many_al = alias.get(j.left, j.left.lower())
            one_al = alias.get(j.right, j.right.lower())
            rel_entries.append(f"    {many_al} ({join_cols}) REFERENCES {one_al}")
        # DIMENSIONS clause: alias.name AS COLUMN
        dim_entries = [f"    {alias.get(d.model, d.model.lower())}.{d.name} AS {d.column}" for d in registry.dimensions]
        dims_clause = "DIMENSIONS (\n" + ",\n    ".join(dim_entries) + "\n  )"

        # METRICS clause: alias.name AS AGG(COLUMN)
        met_entries = [
            f"    {alias.get(m.model, m.model.lower())}.{m.name} AS {self._agg_expr_native(m)}"
            for m in registry.metrics
        ]
        mets_clause = "METRICS (\n" + ",\n    ".join(met_entries) + "\n  )"

        parts = [f"CREATE OR REPLACE SEMANTIC VIEW {fqn}{sv_name}", f"  {tables_clause}"]
        if rel_entries:
            parts.append(f"  RELATIONSHIPS ({chr(10)}" + ",\n".join(rel_entries) + "\n  )")
        parts.append(f"  {dims_clause}")
        parts.append(f"  {mets_clause}")
        return "\n".join(parts)

    # -- native semantic view query -------------------------------------------

    def native_view_query(
        self,
        registry: CompiledRegistry,
        selection: dict[str, Any],
        fqn: str = "",
    ) -> str | None:
        """Return ``SELECT * FROM SEMANTIC_VIEW(sv METRICS ... DIMENSIONS ... WHERE ...)``
        for *selection*.

        Verified grammar: METRICS and DIMENSIONS use semantic **names** (not
        physical columns). A WHERE clause inside SEMANTIC_VIEW(...) also
        references dimension names.

        Validation (mixed-grain / incompatible-dimension) is performed by the
        compiler *before* calling this method; this method only renders SQL.

        Filter ``op`` values are validated against the same closed allowlist used
        by the base-table path (``_ALLOWED_OPS`` / ``_render_predicate`` in
        ``compiler.py``) — unknown operators raise
        :py:exc:`~nxd.experimental.semantic.compiler.CompileError` before any
        SQL is emitted.
        """
        from .compiler import CompileError
        from .compiler import _render_predicate

        sv_name = self._resolve_view_name(registry)

        measures = list(selection.get("measures") or [])
        dimensions = list(selection.get("dimensions") or [])
        filters = list(selection.get("filters") or [])

        metric_names = ", ".join(measures)

        # Collect dimension names: selected + filter dims (de-duped, preserving order).
        all_dim_names: list[str] = []
        seen_dims: set[str] = set()
        for name in dimensions:
            if name not in seen_dims:
                seen_dims.add(name)
                all_dim_names.append(name)
        for f in filters:
            fname = f.get("dimension") or f.get("name") or ""
            if fname and fname not in seen_dims:
                seen_dims.add(fname)
                all_dim_names.append(fname)

        parts = [f"METRICS {metric_names}"]
        if all_dim_names:
            parts.append("DIMENSIONS " + ", ".join(all_dim_names))
        if filters:
            preds: list[str] = []
            for f in filters:
                dim_name = f.get("dimension") or f.get("name") or ""
                if not dim_name:
                    raise CompileError("filter is missing 'dimension' key")
                op = (f.get("op") or "=").upper()
                val = f.get("value")
                # _render_predicate enforces the allowlist — raises CompileError on
                # unknown op or IN/NOT IN with a scalar value.
                preds.append(_render_predicate(dim_name, op, val))
            parts.append("WHERE " + " AND ".join(preds))

        sv_args = " ".join(parts)
        return f"SELECT * FROM SEMANTIC_VIEW({fqn}{sv_name} {sv_args})"

    # -- existence probe ------------------------------------------------------

    def supports_native_semantic_view(self, cursor: Any, fqn: str = "") -> bool:
        """True if the semantic view currently exists as a native Snowflake object.

        Uses ``SHOW SEMANTIC VIEWS LIKE '<name>'`` (cheap metadata query, no
        table scan). Returns False on any error (e.g. DuckDB, insufficient
        privilege, view not yet provisioned).
        """
        view_id = self._view_name or "SEMANTIC_VIEW"
        qualified = fqn.rstrip(".")
        try:
            if qualified:
                cursor.execute(f"SHOW SEMANTIC VIEWS LIKE '{view_id}' IN SCHEMA {qualified}")
            else:
                cursor.execute(f"SHOW SEMANTIC VIEWS LIKE '{view_id}'")
            return len(cursor.fetchall()) > 0
        except Exception:
            return False

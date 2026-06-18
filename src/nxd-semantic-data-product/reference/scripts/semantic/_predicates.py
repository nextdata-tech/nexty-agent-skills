"""Shared predicate renderer for the NXD semantic-layer stopgap (NEX-620).

This is a neutral leaf module that contains the filter-operator allowlist and
shared predicate-rendering logic used by BOTH the base-table compiler path
(``compiler.py``) and the native semantic-view dialect path (``dialect.py``).
Neither of those modules imports from the other for predicate logic — both
import from this module instead, breaking the cyclic dependency.

See: (ADR under review in nxd PR #6893: docs/architecture/adrs/026-semantic-layer-first-class.md)
"""

from __future__ import annotations

from typing import Any


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
# Filter rendering (shared predicate renderer)
# ---------------------------------------------------------------------------

#: Closed allowlist of permitted filter operators.  Both the base-table path
#: (``_filter_sql`` in ``compiler.py``) and the native semantic-view path
#: (``SnowflakeDialect.native_view_query`` in ``dialect.py``) call
#: ``_render_predicate`` so the same allowlist governs both — closing the
#: injection gap where the native path previously accepted arbitrary ``op``
#: strings after only ``.upper()``.
_ALLOWED_OPS: frozenset[str] = frozenset({"=", "!=", "<>", ">", ">=", "<", "<=", "LIKE", "ILIKE", "IN", "NOT IN"})


def _render_predicate(col_or_name: str, op: str, val: Any) -> str:  # pyright: ignore[reportUnusedFunction]
    """Render a single filter predicate after operator allowlist enforcement.

    Parameters
    ----------
    col_or_name:
        The column reference or dimension name to use on the left-hand side of
        the predicate.  For base-table queries this is the physical column name;
        for native semantic-view queries this is the semantic dimension name.
    op:
        The operator string, already ``.upper()``-ed by the caller.
    val:
        The right-hand value.  Lists/tuples are valid only for ``IN``/``NOT IN``.

    Raises
    ------
    CompileError
        If *op* is not in :py:data:`_ALLOWED_OPS`, or if ``IN``/``NOT IN`` is
        used with a scalar value.
    """
    if op not in _ALLOWED_OPS:
        raise CompileError(
            f"unsupported filter op {op!r}. op MUST be one of these EXACT symbols: "
            "'=', '!=', '<>', '>', '>=', '<', '<=', 'LIKE', 'ILIKE', 'IN', 'NOT IN'."
        )
    if op in ("IN", "NOT IN"):
        if not isinstance(val, (list, tuple)):
            raise CompileError(
                f"filter op {op!r} requires a list value, got {type(val).__name__!r}. "
                'Pass a list of values, e.g. ["A", "B"].'
            )
        from typing import cast

        val_seq: list[Any] = cast(list[Any], val)
        rendered = ", ".join(_lit(v) for v in val_seq)
        return f"{col_or_name} {op} ({rendered})"
    return f"{col_or_name} {op} {_lit(val)}"

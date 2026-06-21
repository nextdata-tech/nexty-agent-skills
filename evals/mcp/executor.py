"""Governed Snowflake executor for the eval MCP server.

Ported from ``examples/t2sql-poc/harness/executor.py`` (the t2sql PoC), with the
one PoC-specific coupling (``contract.pharma_mesh``) removed: the mesh of base
tables is supplied explicitly by the caller as a plain list of table names, and
the PII map is passed in. The masking / statement-validation / governed-schema
mechanics are unchanged — they carry regression-hardened subtleties (multi-
statement reject, non-SELECT reject, LIMIT cap, UPPERCASE→lowercase keys) we do
not want to re-derive.

Governance boundary: construction materialises a per-principal Snowflake schema
of views — one per base table, with PII columns masked to ``CAST(NULL AS type)``
when the principal can't see PII. ``execute()`` issues ``USE SCHEMA <gov>`` so
unqualified table names in the compiled SQL resolve ONLY to those governed
views; the base tables are unreachable by bare name. The agent's compiled SQL
therefore cannot reach raw PII even if it tries.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from snowflake.connector import SnowflakeConnection

DEFAULT_LIMIT = 100_000
DEFAULT_TIMEOUT_S = 30

_ALLOWED_LEADING = ("SELECT", "WITH")


@dataclass(frozen=True)
class Principal:
    """A caller identity + its governance grants (flat in-process analog of an
    OpenFGA subject). ``can_see_pii=False`` masks PII columns to NULL in this
    principal's governed views."""

    name: str
    can_see_pii: bool = True
    row_filter_sql: str | None = None
    row_filter_table: str = ""


def _schema_name(principal: Principal) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", principal.name)
    return f"gov_{safe}"


def _base_schema() -> str:
    """Configured base schema (SNOWFLAKE_SCHEMA), uppercased to match Snowflake's
    unquoted-identifier storage so INFORMATION_SCHEMA lookups match."""
    schema = os.environ.get("SNOWFLAKE_SCHEMA", "")
    return schema.upper() if schema else "PUBLIC"


def _base_columns(con: SnowflakeConnection, table: str) -> list[tuple[str, str]]:
    """[(column_name_lower, sql_type), ...] for a base table in the base schema."""
    cur = con.cursor()
    cur.execute(
        "SELECT COLUMN_NAME, DATA_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
        "ORDER BY ORDINAL_POSITION",
        (_base_schema(), table.upper()),
    )
    rows = cur.fetchall()
    cur.close()
    return [(r[0].lower(), r[1]) for r in rows]


class GovernedExecutor:
    """The ONLY place compiled SQL touches data. See module docstring."""

    def __init__(
        self,
        con: SnowflakeConnection,
        principal: Principal,
        *,
        tables: list[str],
        pii_map: dict[str, list[str]],
        limit_cap: int = DEFAULT_LIMIT,
        timeout_s: int | None = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._con = con
        self.principal = principal
        self._limit_cap = limit_cap
        self._timeout_s = timeout_s
        self._schema = _schema_name(principal)
        self._base_schema = _base_schema()
        # Physical base tables of this scenario's mesh + the {table: [pii cols]}
        # map. Both supplied explicitly — no implicit pharma default.
        self._tables = sorted(set(tables))
        self._pii_map = pii_map
        self._build_governed_schema()

    # ------------------------------------------------------------------ build
    def _build_governed_schema(self) -> None:
        con = self._con
        pii = self._pii_map

        cur = con.cursor()
        try:
            cur.execute(f"DROP SCHEMA IF EXISTS {self._schema} CASCADE")
            cur.execute(f"CREATE SCHEMA {self._schema}")
        finally:
            cur.close()

        for table in self._tables:
            cols = _base_columns(con, table)
            if not cols:
                # No fixture for this table — skip; a reference would error,
                # which is the correct (fail-closed) behaviour.
                continue

            masked = (
                set(pii.get(table, [])) if not self.principal.can_see_pii else set()
            )

            select_items: list[str] = []
            for name, sqltype in cols:
                if name in masked:
                    select_items.append(f"CAST(NULL AS {sqltype}) AS {name}")
                else:
                    select_items.append(name)

            where = ""
            if (
                self.principal.row_filter_sql
                and table == self.principal.row_filter_table
            ):
                where = f" WHERE {self.principal.row_filter_sql}"

            view_sql = (
                f"CREATE VIEW {self._schema}.{table} AS "
                f"SELECT {', '.join(select_items)} "
                f"FROM {self._base_schema}.{table}{where}"
            )
            vcur = con.cursor()
            try:
                vcur.execute(view_sql)
            finally:
                vcur.close()

    # --------------------------------------------------------------- validate
    @staticmethod
    def _validate(sql: str) -> str:
        """Reject multi-statement and non-SELECT/WITH input; return trimmed sql."""
        if sql is None or not sql.strip():
            raise ValueError("empty SQL")
        stripped = sql.strip()

        body = stripped[:-1] if stripped.endswith(";") else stripped
        if ";" in body:
            raise ValueError("multi-statement SQL is not allowed")

        probe = re.sub(r"/\*.*?\*/", " ", body, flags=re.DOTALL)
        probe = re.sub(r"--[^\n]*", " ", probe)
        leading = probe.lstrip()
        head = leading.split(None, 1)[0].upper() if leading.split(None, 1) else ""
        if head not in _ALLOWED_LEADING:
            raise ValueError(
                f"only SELECT/WITH statements are allowed, got: {head or '<empty>'!r}"
            )
        return body

    def _inject_limit(self, sql: str) -> str:
        if re.search(r"\bLIMIT\b\s+\d+\s*$", sql, flags=re.IGNORECASE):
            return sql
        if re.search(r"\bLIMIT\b", sql, flags=re.IGNORECASE):
            return sql
        return f"{sql}\nLIMIT {self._limit_cap}"

    # ---------------------------------------------------------------- execute
    def execute(self, sql: str) -> list[dict]:
        """Validate, cap, point the session at the governed schema, execute, and
        return rows as list[dict] with LOWERCASE keys."""
        body = self._validate(sql)
        capped = self._inject_limit(body)

        con = self._con

        if self._timeout_s is not None:
            try:
                tcur = con.cursor()
                tcur.execute(
                    f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {int(self._timeout_s)}"
                )
                tcur.close()
            except Exception:
                pass

        try:
            scur = con.cursor()
            try:
                scur.execute(f"USE SCHEMA {self._schema}")
            finally:
                scur.close()

            cur = con.cursor()
            try:
                cur.execute(capped)
                columns = [d[0].lower() for d in cur.description] if cur.description else []
                rows = cur.fetchall()
            finally:
                cur.close()
        finally:
            try:
                rcur = con.cursor()
                rcur.execute(f"USE SCHEMA {self._base_schema}")
                rcur.close()
            except Exception:
                pass

        return [dict(zip(columns, row)) for row in rows]

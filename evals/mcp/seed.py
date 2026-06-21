"""Load a scenario's base-table fixtures into lower-env Snowflake.

Each MCP scenario ships ``fixtures/seed.sql`` — a sequence of DROP/CREATE/INSERT
statements that materialise the physical base tables the semantic registry maps
onto. The loader runs them against the configured base schema once per server
start. Idempotent: every seed.sql is authored DROP-then-CREATE so re-running is
safe and the governed views (built per-principal over these tables) always see a
known fixture state.

The statements run against SNOWFLAKE_SCHEMA (the base schema). The governed
executor then builds per-principal masked views OVER these tables in separate
``gov_*`` schemas, so the agent never touches these base tables by bare name.
"""

from __future__ import annotations

from pathlib import Path

from snowflake.connector import SnowflakeConnection


def _split_statements(sql_text: str) -> list[str]:
    """Split a seed.sql into individual statements on ``;`` at line ends.

    Seed files are simple DDL/DML — no procedural blocks, no ``;`` inside string
    literals in our fixtures — so a line-oriented split on trailing ``;`` is
    sufficient and avoids a SQL parser dependency. Comments (``--``) are stripped.
    """
    statements: list[str] = []
    buf: list[str] = []
    for raw in sql_text.splitlines():
        line = raw.split("--", 1)[0].rstrip()
        if not line.strip():
            continue
        buf.append(line)
        if line.endswith(";"):
            stmt = "\n".join(buf).rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            buf = []
    if buf:
        stmt = "\n".join(buf).strip()
        if stmt:
            statements.append(stmt)
    return statements


def load_seed(con: SnowflakeConnection, fixture_dir: Path) -> int:
    """Execute fixtures/seed.sql against the base schema. Returns statement count."""
    path = fixture_dir / "seed.sql"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing — an MCP scenario must ship a seed.sql that "
            "DROP+CREATE+INSERTs its physical base tables."
        )
    statements = _split_statements(path.read_text(encoding="utf-8"))
    cur = con.cursor()
    try:
        for stmt in statements:
            cur.execute(stmt)
    finally:
        cur.close()
    return len(statements)

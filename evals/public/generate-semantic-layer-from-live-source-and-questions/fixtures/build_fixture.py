#!/usr/bin/env python3
"""Materialize the scenario's sample DuckDB from the committed SQL seed.

Writes ``source.duckdb`` next to this script, containing ``main.customers``
and ``main.orders``. This stands in for the dlt sample load that, in a real
session, lands a sampled copy of the operational source into a local DuckDB
file — the eval materializes the same artifact deterministically from
``seed_tables.sql`` instead (a committed SQL seed is reviewable in git; a
binary .duckdb is not).

Idempotent: an existing source.duckdb is replaced.

Requires the ``duckdb`` package. If it is not importable, run:
    uv run --with duckdb python build_fixture.py
or: pip install duckdb
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = HERE / "seed_tables.sql"
OUT = HERE / "source.duckdb"


def main() -> int:
    try:
        import duckdb  # type: ignore
    except ImportError:
        print(
            "duckdb is required: `uv run --with duckdb python build_fixture.py` "
            "or `pip install duckdb`"
        )
        return 2

    for stale in (OUT, OUT.with_suffix(".duckdb.wal")):
        if stale.exists():
            stale.unlink()

    con = duckdb.connect(str(OUT))
    try:
        con.execute(SEED.read_text(encoding="utf-8"))
        tables = [row[0] for row in con.execute("SHOW TABLES").fetchall()]
        for table in tables:
            count = con.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0]
            print(f"main.{table}: {count} rows")
    finally:
        con.close()
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

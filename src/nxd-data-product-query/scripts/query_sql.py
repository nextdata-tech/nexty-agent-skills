"""Run a SQL query against the leased credential from connect_port.py.

Supports Snowflake, Postgres / pgvector, and any DB-API driver discovered by
type_hint in the leased credential. Reads credentials from --creds (the file
connect_port.py wrote); never accepts them on argv.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _connect(details: dict, location: dict, type_hint: str) -> Any:
    """Build a DB-API connection from the credential details + the location.

    Each driver maps the JSON fields differently — extend this when adding
    support for a new store.
    """
    t = (type_hint or "").lower()
    data = details.get("data") or details

    if "snowflake" in t:
        import snowflake.connector  # type: ignore

        # Key-pair leases hand back a PEM string (data.private_key_pem, or nested
        # under data.auth.private_key_pem). The connector wants a DER-encoded
        # private_key, so convert. Falls back to a raw DER private_key or a
        # password when those are what the lease provided.
        auth = data.get("auth") or {}
        pem = data.get("private_key_pem") or auth.get("private_key_pem")
        der = data.get("private_key")
        if pem and not der:
            from cryptography.hazmat.primitives import serialization  # type: ignore

            key = serialization.load_pem_private_key(
                pem.encode() if isinstance(pem, str) else pem, password=None
            )
            der = key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )

        return snowflake.connector.connect(
            user=data.get("username") or data.get("user"),
            password=data.get("_password") or data.get("password"),
            private_key=der,
            account=data.get("account") or location.get("account"),
            warehouse=data.get("warehouse") or location.get("warehouse"),
            database=data.get("database") or location.get("database"),
            schema=data.get("schema") or location.get("schema"),
            role=data.get("role"),
        )

    if "postgres" in t or "pgvector" in t:
        import psycopg  # type: ignore

        return psycopg.connect(
            host=data.get("host") or location.get("host"),
            port=int(data.get("port") or location.get("port") or 5432),
            dbname=data.get("database") or location.get("database"),
            user=data.get("username") or data.get("user"),
            password=data.get("_password") or data.get("password"),
            sslmode=data.get("sslmode", "require"),
        )

    sys.exit(f"unsupported sql driver: type_hint={type_hint!r}; extend query_sql.py")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--creds", required=True, help="Path to the JSON file connect_port.py wrote")
    p.add_argument("--sql", required=True)
    p.add_argument("--limit", type=int, default=100, help="Hard cap on rows returned (default 100)")
    args = p.parse_args()

    doc = json.loads(Path(args.creds).read_text())
    connect = doc.get("connect", {})
    location = (doc.get("location") or {}).get("location") or {}
    if connect.get("status") != "connected":
        sys.exit(
            f"port is not connected: status={connect.get('status')!r}; "
            "re-run connect_port.py and check the approval flow"
        )
    lc = connect["leased_credential"]
    details = lc.get("details", {})
    type_hint = details.get("type_hint") or lc.get("type") or ""

    conn = _connect(details, location, type_hint)
    try:
        cur = conn.cursor()
        cur.execute(args.sql)
        rows = cur.fetchmany(args.limit)
        cols = [d[0] for d in cur.description] if cur.description else []
        print(json.dumps({"columns": cols, "rows": [list(r) for r in rows]}, default=str, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()

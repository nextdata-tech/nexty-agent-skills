"""Execute read-only SQL against the live mesh via a leased DP-output credential.

This module leases a Snowflake credential from a data-product output port and
runs an arbitrary SELECT against the warehouse, returning rows as
``list[dict]`` with lowercased column keys — matching the fetch convention used
by the gold oracle (``freeze_gold._rows_from_cursor``).

It uses the MESH-LEASED credential path (``connect_output`` -> ephemeral
Snowflake cred), NOT the PoC's ``SNOWFLAKE_*`` environment variables. The
leased cred grants one role/warehouse against one account; for a cross-DP SQL
string the leased role must have SELECT over every referenced ``DB.SCHEMA``.

Wiring (mirrors ``connect_port.py`` + ``query_sql.py``):
    read_token -> find_dp -> get_location + connect_output
    -> snowflake.connector.connect(... from leased_credential.details.data ...)
    -> cursor.execute(sql) -> fetch -> lowercase keys.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# The query-skill scripts dir holds nxd_api (find_dp/connect_output/...). Add it
# to sys.path so this harness can lease without copying that client.
_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "nxd-query-data-product"
    / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

from nxd_api import connect_output, find_dp, get_location, read_token  # noqa: E402


# Defensive ceilings.
DEFAULT_ROW_CAP = 200
DEFAULT_STATEMENT_TIMEOUT_SECONDS = 120


def _lower_rows(columns: list[str], rows: list[tuple]) -> list[dict[str, Any]]:
    """Turn cursor rows into list[dict] with lowercased keys."""
    keys = [c.lower() for c in columns]
    return [dict(zip(keys, row)) for row in rows]


def lease_credential(
    *,
    dp: str,
    port: str,
    api_url: str,
    token_file: str | None = None,
    ttl: str = "PT1H",
) -> dict[str, Any]:
    """Lease an ephemeral credential for one DP output port.

    Returns the assembled document (same shape connect_port.py persists):
    ``{"dp": {...}, "port", "location", "connect"}``. Raises if the DP is not
    found or the port did not reach ``connected`` (e.g. approval_pending).
    """
    token = read_token(token_file)
    # find_mesh.py returns api_url WITH a trailing ``/api`` (the config ``url:``),
    # but nxd_api builds ``{base}/api/v1/...`` — passing the trailing-/api form
    # double-prefixes to ``/api/api/v1`` (404, surfaced as a misleading 401/404).
    # Normalize to the bare host base the REST helpers expect.
    if api_url.rstrip("/").endswith("/api"):
        api_url = api_url.rstrip("/")[: -len("/api")]
    dp_doc = find_dp(api_url, token, dp)
    if not dp_doc:
        raise RuntimeError(f"data product not found: {dp}")

    location = get_location(dp_doc, port, token)
    connect = connect_output(dp_doc, port, token, ttl=ttl)

    status = connect.get("status")
    if status != "connected":
        raise RuntimeError(
            f"port not connected: status={status!r} "
            f"(dp={dp} port={port}); cross-DP SQL cannot execute"
        )
    return {
        "dp": {"fullName": dp_doc["fullName"], "baseUrl": dp_doc["baseUrl"]},
        "port": port,
        "location": location,
        "connect": connect,
    }


def _connect_snowflake(creds: dict[str, Any]):
    """Build a Snowflake DB-API connection from a leased-credential document."""
    connect = creds.get("connect", {})
    if connect.get("status") != "connected":
        raise RuntimeError(f"port not connected: status={connect.get('status')!r}")

    location = (creds.get("location") or {}).get("location") or {}
    lc = connect["leased_credential"]
    details = lc.get("details", {})
    type_hint = (details.get("type_hint") or lc.get("type") or "").lower()
    if "snowflake" not in type_hint:
        raise RuntimeError(
            f"unsupported leased cred type_hint={type_hint!r}; live_exec only handles snowflake"
        )

    data = details.get("data") or details
    import snowflake.connector  # type: ignore

    # The temporal cred minted for a managed-access Snowflake port is KEY-PAIR
    # (JWT): it carries a ``private_key_pem`` (PEM text), NOT a password. The
    # connector wants the key as DER bytes via ``private_key``, so load the PEM
    # and serialize to DER when present. Fall back to password auth otherwise.
    private_key_der = data.get("private_key")
    pem = data.get("private_key_pem")
    if pem and private_key_der is None:
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(
            pem.encode("utf-8") if isinstance(pem, str) else pem, password=None
        )
        private_key_der = key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    return snowflake.connector.connect(
        user=data.get("username") or data.get("user"),
        password=data.get("_password") or data.get("password"),
        private_key=private_key_der,
        account=data.get("account") or location.get("account"),
        warehouse=data.get("warehouse") or location.get("warehouse"),
        database=data.get("database") or location.get("database"),
        schema=data.get("schema") or location.get("schema"),
        role=data.get("role"),
        # Mirror the DP's own run_semantic_query connect: fail-open OCSP (self-hosted
        # cert chains stall the OCSP responder) + bounded login/network retries so a
        # slow first auth doesn't hang the eval.
        ocsp_fail_open=True,
        login_timeout=30,
        network_timeout=30,
    )


def execute_sql(
    sql: str,
    creds: dict[str, Any],
    *,
    row_cap: int = DEFAULT_ROW_CAP,
    statement_timeout_seconds: int = DEFAULT_STATEMENT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Execute one read-only SQL string and return rows as list[dict].

    Column keys are lowercased to match the gold oracle's fetch convention.
    Defensive: a server-side statement timeout, a hard fetch cap, and the
    connection is always closed.
    """
    conn = _connect_snowflake(creds)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {int(statement_timeout_seconds)}"
            )
        except Exception:
            # Non-fatal: some leased roles may not permit ALTER SESSION.
            pass
        cur.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(int(row_cap))
        return _lower_rows(columns, rows)
    finally:
        conn.close()


def run(
    sql: str,
    *,
    dp: str,
    port: str,
    api_url: str,
    token_file: str | None = None,
    ttl: str = "PT1H",
    row_cap: int = DEFAULT_ROW_CAP,
    statement_timeout_seconds: int = DEFAULT_STATEMENT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Lease a credential then execute ``sql``. Convenience one-shot."""
    creds = lease_credential(
        dp=dp, port=port, api_url=api_url, token_file=token_file, ttl=ttl
    )
    return execute_sql(
        sql,
        creds,
        row_cap=row_cap,
        statement_timeout_seconds=statement_timeout_seconds,
    )


def _smoke() -> None:
    """Execute the proven compiled cross-DP SQL at /tmp/xdp-live2.sql.

    Resolves the mesh (api_url + token_file) via find_mesh.py, leases against
    the subjects DP's default output port, and prints row count + first rows.
    Override the lease target with env vars:
        XDP_DP    (default pharma-subjects-demo)
        XDP_PORT  (default default)
        XDP_SQL   (default /tmp/xdp-live2.sql)
    """
    import json
    import subprocess

    sql_path = Path(os.environ.get("XDP_SQL", "/tmp/xdp-live2.sql"))
    sql = sql_path.read_text()

    find_mesh = _SKILL_SCRIPTS / "find_mesh.py"
    proc = subprocess.run(
        [sys.executable, str(find_mesh)],
        capture_output=True,
        text=True,
        check=True,
    )
    mesh = json.loads(proc.stdout)
    api_url = mesh["api_url"]
    token_file = mesh.get("token_file")

    dp = os.environ.get("XDP_DP", "pharma-subjects-demo")
    port = os.environ.get("XDP_PORT", "default")

    print(f"lease dp={dp} port={port} api_url={api_url}", file=sys.stderr)
    rows = run(sql, dp=dp, port=port, api_url=api_url, token_file=token_file)

    print(f"row_count={len(rows)}")
    for r in rows[:10]:
        print(json.dumps(r, default=str))


if __name__ == "__main__":
    _smoke()

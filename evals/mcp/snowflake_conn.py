"""Snowflake connection helper for the eval MCP server.

Ported verbatim from the t2sql PoC harness — credentials come from env vars
ONLY (lower-env Snowflake, from the infra-profile-lower-envs GCP secret).

SECURITY NOTE: Credentials are sourced from environment variables ONLY.
They are never hardcoded, never committed, and never written to log output.
The real infra-profile lives in a gitignored `.nxd/*.yaml` —
this module does not read that file; it reads ONLY the env vars below.

Required env vars:
    SNOWFLAKE_ACCOUNT   — account identifier in <org>-<account> form
    SNOWFLAKE_USER      — Snowflake username
    SNOWFLAKE_WAREHOUSE — virtual warehouse name
    SNOWFLAKE_DATABASE  — target database
    SNOWFLAKE_SCHEMA    — target schema

Auth (one of):
    SNOWFLAKE_PRIVATE_KEY       — PEM string (may contain literal \\n)
    SNOWFLAKE_PRIVATE_KEY_PATH  — path to a PEM file on disk
    SNOWFLAKE_PASSWORD          — password fallback (not recommended for prod)

Optional:
    SNOWFLAKE_ROLE     — role to assume after connecting
"""

from __future__ import annotations

import os
import textwrap

import snowflake.connector
from snowflake.connector import SnowflakeConnection


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_private_key_der() -> bytes:
    """Load a PKCS8 private key from env and return DER bytes.

    Accepts either:
      - SNOWFLAKE_PRIVATE_KEY  — PEM text, may contain literal ``\\n`` escapes
        (as written by some secret managers) which are normalised to real newlines.
      - SNOWFLAKE_PRIVATE_KEY_PATH — path to a PEM file on disk.

    Returns the key encoded as DER bytes suitable for the ``private_key``
    kwarg of ``snowflake.connector.connect``.
    """
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        load_pem_private_key,
    )

    pem_str = os.environ.get("SNOWFLAKE_PRIVATE_KEY")
    if pem_str:
        # Secret managers often store literal \n instead of real newlines.
        pem_str = pem_str.replace("\\n", "\n")
        pem_bytes = pem_str.encode()
    else:
        path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
        if not path:
            return b""  # signal: no key available
        with open(path, "rb") as fh:
            pem_bytes = fh.read()

    key = load_pem_private_key(pem_bytes, password=None)
    return key.private_bytes(
        encoding=Encoding.DER,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"Missing required env var {name!r}. "
            "Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE, "
            "SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA and either "
            "SNOWFLAKE_PRIVATE_KEY / SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD."
        )
    return val


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def connect() -> SnowflakeConnection:
    """Open and return a Snowflake connection configured from env vars.

    Auth priority:
      1. Keypair  — if SNOWFLAKE_PRIVATE_KEY or SNOWFLAKE_PRIVATE_KEY_PATH set.
      2. Password — if SNOWFLAKE_PASSWORD set (useful for local smoke-tests).
      3. Error    — if neither is present.

    Raises:
        RuntimeError: if any required env var is absent or auth config missing.
    """
    account = _require_env("SNOWFLAKE_ACCOUNT")
    user = _require_env("SNOWFLAKE_USER")
    warehouse = _require_env("SNOWFLAKE_WAREHOUSE")
    database = _require_env("SNOWFLAKE_DATABASE")
    schema = _require_env("SNOWFLAKE_SCHEMA")
    role = os.environ.get("SNOWFLAKE_ROLE")  # optional

    common: dict = dict(
        account=account,
        user=user,
        warehouse=warehouse,
        database=database,
        schema=schema,
    )
    if role:
        common["role"] = role

    # --- keypair auth (preferred) ---
    der = _load_private_key_der()
    if der:
        return snowflake.connector.connect(**common, private_key=der)

    # --- password fallback ---
    password = os.environ.get("SNOWFLAKE_PASSWORD")
    if password:
        return snowflake.connector.connect(**common, password=password)

    raise RuntimeError(
        textwrap.dedent("""\
            No Snowflake authentication method found.
            Set one of:
              SNOWFLAKE_PRIVATE_KEY       (PEM string)
              SNOWFLAKE_PRIVATE_KEY_PATH  (path to PEM file)
              SNOWFLAKE_PASSWORD          (password — not recommended for prod)
        """)
    )

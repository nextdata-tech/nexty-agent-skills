#!/usr/bin/env python3
"""Standalone, dependency-light connectivity probe for the
crm-pipeline-current-v2 api-source closure. Uses only the Python standard
library so it never depends on NXD, dlt, DuckDB, or the generated
transform.

Run manually, with credentials supplied through the authoring session's
runtime secret input (never embedded or printed here):

    NXD_EVAL_SOURCE_TOKEN=<token> python3 connectivity_check.py

It makes one bounded, read-only GET against the configured `deals`
resource, asserts a parseable envelope matching the expected shape, and
prints a bounded, sanitized summary. Secret-like values and personal data
are never printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

# Anchor on this file's own directory, never the caller's cwd.
_CLOSURE = Path(__file__).resolve().parent

# Non-secret resource plan, fixed from the settled blueprint/proposal —
# does not depend on infra-profile.yaml existing yet.
_BASE_URL = "http://127.0.0.1:62519"
_AUTH_HEADER = "Authorization"
_AUTH_SCHEME = "Bearer"
_CREDENTIAL_ENV = "NXD_EVAL_SOURCE_TOKEN"
_RESOURCES = [
    {"model": "deals", "path": "/deals", "data_selector": "data"},
]

_PUBLIC_SUFFIXES = ("host", "port", "database", "schema", "base_url", "auth_type", "region")


def _redact(exc: BaseException) -> str:
    text = str(exc)
    token = os.environ.get(_CREDENTIAL_ENV)
    if token:
        text = text.replace(token, "<redacted>")
    return text


def _bounded_get(path: str) -> tuple[int, dict]:
    token = os.environ.get(_CREDENTIAL_ENV)
    if not token:
        raise SystemExit(f"connectivity check skipped: {_CREDENTIAL_ENV} is not set in this session")
    url = _BASE_URL.rstrip("/") + path
    request = urllib.request.Request(
        url,
        headers={_AUTH_HEADER: f"{_AUTH_SCHEME} {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SystemExit(f"connectivity check failed: {_redact(exc)}") from None
    except URLError as exc:
        raise SystemExit(f"connectivity check failed: {_redact(exc)}") from None
    return status, body


def main() -> int:
    if not os.environ.get(_CREDENTIAL_ENV):
        print(
            "connectivity check: NOT RUN — no credential available in this "
            "session; payload inspection and connectivity remain unverified.",
        )
        return 0

    ok = True
    for resource in _RESOURCES:
        model = resource["model"]
        try:
            status, body = _bounded_get(resource["path"])
        except SystemExit as exc:
            print(f"{model}: FAILED — {exc}")
            ok = False
            continue
        selector = resource["data_selector"]
        rows = body.get(selector) if isinstance(body, dict) else None
        if not isinstance(rows, list):
            print(f"{model}: FAILED — response envelope has no {selector!r} row array")
            ok = False
            continue
        if not rows:
            print(f"{model}: NO ROWS — the endpoint answered and the credential is accepted, but the response held no rows.")
            ok = False
            continue
        top_keys = sorted(body.keys()) if isinstance(body, dict) else []
        sample = rows[0] if isinstance(rows[0], dict) else {}
        sample_keys = sorted(sample.keys())
        print(
            f"{model}: OK — HTTP {status}, top-level keys {top_keys}, "
            f"{len(rows)} row(s) on this page, sample row keys {sample_keys}, "
            f"next_cursor={body.get('next_cursor')!r}"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

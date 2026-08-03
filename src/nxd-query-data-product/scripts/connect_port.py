"""Fetch a port's location + a leased credential.

Writes the full JSON document (location + connect response) to --out (mode 600);
prints a *sanitised* summary to stdout — no secret values, only the field names.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from nxd_api import connect_output, find_dp, get_location, read_token


SECRET_HINTS = (
    "password",
    "secret",
    "token",
    "key",
    "credential",
    "url",  # presigned URLs are secrets
    "private",
    "pem",
)


def _write_private(path: Path, text: str) -> None:
    """Write text to a 0600 file, created with restrictive perms from the start.

    Using os.open with mode 0o600 (instead of write_text + chmod) closes the
    window where the credential file would briefly be readable by group/other
    under the active umask on a shared host.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def _redact_keys(obj: Any) -> Any:
    """Mask any leaf whose key looks like a secret. Used only for the stdout summary."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out[k] = _redact_keys(v)
            elif any(h in k.lower() for h in SECRET_HINTS):
                out[k] = "<redacted>"
            else:
                out[k] = v
        return out
    if isinstance(obj, list):
        return [_redact_keys(x) for x in obj]
    return obj


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True)
    p.add_argument("--dp", required=True, help="Data Product fullName")
    p.add_argument("--port", required=True, help="Output port name")
    p.add_argument("--ttl", default="PT1H", help="ISO-8601 duration (default PT1H)")
    p.add_argument("--token-file")
    p.add_argument(
        "--out",
        default=str(Path(tempfile.gettempdir()) / "nxd-query-data-product" / "port.json"),
        help="Where to write the full leased-credential document (mode 600).",
    )
    args = p.parse_args()

    token = read_token(args.token_file)
    dp = find_dp(args.api_url, token, args.dp)
    if not dp:
        sys.exit(f"data product not found: {args.dp}")

    location = get_location(dp, args.port, token)
    connect = connect_output(dp, args.port, token, ttl=args.ttl)

    doc = {
        "dp": {"fullName": dp["fullName"], "baseUrl": dp["baseUrl"]},
        "port": args.port,
        "location": location,
        "connect": connect,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_private(out_path, json.dumps(doc, indent=2))

    summary = {
        "out_file": str(out_path),
        "status": connect.get("status"),
        "infra_profile_name": connect.get("infra_profile_name") or location.get("infra_profile_name"),
        "infra_service_name": connect.get("infra_service_name") or location.get("infra_service_name"),
        "location": _redact_keys(location.get("location") or {}),
        "leased_credential_type": (connect.get("leased_credential") or {}).get("type"),
        "leased_credential_ttl": (connect.get("leased_credential") or {}).get("ttl"),
        "approval_message": connect.get("message"),
        "approval_tracking_url": connect.get("tracking_url"),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

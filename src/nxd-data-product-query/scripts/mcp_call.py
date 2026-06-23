"""Strict mode — one-shot MCP ``tools/call`` against a DP MCP endpoint.

Thin CLI wrapper over ``mcp_http.call_tool_one_shot`` so a validated plan
step can be executed without writing Python glue per call. Opens an MCP
session (``initialize`` → ``notifications/initialized``), calls one
tool, closes the session, writes the unwrapped tool result to disk.

Used by the strict-mode flow once ``plan_validator.py`` returns
``passed=true`` — walk ``plan.steps[]``, invoke this script per step
with the resolved ``request`` payload, collect the per-step result
files into the final response.

Endpoint URL is taken from the gateway catalogue
(``endpoints[*].endpoint`` written by ``mcp_gateway.py``). The
bearer token comes from ``--token-file`` (preferred) or, falling back,
from the active mesh entry the way ``mcp_gateway.py`` resolves it.

Never writes secrets to stdout or to the chat. Tool responses go to
``--out`` (default ``/tmp/nxd-mcp-call.json``); stdout carries only a
status summary.

CLI:

    python3 mcp_call.py \\
        --endpoint https://dp.<mesh>.<domain>/<dp>/rpcs/<port>/mcp/ \\
        --tool <tool-name> \\
        --args '<json>' \\
        --token-file /tmp/strict-tok.txt \\
        --out /tmp/nxd-step-s1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mcp_http import McpClient, McpError, with_retry
from nxd_api import read_token, resolve_mesh


def _unwrap_tool_result(result: dict[str, Any]) -> Any:
    """MCP ``tools/call`` returns ``{content: [...], structuredContent?: {...}, isError?: bool}``.

    Mirrors the unwrap in ``semantic_relations.py``: prefer
    ``structuredContent`` when present; otherwise stitch any text blocks
    from ``content`` together and try to parse as JSON; fall back to
    the raw result so the caller can still inspect it.
    """
    if not isinstance(result, dict):
        return result
    if "structuredContent" in result and result["structuredContent"] is not None:
        return result["structuredContent"]
    content = result.get("content")
    if isinstance(content, list):
        texts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        joined = "\n".join(texts)
        if joined.strip():
            try:
                return json.loads(joined)
            except json.JSONDecodeError:
                return {"text": joined}
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--endpoint",
        required=True,
        help="DP MCP endpoint URL (from gateway catalogue endpoints[*].endpoint)",
    )
    p.add_argument("--tool", required=True, help="MCP tool name to call")
    p.add_argument(
        "--args",
        default="{}",
        help="JSON object passed as the tool's arguments (default {})",
    )
    p.add_argument(
        "--token-file",
        help="Path to a file holding the bearer token (preferred); falls back to active-mesh token",
    )
    p.add_argument("--mesh", help="Mesh name (only used when --token-file is omitted)")
    p.add_argument(
        "--out",
        default="/tmp/nxd-mcp-call.json",
        help="Where to write the unwrapped tool result (default /tmp/nxd-mcp-call.json)",
    )
    p.add_argument(
        "--raw",
        action="store_true",
        help="Write the raw ``tools/call`` envelope to --out instead of the unwrapped result",
    )
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument(
        "--ca-bundle",
        help="Path to a CA bundle for TLS verification. Needed for LOCAL "
        "clusters with a self-signed cert (e.g. the cluster's nxdCA.crt). "
        "Also honored via REQUESTS_CA_BUNDLE / SSL_CERT_FILE env vars.",
    )
    args = p.parse_args()

    try:
        arguments = json.loads(args.args)
    except json.JSONDecodeError as exc:
        sys.exit(f"--args is not valid JSON: {exc}")
    if not isinstance(arguments, dict):
        sys.exit("--args must be a JSON object")

    if args.token_file:
        token = read_token(args.token_file)
    else:
        m = resolve_mesh(args.mesh)
        if not m.token:
            sys.exit("no bearer token for the active mesh — run nxd-setup or nxd login")
        token = m.token

    try:
        with McpClient(
            endpoint=args.endpoint, token=token, timeout=args.timeout,
            verify=args.ca_bundle if args.ca_bundle else None,
        ) as c:
            # Retry transient 5xx — cold DP proxies frequently 503 the first
            # tools/call after a wake-up; subsequent calls warm up.
            raw = with_retry(lambda: c.tools_call(args.tool, arguments))
    except McpError as exc:
        hint = ""
        if exc.code == 401:
            # 401 = wrong/expired token for the header it was sent on. mcp_http
            # picks the header by token TYPE (PAT → X-Nextdata-Token, the
            # documented MCP auth; OAuth → Authorization: Bearer). A 401 means
            # the token is missing/expired, NOT the wrong kind. Refresh it.
            hint = (
                " — 401: the MCP token is missing or expired. For a PAT, re-check "
                "`nxd mcp config` / re-mint (`nxd create personal-access-token`); "
                "for an OAuth session token, run `nxd whoami` to refresh "
                "~/.nxd/tokens.json. Then retry."
            )
        sys.exit(f"MCP error {exc.code} at {exc.endpoint}: {exc.message}{hint}")
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"{type(exc).__name__}: {exc}")

    payload: Any = raw if args.raw else _unwrap_tool_result(raw)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))

    is_error = bool(raw.get("isError")) if isinstance(raw, dict) else False
    summary = {
        "out": str(out_path),
        "endpoint": args.endpoint,
        "tool": args.tool,
        "is_error": is_error,
        "raw_envelope": args.raw,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

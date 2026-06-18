"""Strict mode — discover DP MCP endpoints + their tool catalogues.

Source of truth for the endpoint list is the mesh MCP gateway, queried via
the CLI: ``nxd mcp health --format json`` (wraps ``GET /health/dps`` on
mcp-proxy-api). For each healthy/degraded DP MCP endpoint we then open a
short MCP session via Streamable HTTP and call ``tools/list`` to capture
the function names + JSON-Schema input shapes — that information is not
exposed by ``nxd mcp health`` itself.

Writes one JSON document to ``--out``:

    {
      "mesh": "<name>",
      "summary": {...},
      "endpoints": [
        {"endpoint": "https://...", "dp_full_name": "...", "port": "...",
         "state": "Healthy|Degraded|Broken|Unknown",
         "tool_count_reported": 2,
         "tools": [{"name": "...", "description": "...", "input_schema": {...}}],
         "error": null}
      ],
      "function_index": [{"dp": "...", "tool": "..."}],
      "errors": [...]
    }

CLI:

    python3 mcp_gateway.py --mesh <name> --token-file /tmp/nxd.tok \
        --out /tmp/nxd-mcp-gateway.json [--include-broken]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from mcp_http import McpClient, McpError, normalise_endpoint
from nxd_api import read_token, resolve_mesh


def _run_nxd_mcp_health(mesh: str | None) -> dict:
    """Invoke ``nxd mcp health --format json`` and assert the shape this
    script depends on.

    Verified CLI output shape (as of `nxd mcp` wrapping mcp-proxy-api's
    ``GET /health/dps``):

        {
          "service": "mcp-proxy-api",
          "version": "...",
          "summary": {"total": int, "healthy": int, ...},
          "discovery_stream": {...},
          "data_products": [
            {
              "endpoint": "https://.../<dp>/rpcs/<port>/mcp/",
              "derived_state": "Healthy|Degraded|Broken|Unknown",
              "http": {"healthy": bool, ...},
              "mcp": {"tool_count": int, "breaker": {"state": "Closed|Open|..."}, ...}
            },
            ...
          ]
        }

    If the top-level ``data_products`` key disappears or is renamed, this
    function exits loudly rather than letting the rest of the script
    silently parse zero endpoints and report a successful empty
    catalogue. Same for ``data_products[*].mcp`` — its absence in any
    row falls through to ``tool_count`` 0 and is recorded per-row, not
    treated as a fatal mismatch (a single misshapen row should not kill
    the whole discovery)."""
    cmd = ["nxd", "mcp", "health", "--format", "json"]
    if mesh:
        cmd.extend(["--mesh", mesh])
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        sys.exit("nxd CLI not on PATH — install nxd or run nxd-setup")
    if p.returncode != 0:
        sys.exit(f"nxd mcp health failed (exit {p.returncode}): {p.stderr.strip()[:500]}")
    try:
        parsed = json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        sys.exit(f"nxd mcp health emitted invalid JSON: {exc}; first 200 chars: {p.stdout[:200]!r}")

    if not isinstance(parsed, dict):
        sys.exit(
            f"nxd mcp health returned a non-object top-level value ({type(parsed).__name__}); "
            f"expected an object with a 'data_products' key"
        )
    if "data_products" not in parsed:
        sys.exit(
            "nxd mcp health output is missing the 'data_products' key — the CLI output schema "
            "appears to have changed. Top-level keys present: "
            f"{sorted(parsed.keys())}. Update mcp_gateway.py to match the new shape "
            "(see the docstring on _run_nxd_mcp_health for the verified shape)."
        )
    if not isinstance(parsed["data_products"], list):
        sys.exit(
            "nxd mcp health: 'data_products' is "
            f"{type(parsed['data_products']).__name__}, expected a list"
        )
    return parsed


def _dp_and_port(endpoint: str) -> tuple[str, str]:
    """Pull the DP fullName + port from the proxy URL path.

    Proxy URL shape: ``<scheme>://<dp-host>/<dp_full_name>/rpcs/<port>/mcp/``
    Anything that doesn't match returns empty strings — the caller still
    records the endpoint, just without parsed identifiers."""
    path = urlparse(endpoint).path.strip("/").split("/")
    # expect: [<dp_full_name>, "rpcs", <port>, "mcp"]
    if len(path) >= 4 and path[1] == "rpcs" and path[3] == "mcp":
        return path[0], path[2]
    return "", ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mesh", help="Mesh name when multiple are configured")
    p.add_argument("--token-file", help="Path to a file holding the bearer token (preferred)")
    p.add_argument("--out", required=True, help="Where to write the gateway catalogue JSON")
    p.add_argument(
        "--include-broken",
        action="store_true",
        help="Also attempt tools/list against endpoints whose breaker is open (default: skip)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Per-endpoint MCP timeout in seconds (default 15)",
    )
    args = p.parse_args()

    health = _run_nxd_mcp_health(args.mesh)

    if args.token_file:
        token = read_token(args.token_file)
        # Token came from --token-file; mesh name unknown here unless passed.
        mesh_name = args.mesh or ""
    else:
        m = resolve_mesh(args.mesh)
        if not m.token:
            sys.exit("no bearer token for the active mesh — run nxd-setup or nxd login")
        token = m.token
        mesh_name = m.name

    endpoints_out: list[dict] = []
    fn_index: list[dict] = []
    errors: list[dict] = []

    # `_run_nxd_mcp_health` already asserted `data_products` is a list,
    # so a missing/renamed key would have exited at parse time rather
    # than producing a silent empty catalogue here.
    for dp in health["data_products"]:
        # Per-row fields per the verified shape in _run_nxd_mcp_health:
        #   endpoint:       str — proxy URL
        #   derived_state:  str — Healthy / Degraded / Broken / Unknown
        #   mcp.tool_count: int — number of tools reported by the DP
        # Missing-row-field defaults (e.g. ``mcp`` absent) record as
        # tool_count=0 rather than killing the whole discovery; a single
        # ragged row should not erase the rest of the catalogue.
        endpoint_raw = dp.get("endpoint") or ""
        endpoint = normalise_endpoint(endpoint_raw) if endpoint_raw else ""
        state = dp.get("derived_state") or "Unknown"
        dp_full, port = _dp_and_port(endpoint)
        tool_count = ((dp.get("mcp") or {}).get("tool_count")) or 0

        entry: dict = {
            "endpoint": endpoint,
            "dp_full_name": dp_full,
            "port": port,
            "state": state,
            "tool_count_reported": tool_count,
            "tools": [],
            "error": None,
        }

        if state == "Broken" and not args.include_broken:
            entry["error"] = "skipped: derived_state=Broken (pass --include-broken to probe)"
            endpoints_out.append(entry)
            continue
        if not endpoint:
            entry["error"] = "missing endpoint URL in mcp health output"
            endpoints_out.append(entry)
            continue

        try:
            with McpClient(endpoint=endpoint, token=token, timeout=args.timeout) as c:
                tools = c.tools_list()
        except McpError as exc:
            entry["error"] = f"{exc.code}: {exc.message}"
            errors.append({"endpoint": endpoint, "reason": entry["error"]})
            endpoints_out.append(entry)
            continue
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"
            errors.append({"endpoint": endpoint, "reason": entry["error"]})
            endpoints_out.append(entry)
            continue

        entry["tools"] = [
            {
                "name": t.get("name"),
                "description": t.get("description"),
                "input_schema": t.get("inputSchema") or t.get("input_schema"),
            }
            for t in tools
        ]
        for t in entry["tools"]:
            fn_index.append({"dp": dp_full, "tool": t["name"]})

        endpoints_out.append(entry)

    catalogue = {
        "mesh": mesh_name,
        "summary": health.get("summary") or {},
        "discovery_stream": health.get("discovery_stream") or {},
        "endpoints": endpoints_out,
        "function_index": fn_index,
        "errors": errors,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(catalogue, indent=2))

    healthy = sum(1 for e in endpoints_out if e["state"] == "Healthy" and not e["error"])
    print(
        json.dumps(
            {
                "out": str(out_path),
                "endpoints_total": len(endpoints_out),
                "endpoints_healthy": healthy,
                "tools_indexed": len(fn_index),
                "errors": len(errors),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

"""Strict mode — discover DP MCP tools via the mesh MCP gateway multiplexer.

Source of truth is the **MCP multiplexer** (mcp-proxy-api) at ``<base>/dp/mcp/``
(or ``<base>/mcp/``). ONE MCP session yields everything strict mode needs:

  - ``proxy__getDataProductsHealth`` — per-DP derived_state / breaker (replaces
    the old ``nxd mcp health`` subprocess, Stage 1).
  - ``tools/list`` — every DP's MCP tools, namespaced ``<function>__<hash>``
    (replaces the per-DP endpoint ``tools/list`` fan-out, Stage 2).

No CLI subprocess, no per-DP dial. Output keeps the SAME catalogue shape the
downstream strict-mode scripts (``semantic_relations.py``, ``plan_validator.py``)
already consume — only the SOURCE changed. Each ``endpoints[*].endpoint`` is the
multiplexer URL and ``tools[*].name`` is the namespaced wire name, so a caller
dials the multiplexer with that wire name (``mcp_call.py`` / ``semantic_relations``
work unchanged).

Catalogue written to ``--out``:

    {
      "mesh": "<name>",
      "endpoint": "<multiplexer url>",
      "summary": {...},                       # from getDataProductsHealth
      "endpoints": [
        {"endpoint": "<multiplexer url>", "dp_full_name": "<hash>",
         "port": "", "state": "Healthy|...",
         "tools": [{"name": "<fn>__<hash>", "description": "...", "input_schema": {...}}],
         "error": null}
      ],
      "function_index": [{"dp": "<hash>", "tool": "<fn>__<hash>"}],
      "gateway_tools": ["proxy__...", ...],   # the multiplexer's own tools
      "errors": [...]
    }

NOTE on ``dp_full_name``: the multiplexer namespaces per-DP tools by an opaque
``__<hash>``, not the DP fullName. We group by that hash. To map hash→fullName,
call ``gateway_tools.py details --dp <fullName>`` or read each group's
``semantic_model`` response (which carries its own data_product). The hash is a
stable per-DP key within a session — sufficient for the validator, which matches
on ``(dp, tool)`` pairs it sees in this same catalogue.

CLI:

    python3 mcp_gateway.py --token-file /tmp/nxd.tok --out /tmp/nxd-mcp-gateway.json \
        [--endpoint <url>] [--include-broken]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mcp_http import McpClient, McpError, with_retry
from nxd_api import read_token, resolve_mesh

TOOL_HEALTH = "proxy__getDataProductsHealth"


def _proxy_endpoints(api_url: str, override: str | None) -> list[str]:
    """Candidate multiplexer URLs (mirror gateway_tools._proxy_endpoints)."""
    if override:
        return [override]
    base = api_url.rstrip("/")
    if base.endswith("/api"):
        base = base[: -len("/api")]
    return [f"{base}/dp/mcp/", f"{base}/mcp/"]


def _open(endpoints: list[str], token: str, timeout: float) -> McpClient:
    last: Exception | None = None
    for ep in endpoints:
        try:
            c = McpClient(endpoint=ep, token=token, timeout=timeout)
            c.initialize()
            return c
        except McpError as exc:
            last = exc
            if exc.code not in (404, 502, 503, 504):
                raise
        except Exception as exc:  # noqa: BLE001
            last = exc
    sys.exit(f"could not reach the MCP gateway at any of {endpoints}: {last}")


def _unwrap(result: dict[str, Any]) -> Any:
    if not isinstance(result, dict):
        return result
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    content = result.get("content")
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        joined = "\n".join(texts).strip()
        if joined:
            try:
                return json.loads(joined)
            except json.JSONDecodeError:
                return {"text": joined}
    return result


def _health_summary(c: McpClient) -> dict:
    """Call proxy__getDataProductsHealth; return its summary (best-effort)."""
    try:
        payload = _unwrap(with_retry(lambda: c.tools_call(TOOL_HEALTH, {})))
    except McpError as exc:
        return {"_health_error": f"{exc.code}: {exc.message}"}
    if isinstance(payload, dict):
        return payload.get("summary") or payload.get("data_products") and {"raw": "see health tool"} or payload
    return {}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mesh", help="Mesh name when multiple are configured")
    p.add_argument("--token-file", help="Path to a file holding the token (preferred)")
    p.add_argument("--endpoint", help="Override the multiplexer URL")
    p.add_argument("--out", required=True, help="Where to write the gateway catalogue JSON")
    p.add_argument(
        "--include-broken",
        action="store_true",
        help="(kept for compatibility; the multiplexer tools/list already excludes unhealthy DPs)",
    )
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()

    if args.token_file:
        token = read_token(args.token_file)
        api_url = "" if args.endpoint else resolve_mesh(args.mesh).api_url
        mesh_name = args.mesh or ""
    else:
        m = resolve_mesh(args.mesh)
        if not m.token:
            sys.exit("no token for the active mesh — run nxd-setup or nxd login")
        token, api_url, mesh_name = m.token, m.api_url, m.name

    endpoints = _proxy_endpoints(api_url, args.endpoint)
    c = _open(endpoints, token, args.timeout)
    multiplexer = c.endpoint
    try:
        summary = _health_summary(c)
        tools = c.tools_list()
    finally:
        c.close()

    # Group per-DP tools by their __<hash> suffix; collect the gateway's own
    # tools (proxy__/glossary__/discovery-) separately.
    groups: dict[str, list[dict]] = {}
    gateway_tools: list[str] = []
    for t in tools:
        n = t.get("name") or ""
        if "__" in n and not n.startswith(("proxy__", "glossary__", "discovery-")):
            _, _, h = n.rpartition("__")
            groups.setdefault(h, []).append(
                {
                    "name": n,
                    "description": t.get("description"),
                    "input_schema": t.get("inputSchema") or t.get("input_schema"),
                }
            )
        else:
            gateway_tools.append(n)

    endpoints_out: list[dict] = []
    fn_index: list[dict] = []
    for h, tool_list in groups.items():
        endpoints_out.append(
            {
                "endpoint": multiplexer,
                "dp_full_name": h,  # opaque per-DP hash (see module docstring)
                "port": "",
                "state": "Healthy",
                "tool_count_reported": len(tool_list),
                "tools": tool_list,
                "error": None,
            }
        )
        for t in tool_list:
            fn_index.append({"dp": h, "tool": t["name"]})

    catalogue = {
        "mesh": mesh_name,
        "endpoint": multiplexer,
        "summary": summary,
        "endpoints": endpoints_out,
        "function_index": fn_index,
        "gateway_tools": gateway_tools,
        "errors": [],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(catalogue, indent=2))

    print(
        json.dumps(
            {
                "out": str(out_path),
                "endpoint": multiplexer,
                "dp_groups": len(endpoints_out),
                "tools_indexed": len(fn_index),
                "gateway_tools": len(gateway_tools),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

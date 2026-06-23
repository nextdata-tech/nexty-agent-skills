"""MCP-first discovery / metadata / health via the mesh MCP gateway.

The mesh runs a single **MCP multiplexer** (mcp-proxy-api) that exposes, over ONE
MCP session, a set of gateway tools that return exactly the catalogue / metadata
/ health / glossary / debug information this skill used to pull from the per-DP
**REST API** (`/api/v1/data-products`, `/outputs`, `/models`) and the **CLI**
(`nxd mcp health`). Using the gateway means: one session, no REST venv on the hot
path, no CLI subprocess, no per-DP fan-out.

Gateway tools (declared in mcp-proxy-api `src/mcp/server/tools.rs`) and the
REST/CLI they replace:

    discovery-system-dp-production__list_data_products   ← list_dps.py
    proxy__get_data_product_details                      ← list_outputs.py + port_models.py
    proxy__getDataProductsHealth                         ← nxd mcp health
    glossary__get_glossary                               ← glossary REST
    proxy__getDataProductLogs / proxy__getDataProductEvents  ← debug

What the gateway CANNOT do: lease store credentials. Direct-store querying
(Snowflake/Postgres SQL, presigned-file fetch, pgvector dial) still needs the
per-DP REST `connect` path (connect_port.py + query_sql.py / fetch_file.py /
vector_search.py). Those stay as the non-MCP fallback.

Auth: handled by mcp_http (PAT → `X-Nextdata-Token`, OAuth → `Authorization:
Bearer`, keyed on token type). Pass the token via `--token-file` (the
find_mesh.py token_file) or let it resolve from the active mesh.

Endpoint: the multiplexer lives at `<base>/dp/mcp/` (this mesh) or `<base>/mcp/`,
derived from the mesh `api_url` (strip `/api`). Override with `--endpoint`.

CLI (writes JSON to --out, or stdout if omitted — none of this is secret):

    python3 gateway_tools.py list-dps [--domain D] --token-file <f>
    python3 gateway_tools.py details --dp <fullName> [--outputs] [--models] \
        [--inputs] [--promises] [--policies] --token-file <f>
    python3 gateway_tools.py health [--broken-only] --token-file <f>
    python3 gateway_tools.py glossary --name <glossary-dp> --token-file <f>
    python3 gateway_tools.py logs --dp <fullName> [--debug] --token-file <f>
    python3 gateway_tools.py events --dp <fullName> --token-file <f>
    python3 gateway_tools.py tools [--dp <fullName>] --token-file <f>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp_http import McpClient, McpError, with_retry
from nxd_api import read_token, resolve_mesh

# Gateway tool names (mcp-proxy-api src/mcp/server/tools.rs). The discovery tool
# carries an environment-specific suffix; match by prefix at runtime instead of
# hard-coding the full name.
TOOL_LIST_DPS_PREFIX = "discovery-system-dp"
TOOL_DETAILS = "proxy__get_data_product_details"
TOOL_HEALTH = "proxy__getDataProductsHealth"
TOOL_GLOSSARY = "glossary__get_glossary"
TOOL_LOGS = "proxy__getDataProductLogs"
TOOL_EVENTS = "proxy__getDataProductEvents"


def _proxy_endpoints(api_url: str, override: str | None) -> list[str]:
    """Candidate multiplexer URLs, in priority order.

    Derived from the mesh api_url by stripping a trailing ``/api``. This mesh
    serves the multiplexer at ``<base>/dp/mcp/``; the generic nxd pattern is
    ``<base>/mcp/`` (see components/docs/dp_development/mcp_tools.md). Try both.
    """
    if override:
        return [override]
    base = api_url.rstrip("/")
    if base.endswith("/api"):
        base = base[: -len("/api")]
    return [f"{base}/dp/mcp/", f"{base}/mcp/"]


def _open(endpoints: list[str], token: str, timeout: float) -> McpClient:
    """Open a session against the first multiplexer URL that initialises."""
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
    raise SystemExit(
        f"could not reach the MCP gateway at any of {endpoints}: {last}"
    )


def _unwrap(result: dict[str, Any]) -> Any:
    """Unwrap an MCP ``tools/call`` envelope to its JSON payload.

    Prefer ``structuredContent``; else stitch text blocks and try JSON; else
    return the raw envelope. Mirrors mcp_call.py / semantic_relations.py.
    """
    if not isinstance(result, dict):
        return result
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    content = result.get("content")
    if isinstance(content, list):
        texts = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        joined = "\n".join(texts).strip()
        if joined:
            try:
                return json.loads(joined)
            except json.JSONDecodeError:
                return {"text": joined}
    return result


def _call(c: McpClient, name: str, args: dict[str, Any]) -> Any:
    return _unwrap(with_retry(lambda: c.tools_call(name, args)))


def _resolve_list_dps_tool(c: McpClient) -> str:
    """Find the env-suffixed discovery tool name from a live tools/list."""
    for t in c.tools_list():
        n = t.get("name") or ""
        if n.startswith(TOOL_LIST_DPS_PREFIX) and n.endswith("list_data_products"):
            return n
    raise SystemExit(
        f"no '{TOOL_LIST_DPS_PREFIX}…list_data_products' tool on the gateway — "
        "is the discovery system DP healthy?"
    )


def _dp_tools_by_owner(c: McpClient, dp: str | None) -> dict[str, Any]:
    """Group the multiplexer's per-DP tools (``<fn>__<hash>``) by hash.

    The multiplexer namespaces each DP's MCP tools with a ``__<hash>`` suffix.
    This is the discovery the old list_outputs.py rpc-port branch + strict-mode
    Stage 2 produced — now a single tools/list. The hash is opaque, but every
    per-DP tool description is prefixed ``(data product: <fullName>, port: ...)``
    so when ``--dp`` is given we filter to the group whose descriptions name that
    DP. Without --dp we return the full grouping.
    """
    groups: dict[str, list[dict]] = {}
    gateway_tools = []
    owner: dict[str, str] = {}  # hash -> owning DP fullName (from description)
    for t in c.tools_list():
        n = t.get("name") or ""
        if "__" in n and not n.startswith(("proxy__", "glossary__", "discovery-")):
            fn, _, h = n.rpartition("__")
            desc = t.get("description") or ""
            groups.setdefault(h, []).append(
                {"wire_name": n, "function": fn, "description": desc}
            )
            m = re.search(r"data product:\s*([^,)]+)", desc)
            if m:
                owner[h] = m.group(1).strip()
        else:
            gateway_tools.append(n)
    if dp:
        groups = {h: ts for h, ts in groups.items() if owner.get(h) == dp}
        return {"per_dp_tool_groups": groups, "dp": dp}
    return {"per_dp_tool_groups": groups, "gateway_tools": gateway_tools}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=[
        "list-dps", "details", "health", "glossary", "logs", "events", "tools",
    ])
    ap.add_argument("--dp", help="Data Product fullName (details/logs/events)")
    ap.add_argument("--domain", help="domain filter (list-dps)")
    ap.add_argument("--name", help="glossary DP name (glossary)")
    ap.add_argument("--outputs", action="store_true")
    ap.add_argument("--models", action="store_true", help="include semantic models (details)")
    ap.add_argument("--inputs", action="store_true")
    ap.add_argument("--promises", action="store_true")
    ap.add_argument("--policies", action="store_true")
    ap.add_argument("--broken-only", action="store_true", help="health: Broken DPs only")
    ap.add_argument("--debug", action="store_true", help="logs: include DEBUG lines")
    ap.add_argument("--mesh", help="mesh name when several are configured")
    ap.add_argument("--token-file", help="file holding the bearer/PAT token (preferred)")
    ap.add_argument("--endpoint", help="override the multiplexer URL")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    ap.add_argument("--timeout", type=float, default=40.0)
    args = ap.parse_args()

    if args.token_file:
        token = read_token(args.token_file)
        api_url = resolve_mesh(args.mesh).api_url if not args.endpoint else ""
    else:
        m = resolve_mesh(args.mesh)
        if not m.token:
            sys.exit("no token for the active mesh — run nxd-setup / nxd login, or pass --token-file")
        token = m.token
        api_url = m.api_url

    endpoints = _proxy_endpoints(api_url, args.endpoint)

    c = _open(endpoints, token, args.timeout)
    try:
        if args.command == "list-dps":
            tool = _resolve_list_dps_tool(c)
            call_args: dict[str, Any] = {}
            if args.domain:
                call_args["filter_domain"] = args.domain
            payload = _call(c, tool, call_args)
        elif args.command == "details":
            if not args.dp:
                sys.exit("details requires --dp")
            payload = _call(c, TOOL_DETAILS, {
                "dataProduct": args.dp,
                "includeOutputs": args.outputs,
                "includeSemanticModels": args.models,
                "includeInputs": args.inputs,
                "includePromises": args.promises,
                "includePolicies": args.policies,
            })
        elif args.command == "health":
            payload = _call(c, TOOL_HEALTH, {"filter_broken_only": args.broken_only})
        elif args.command == "glossary":
            if not args.name:
                sys.exit("glossary requires --name")
            payload = _call(c, TOOL_GLOSSARY, {"glossary": args.name})
        elif args.command == "logs":
            if not args.dp:
                sys.exit("logs requires --dp")
            payload = _call(c, TOOL_LOGS, {"data_product": args.dp, "debug": args.debug})
        elif args.command == "events":
            if not args.dp:
                sys.exit("events requires --dp")
            payload = _call(c, TOOL_EVENTS, {"data_product": args.dp})
        elif args.command == "tools":
            payload = _dp_tools_by_owner(c, args.dp)
        else:  # pragma: no cover
            sys.exit(f"unknown command {args.command}")
    finally:
        c.close()

    text = json.dumps(payload, indent=2, default=str)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(json.dumps({"out": str(out), "command": args.command}))
    else:
        print(text)


if __name__ == "__main__":
    main()

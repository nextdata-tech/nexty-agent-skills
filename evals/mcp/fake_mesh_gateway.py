"""Tiny authenticated mesh MCP gateway proxy for semantic fixture cells.

The gateway exposes the mesh-level ``/dp/mcp/`` surface and forwards one
member DP's tools to ``semantic_server``. It deliberately implements only the
Streamable-HTTP operations used by nxd-query-data-product.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit


def _decode_response(raw: bytes, content_type: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if "text/event-stream" in content_type.lower():
        result: dict[str, Any] = {}
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    result = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        return result
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


class Gateway:
    def __init__(self, upstream: str, token: str, dp: str, catalog: dict[str, Any] | None = None):
        # FastMCP's HTTP route redirects /mcp/ to /mcp. urllib does not
        # preserve a POST body across that redirect, so target the canonical
        # no-trailing-slash route directly.
        self.upstream = upstream.rstrip("/")
        self.token = token
        self.dp = dp
        self.catalog = catalog or {}
        upstream_parts = urlsplit(upstream).path.rstrip("/").split("/")
        self.rpc_port = upstream_parts[-2] if upstream_parts[-1] == "mcp" else upstream_parts[-1]
        self.tool_hash = base64.b32encode(
            hashlib.sha256(f"{dp}__{self.rpc_port}".encode()).digest()
        ).decode("ascii").lower()[:10]
        self.sessions: dict[str, str] = {}
        self.lock = threading.Lock()

    def _builtins(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "discovery-system-dp-production__list_data_products",
                "description": "List data products in the mesh",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "proxy__get_data_product_details",
                "description": "Get details for a data product",
                "inputSchema": {"type": "object", "properties": {"dataProduct": {"type": "string"}}},
            },
        ]

    def _builtin_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if name == "discovery-system-dp-production__list_data_products":
            return {"data_products": [{
                "fullName": self.dp, "name": self.dp,
                "semantic_models": self.catalog.get("list_models", []),
            }]}
        if name == "proxy__get_data_product_details":
            if arguments.get("dataProduct") != self.dp:
                return {"error": f"unknown data product: {arguments.get('dataProduct', '')}"}
            details = self.catalog.get("describe_model", {})
            return {
                "fullName": self.dp, "name": self.dp, "rpc_port": self.rpc_port,
                "semantic_models": list(details.values()) if isinstance(details, dict) else [],
            }
        return None

    @staticmethod
    def _rpc_error(body: dict[str, Any], code: int, message: str) -> bytes:
        return json.dumps({
            "jsonrpc": "2.0", "id": body.get("id"),
            "error": {"code": code, "message": message},
        }).encode()

    def request(self, body: dict[str, Any], upstream_session: str | None = None):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if upstream_session:
            headers["Mcp-Session-Id"] = upstream_session
        request = urllib.request.Request(
            self.upstream, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read()
                return response.status, response.headers.get("Content-Type", "application/json"), raw, response.headers.get("Mcp-Session-Id")
        except urllib.error.HTTPError as exc:
            return exc.code, "application/json", exc.read(), None

    def handle(self, body: dict[str, Any], session_id: str | None):
        method = body.get("method")
        if method == "initialize":
            status, ctype, raw, upstream_session = self.request(body)
            if status >= 400 or not upstream_session:
                return status if status >= 400 else 502, ctype, raw, None
            proxy_session = secrets.token_urlsafe(24)
            with self.lock:
                self.sessions[proxy_session] = upstream_session
            return status, ctype, raw, proxy_session

        with self.lock:
            upstream_session = self.sessions.get(session_id or "")
        if not upstream_session:
            return 400, "application/json", self._rpc_error(body, -32000, "unknown MCP session"), None

        forwarded = dict(body)
        params = forwarded.get("params")
        if isinstance(params, dict) and method == "tools/call":
            name = params.get("name", "")
            if isinstance(name, str):
                builtin = self._builtin_call(name, params.get("arguments") or {})
                if builtin is not None:
                    response = {"jsonrpc": "2.0", "id": body.get("id"), "result": {
                        "content": [{"type": "text", "text": json.dumps(builtin)}],
                        "structuredContent": builtin,
                    }}
                    return 200, "application/json", json.dumps(response).encode(), session_id
            function, separator, suffix = name.rpartition("__") if isinstance(name, str) else ("", "", "")
            if not separator or suffix != self.tool_hash:
                return 200, "application/json", self._rpc_error(body, -32601, f"Unknown tool: {name}"), session_id
            params = dict(params)
            params["name"] = function
            forwarded["params"] = params

        status, ctype, raw, _ = self.request(forwarded, upstream_session)
        if status < 400 and method == "tools/list":
            response = _decode_response(raw, ctype)
            result = response.get("result")
            tools = result.get("tools") if isinstance(result, dict) else None
            if isinstance(tools, list):
                for tool in tools:
                    if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                        tool["name"] = f"{tool['name']}__{self.tool_hash}"
                        description = str(tool.get("description", ""))
                        tool["description"] = f"(data product: {self.dp}, port: {self.rpc_port}) {description}"
                tools.extend(self._builtins())
                raw = json.dumps(response).encode()
                ctype = "application/json"
        return status, ctype, raw, session_id


def make_handler(gateway: Gateway, path: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            if urlsplit(self.path).path.rstrip("/") != path.rstrip("/"):
                self.send_error(404)
                return
            supplied = self.headers.get("X-Nextdata-Token", "")
            if not supplied:
                self.send_error(401, "missing X-Nextdata-Token")
                return
            if not hmac.compare_digest(supplied, gateway.token):
                self.send_error(403, "invalid X-Nextdata-Token")
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                if not isinstance(body, dict):
                    raise ValueError("JSON-RPC request must be an object")
            except (json.JSONDecodeError, ValueError):
                self.send_error(400, "invalid JSON-RPC request")
                return
            status, ctype, raw, session = gateway.handle(body, self.headers.get("Mcp-Session-Id"))
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            if session:
                self.send_header("Mcp-Session-Id", session)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def log_message(self, _format, *_args):
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--path", default="/dp/mcp/")
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--dp", required=True)
    parser.add_argument("--catalog", required=True)
    args = parser.parse_args()
    import os

    token = os.environ.get("NEXTY_SEMANTIC_GATEWAY_TOKEN", "")
    if not token:
        parser.error("NEXTY_SEMANTIC_GATEWAY_TOKEN is required")
    with open(args.catalog, encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    gateway = Gateway(args.upstream, token, args.dp, catalog)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(gateway, args.path))
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Minimal MCP Streamable-HTTP client used by the strict-mode scripts.

The platform exposes per-DP MCP servers behind a proxy at
``https://<dp-host>/<dp>/rpcs/<port>/mcp/``. Streamable HTTP works as:

1. ``POST /mcp/`` ``initialize`` → 200 with ``Mcp-Session-Id`` response header.
2. ``POST /mcp/`` ``notifications/initialized`` (no id) → 202 ack.
3. ``POST /mcp/`` ``tools/list`` / ``tools/call`` with the same session id.

Auth: bearer token from ``~/.nxd/tokens.json`` (the file ``nxd login`` writes).
The mesh registry entry's auth/install host picks the right token; the proxy
shares a parent domain with the mesh API so the same token applies.

Use via:

    from mcp_http import McpClient
    with McpClient(endpoint_url, token) as c:
        tools = c.tools_list()
        result = c.tools_call("<tool-name>", {"<key>": "<value>"})
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import requests


_PROTOCOL_VERSION = "2025-06-18"
_CLIENT = {"name": "nxd-data-product-query", "version": "0.1.0"}


def normalise_endpoint(endpoint: str) -> str:
    """Flip ``http://`` → ``https://`` and ensure trailing slash.

    ``nxd mcp health`` reports endpoints as ``http://``; the proxy speaks
    HTTPS only. The path must end with ``/`` for the proxy to route MCP
    correctly."""
    if endpoint.startswith("http://"):
        endpoint = "https://" + endpoint[len("http://"):]
    if not endpoint.endswith("/"):
        endpoint += "/"
    return endpoint


@dataclass
class McpError(Exception):
    code: int
    message: str
    endpoint: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"MCP {self.code} at {self.endpoint}: {self.message}"


@dataclass
class McpClient:
    endpoint: str
    token: str
    timeout: float = 30.0
    session_id: str | None = field(default=None, init=False)
    _session: requests.Session = field(default_factory=requests.Session, init=False)
    _next_id: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        self.endpoint = normalise_endpoint(self.endpoint)

    # --- lifecycle ----------------------------------------------------------

    def __enter__(self) -> "McpClient":
        self.initialize()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def initialize(self) -> dict[str, Any]:
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": _CLIENT,
            },
        }
        self._next_id += 1
        r = self._session.post(
            self.endpoint,
            headers=self._headers(),
            data=json.dumps(body),
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise McpError(r.status_code, r.text[:500], self.endpoint)
        sid = r.headers.get("mcp-session-id") or r.headers.get("Mcp-Session-Id")
        if not sid:
            raise McpError(500, "no Mcp-Session-Id header on initialize response", self.endpoint)
        self.session_id = sid
        result = _parse_jsonrpc_response(r).get("result") or {}
        self._post_notification("notifications/initialized", {})
        return result

    def close(self) -> None:
        self._session.close()

    # --- calls --------------------------------------------------------------

    def tools_list(self) -> list[dict[str, Any]]:
        result = self._rpc("tools/list", {})
        return list(result.get("tools") or [])

    def tools_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._rpc("tools/call", {"name": name, "arguments": arguments})

    # --- internals ----------------------------------------------------------

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.session_id:
            raise McpError(500, "session not initialised", self.endpoint)
        body = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        self._next_id += 1
        r = self._session.post(
            self.endpoint,
            headers=self._headers(include_session=True),
            data=json.dumps(body),
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise McpError(r.status_code, r.text[:500], self.endpoint)
        parsed = _parse_jsonrpc_response(r)
        if "error" in parsed:
            err = parsed["error"]
            raise McpError(int(err.get("code", 500)), str(err.get("message", "unknown")), self.endpoint)
        return parsed.get("result") or {}

    def _post_notification(self, method: str, params: dict[str, Any]) -> None:
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        r = self._session.post(
            self.endpoint,
            headers=self._headers(include_session=True),
            data=json.dumps(body),
            timeout=self.timeout,
        )
        if r.status_code >= 400 and r.status_code != 202:
            raise McpError(r.status_code, r.text[:500], self.endpoint)

    def _headers(self, *, include_session: bool = False) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if include_session and self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h


def _parse_jsonrpc_response(r: requests.Response) -> dict[str, Any]:
    """The proxy sometimes returns ``text/event-stream`` for in-flight tool
    calls and plain JSON for everything else. Handle both shapes."""
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "text/event-stream" in ctype:
        # SSE: walk frames; the final ``data:`` line carries the response.
        last: dict[str, Any] = {}
        for line in r.text.splitlines():
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
                if payload and payload != "[DONE]":
                    try:
                        last = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
        return last
    return r.json()


def call_tool_one_shot(
    endpoint: str,
    token: str,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Convenience: open a session, call one tool, close. Returns the tool result."""
    with McpClient(endpoint=endpoint, token=token, timeout=timeout) as c:
        return c.tools_call(name, arguments or {})


# Small backoff for transient 503s from cold MCP servers.
def with_retry(fn, *, attempts: int = 3, backoff: float = 1.0):  # pragma: no cover - thin wrapper
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except McpError as exc:
            last = exc
            if exc.code not in (502, 503, 504):
                raise
            time.sleep(backoff * (2 ** i))
    assert last is not None
    raise last

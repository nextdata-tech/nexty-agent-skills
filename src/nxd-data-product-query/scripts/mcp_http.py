"""Minimal MCP Streamable-HTTP client used by the strict-mode scripts.

The platform exposes per-DP MCP servers behind a proxy at
``https://<dp-host>/<dp>/rpcs/<port>/mcp/``. Streamable HTTP works as:

1. ``POST /mcp/`` ``initialize`` → 200 with ``Mcp-Session-Id`` response header.
2. ``POST /mcp/`` ``notifications/initialized`` (no id) → 202 ack.
3. ``POST /mcp/`` ``tools/list`` / ``tools/call`` with the same session id.

Auth: the wire header depends on the token TYPE (see ``_auth_header``). A PAT
(``nxdpat_…``, the token ``nxd mcp config`` / ``nxd login`` provision) goes in
``X-Nextdata-Token`` — the documented MCP auth; an OAuth session token goes in
``Authorization: Bearer``. The two are mutually exclusive on the gateway.

Use via:

    from mcp_http import McpClient
    with McpClient(endpoint_url, token) as c:
        tools = c.tools_list()
        result = c.tools_call("<tool-name>", {"<key>": "<value>"})
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests


_PROTOCOL_VERSION = "2025-06-18"
_CLIENT = {"name": "nxd-data-product-query", "version": "0.1.0"}


def _default_verify() -> bool | str:
    """Resolve TLS verification for the MCP session.

    LOCAL clusters (e.g. ``nxd.nxd.local``) serve a self-signed CA, so default
    ``requests`` verification fails with ``CERTIFICATE_VERIFY_FAILED``. Honor the
    standard env vars so a caller can point at the cluster CA bundle
    (``shared/charts/nxd/localCerts/nxdCA.crt``) without code changes:

        REQUESTS_CA_BUNDLE=<ca>  (or)  SSL_CERT_FILE=<ca>

    Returns the bundle path if either is set + exists, else True (system store).
    Set ``NXD_MCP_INSECURE=1`` to skip verification entirely (local dev only).
    """
    if os.environ.get("NXD_MCP_INSECURE") == "1":
        return False
    for var in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "NXD_CA_BUNDLE"):
        path = os.environ.get(var)
        if path and os.path.exists(path):
            return path
    return True


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


def _auth_header(token: str) -> dict[str, str]:
    """Pick the right auth header for the token TYPE — the wire header decides
    which token the gateway accepts, and the two are mutually exclusive.

    Verified live against the mesh MCP gateway (``/dp/mcp``) and documented in
    nxd ``components/docs/basics/using_mcp.md`` /
    ``components/docs/dp_development/mcp_tools.md`` (every MCP example uses
    ``X-Nextdata-Token: <PAT>``):

        header                 PAT (nxdpat_…)   OAuth session token
        X-Nextdata-Token       200              401
        Authorization: Bearer  401              200

    Sending BOTH headers 401s. So send exactly one, keyed on the token kind:
      - PAT (``nxdpat_`` prefix, the token ``nxd mcp config`` / ``nxd login``
        provision) → ``X-Nextdata-Token`` — the documented MCP auth.
      - anything else (an OAuth JWT session token) → ``Authorization: Bearer``.
    """
    if token.startswith("nxdpat_"):
        return {"X-Nextdata-Token": token}
    return {"Authorization": f"Bearer {token}"}


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
    # TLS verification: bundle path / True (system store) / False (insecure).
    # Defaults from REQUESTS_CA_BUNDLE / SSL_CERT_FILE / NXD_CA_BUNDLE so local
    # self-signed clusters work; callers may override explicitly.
    verify: bool | str | None = None
    session_id: str | None = field(default=None, init=False)
    _session: requests.Session = field(default_factory=requests.Session, init=False)
    _next_id: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        self.endpoint = normalise_endpoint(self.endpoint)
        self._session.verify = _default_verify() if self.verify is None else self.verify

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
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        h.update(_auth_header(self.token))
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


# Small exponential backoff for transient 5xx from cold MCP servers
# (proxy spins up the DP container on first hit; subsequent calls are warm).
# Retries only on 502 / 503 / 504; any other ``McpError`` raises through.
def with_retry(fn, *, attempts: int = 3, backoff: float = 0.5):
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


def call_tool_one_shot(
    endpoint: str,
    token: str,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    timeout: float = 30.0,
    retry_attempts: int = 3,
    verify: bool | str | None = None,
) -> dict[str, Any]:
    """Convenience: open a session, call one tool, close. Returns the tool result.

    The ``tools/call`` invocation is wrapped in ``with_retry`` so transient
    5xx from a cold DP proxy auto-recover. Session ``initialize`` itself
    is not retried — that fails fast for clearer error surface.

    ``verify`` overrides TLS verification (CA bundle path / False to skip);
    defaults from the standard CA-bundle env vars (see ``_default_verify``)."""
    with McpClient(endpoint=endpoint, token=token, timeout=timeout, verify=verify) as c:
        return with_retry(lambda: c.tools_call(name, arguments or {}), attempts=retry_attempts)

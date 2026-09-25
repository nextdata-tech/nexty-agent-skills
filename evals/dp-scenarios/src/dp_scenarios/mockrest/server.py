"""Real HTTP lifecycle and request dispatch for configurable mock sources.

The data and control applications bind to different sockets.  Data requests
are counted before any configured behavior runs, while capability, state, and
counter operations are available only on the control socket.  Startup probes
the first successful configured data route and the control health URL over HTTP,
then clears those probe events before returning, so a caller never receives a
log-line approximation of readiness or a polluted call-count oracle.  Dataset
state is snapshotted before injected latency, making a request's result depend
on the state at dispatch rather than on when its sleep happens to finish.

The smoke tier intentionally omits tombstone records, nested PII objects carrying
sentinel values, and an FX route with a missing weekend date.  A future fidelity
tier covering deletion, privacy handling, and calendar/FX completeness will need
those capabilities.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Mapping

from aiohttp import ClientSession, ClientTimeout, web

from .behaviors import (
    BehaviorError,
    compile_path,
    cursor_offsets,
    is_rate_limited,
    match_path,
    paginate,
    route_specificity,
    select_children,
    select_item,
    satisfy_header,
    has_nonblank_user_agent,
)
from .capability import CapabilityManifest
from .config import ConfigError, ResponseSpec, RouteConfig, ScenarioConfig, load_config
from .counters import RequestCounters


CONTROL_SECRET_HEADER = "X-Source-Control"
UNMATCHED_ROUTE = "__unmatched__"
NEUTRAL_SERVER_HEADER = "source"


def _error(status: int, message: str) -> web.Response:
    """Return a stable error body without disclosing hidden route metadata."""

    return web.json_response({"error": message}, status=status)


def _csv_response(records: Any, *, status: int = 200) -> web.Response:
    if not isinstance(records, list) or not all(isinstance(record, Mapping) for record in records):
        return _error(500, "configured CSV response is not a collection of records")
    fieldnames: list[str] = []
    for record in records:
        for key in record:
            if key not in fieldnames:
                fieldnames.append(str(key))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    if fieldnames:
        writer.writeheader()
        writer.writerows(records)
    return web.Response(text=output.getvalue(), status=status, content_type="text/csv")


@web.middleware
async def _neutral_server_header(
    request: web.Request, handler: Any
) -> web.StreamResponse:
    """Keep the implementation stack out of every HTTP response."""

    response = await handler(request)
    response.headers["Server"] = NEUTRAL_SERVER_HEADER
    return response


@dataclass(frozen=True)
class ServerAddresses:
    """The selected addresses after ephemeral ports have been bound."""

    data_host: str
    data_port: int
    control_host: str
    control_port: int


async def wait_until_ready(
    data_url: str,
    control_url: str,
    *,
    data_probe_path: str,
    control_health_path: str = "/health",
    data_headers: Mapping[str, str] | None = None,
    control_headers: Mapping[str, str] | None = None,
    deadline: float = 30.0,
    probe_timeout: float = 5.0,
    max_backoff: float = 0.25,
) -> None:
    """Probe the configured data route and control health until a deadline."""

    if not data_probe_path.startswith("/"):
        raise ValueError("data_probe_path must be an absolute path")
    if deadline <= 0:
        raise ValueError("deadline must be positive")
    if probe_timeout <= 0:
        raise ValueError("probe_timeout must be positive")
    if max_backoff < 0:
        raise ValueError("max_backoff must not be negative")
    timeout = ClientTimeout(total=probe_timeout)
    started = time.monotonic()
    deadline_at = started + deadline
    backoff = 0.01
    async with ClientSession(timeout=timeout) as session:
        last_error: Exception | None = None
        while True:
            if time.monotonic() >= deadline_at:
                elapsed = time.monotonic() - started
                raise RuntimeError(
                    "mock-rest server did not answer configured data and control probes "
                    f"within {elapsed:.3f}s; data probe path={data_probe_path}; "
                    f"last probe error={last_error}"
                ) from last_error
            try:
                async with session.get(
                    data_url.rstrip("/") + data_probe_path,
                    headers=data_headers,
                ) as data_response:
                    if not 200 <= data_response.status < 300:
                        raise RuntimeError(f"data probe returned HTTP {data_response.status}")
                    await data_response.read()
                async with session.get(
                    control_url.rstrip("/") + control_health_path,
                    headers=control_headers,
                ) as control_response:
                    if control_response.status != 200:
                        raise RuntimeError(f"control health returned HTTP {control_response.status}")
                    await control_response.read()
                return
            except Exception as exc:  # socket startup races are expected before a successful probe
                last_error = exc
                remaining = deadline_at - time.monotonic()
                if remaining <= 0:
                    continue
                await asyncio.sleep(min(backoff, remaining))
                backoff = min(max_backoff, backoff * 2) if max_backoff else 0


class MockRestServer:
    """An ephemeral-port data/control HTTP server for one validated scenario."""

    def __init__(
        self,
        config: ScenarioConfig | str | Mapping[str, Any],
        control_secret: str | None = None,
    ) -> None:
        self.config = config if isinstance(config, ScenarioConfig) else load_config(config)
        self.counters = RequestCounters()
        self.capability = CapabilityManifest.from_mapping(self.config.capability)
        self._control_secret = (
            secrets.token_urlsafe(32) if control_secret is None else control_secret
        )
        self._current_states: dict[str, str] = {}
        for route in self.config.routes:
            if route.states and route.state_family is not None:
                previous = self._current_states.setdefault(route.state_family, route.initial_state)
                if previous not in route.states:
                    raise ConfigError(
                        f"routes for state family {route.state_family} have incompatible initial states"
                    )
        if not self.capability.endpoints:
            self.capability = self._manifest_from_routes()
        self._remaining_requests = (
            self.config.auth.initial_requests if self.config.auth is not None else None
        )
        self._state_lock = asyncio.Lock()
        self._data_runner: web.AppRunner | None = None
        self._control_runner: web.AppRunner | None = None
        self._data_site: web.TCPSite | None = None
        self._control_site: web.TCPSite | None = None
        self._routes = sorted(self.config.routes, key=lambda route: route_specificity(route.path))
        self._patterns = {id(route): compile_path(route.path) for route in self._routes}
        self._cursor_maps: dict[tuple[str, str], dict[str, int]] = {}
        self._addresses: ServerAddresses | None = None

    @property
    def control_secret(self) -> str:
        """Return the in-memory control credential for the owning harness."""

        return self._control_secret

    @property
    def control_headers(self) -> Mapping[str, str]:
        """Return the header required for authenticated control-port requests."""

        return {CONTROL_SECRET_HEADER: self._control_secret}

    def _manifest_from_routes(self) -> CapabilityManifest:
        endpoints: dict[str, dict[str, list[int]]] = {}
        for route in self.config.routes:
            statuses = [route.status]
            if route.write_forbidden:
                statuses = [403]
            endpoints.setdefault(route.path, {})[route.method] = statuses
        return CapabilityManifest.from_mapping(
            {"metrics": {}, "endpoints": endpoints}
        )

    @property
    def addresses(self) -> ServerAddresses:
        """Return bound addresses, raising if startup has not completed."""

        if self._addresses is None:
            raise RuntimeError("mock-rest server has not started")
        return self._addresses

    @property
    def data_host(self) -> str:
        return self.addresses.data_host

    @property
    def data_port(self) -> int:
        return self.addresses.data_port

    @property
    def control_host(self) -> str:
        return self.addresses.control_host

    @property
    def control_port(self) -> int:
        return self.addresses.control_port

    @property
    def data_url(self) -> str:
        return f"http://{self.data_host}:{self.data_port}"

    @property
    def control_url(self) -> str:
        return f"http://{self.control_host}:{self.control_port}"

    @property
    def control_paths(self) -> Mapping[str, str]:
        """Expose control paths to graders without serving them on data."""

        control = self.config.control
        return {
            "health": control.health_path,
            "counters": control.counters_path,
            "reset": control.reset_path,
            "capability": control.capability_path,
            "state": control.state_path,
        }

    def _readiness_probe(self) -> tuple[str, Mapping[str, str]]:
        """Choose a parameter-free successful GET route when one is available."""

        candidates = [
            route
            for route in self.config.routes
            if route.method == "GET"
            and 200 <= route.status < 300
            and not route.write_forbidden
            and (not route.required_scopes or self._authorized(route))
            and re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", route.path) is None
        ]
        candidates.extend(
            route
            for route in self.config.routes
            if route.method == "GET"
            and 200 <= route.status < 300
            and not route.write_forbidden
            and (not route.required_scopes or self._authorized(route))
            and re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", route.path) is not None
        )
        for route in candidates:
            candidate = "probe"
            spec = route.response
            if spec is None and route.states:
                spec = route.states[route.initial_state]
            if spec is not None and isinstance(spec.data, list) and spec.data:
                first = spec.data[0]
                if isinstance(first, Mapping) and first.get(spec.item_key) is not None:
                    candidate = str(first[spec.item_key])
            path = re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*\}", candidate, route.path)
            headers: dict[str, str] = {}
            if route.require_user_agent:
                headers["User-Agent"] = "readiness-probe"
            if route.required_header is not None:
                headers[route.required_header.name] = route.required_header.value
            if route.auth_required:
                assert self.config.auth is not None
                auth = self.config.auth
                headers[auth.header] = f"{auth.scheme} {auth.token}"
            return path, headers
        raise ConfigError("scenario needs a GET route with a successful 2xx status for readiness")

    async def start(self, *, wait_for_ready: bool = True) -> "MockRestServer":
        """Bind both ports and optionally wait until both configured probes answer."""

        if any(
            spec.deferred
            for route in self.config.routes
            for spec in (([route.response] if route.response is not None else []) + list(route.states.values()))
        ):
            raise ConfigError(
                "mock-rest cannot start with unresolved fixture_source responses; "
                "resolve the fixture sources before starting the server"
            )
        if self._addresses is not None:
            return self
        data_app = web.Application(middlewares=[_neutral_server_header])
        control_app = web.Application(middlewares=[_neutral_server_header])
        data_app.router.add_route("*", "/{tail:.*}", self._data_handler)
        control_app.router.add_route("*", "/{tail:.*}", self._control_handler)
        self._data_runner = web.AppRunner(data_app, access_log=None)
        self._control_runner = web.AppRunner(control_app, access_log=None)
        try:
            await self._data_runner.setup()
            await self._control_runner.setup()
            self._data_site = web.TCPSite(
                self._data_runner,
                self.config.data_host,
                self.config.data_port,
                reuse_address=True,
            )
            self._control_site = web.TCPSite(
                self._control_runner,
                self.config.control_host,
                self.config.control_port,
                reuse_address=True,
            )
            await self._data_site.start()
            await self._control_site.start()
            data_port = _site_port(self._data_site)
            control_port = _site_port(self._control_site)
            self._addresses = ServerAddresses(
                self.config.data_host,
                data_port,
                self.config.control_host,
                control_port,
            )
            if wait_for_ready:
                data_path, data_headers = self._readiness_probe()
                await wait_until_ready(
                    self.data_url,
                    self.control_url,
                    data_probe_path=data_path,
                    data_headers=data_headers,
                    control_health_path=self.config.control.health_path,
                    control_headers=self.control_headers,
                )
                self.counters.reset()
                if self.config.auth is not None:
                    async with self._state_lock:
                        self._remaining_requests = self.config.auth.initial_requests
            return self
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Close both listeners and release their ports."""

        self._addresses = None
        if self._data_runner is not None:
            await self._data_runner.cleanup()
        if self._control_runner is not None:
            await self._control_runner.cleanup()
        self._data_runner = None
        self._control_runner = None
        self._data_site = None
        self._control_site = None

    async def snapshot_runtime_state(self) -> dict[str, Any]:
        """Capture the non-secret state needed to continue this source."""

        async with self._state_lock:
            return {
                "schema": 1,
                "remaining_requests": self._remaining_requests,
                "current_states": dict(self._current_states),
                "counters": self.counters.snapshot(),
            }

    async def restore_runtime_state(self, state: Mapping[str, Any]) -> None:
        """Restore a validated source snapshot after the readiness probe."""

        if not isinstance(state, Mapping) or set(state) != {
            "schema",
            "remaining_requests",
            "current_states",
            "counters",
        }:
            raise ValueError("mock source runtime state has an invalid shape")
        if state["schema"] != 1:
            raise ValueError("mock source runtime state has an unsupported schema")
        remaining = state["remaining_requests"]
        if remaining is not None and (
            isinstance(remaining, bool)
            or not isinstance(remaining, int)
            or remaining < 0
        ):
            raise ValueError("mock source runtime state has an invalid auth budget")
        if self.config.auth is None:
            if remaining is not None:
                raise ValueError("mock source runtime state has an auth budget without auth")
        elif remaining is None or remaining > self.config.auth.initial_requests:
            raise ValueError("mock source runtime state has an invalid auth budget")

        current_states = state["current_states"]
        if not isinstance(current_states, Mapping):
            raise ValueError("mock source runtime state has invalid route state")
        expected_families = {
            route.state_family
            for route in self.config.routes
            if route.states and route.state_family is not None
        }
        if set(current_states) != expected_families:
            raise ValueError("mock source runtime state does not match route state families")
        for family, selected in current_states.items():
            if not isinstance(family, str) or not isinstance(selected, str):
                raise ValueError("mock source runtime state has invalid route state")
            family_routes = [
                route for route in self.config.routes if route.state_family == family
            ]
            if not family_routes or any(selected not in route.states for route in family_routes):
                raise ValueError("mock source runtime state has an unknown route state")

        counters = state["counters"]
        if not isinstance(counters, Mapping):
            raise ValueError("mock source runtime state has invalid counters")
        async with self._state_lock:
            self._remaining_requests = remaining
            self._current_states = dict(current_states)
            self._cursor_maps.clear()
            self.counters.restore_snapshot(counters)

    async def __aenter__(self) -> "MockRestServer":
        return await self.start()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.stop()

    async def _data_handler(self, request: web.Request) -> web.StreamResponse:
        path = request.path
        if self.config.auth is not None and path == self.config.auth.refresh_path:
            request_number = self.counters.record(path, request.method, request.headers)
            if request.method not in {"GET", "POST"}:
                response = _error(405, "method not allowed")
                self.counters.record_response(path, request_number, response.status)
                return response
            async with self._state_lock:
                self._remaining_requests = self.config.auth.initial_requests
            response = web.json_response({"status": "refreshed"})
            self.counters.record_response(path, request_number, response.status)
            return response
        if path in self.config.docs and request.method == "GET":
            page = self.config.docs[path]
            return web.Response(text=page.body, content_type=page.content_type)

        match = self._find_route(request.method, path)
        if match is None:
            request_number = self.counters.record(UNMATCHED_ROUTE, request.method, request.headers)
            response = _error(404, "not found")
            self.counters.record_response(UNMATCHED_ROUTE, request_number, response.status)
            return response
        route, path_parameters = match
        request_number = self.counters.record(
            route.path,
            request.method,
            request.headers,
        )

        def finish(response: web.StreamResponse, *, page: Any = None) -> web.StreamResponse:
            self.counters.record_response(route.path, request_number, response.status)
            if page is not None:
                self.counters.record_page_observation(
                    rows=page.records,
                    next_cursor=page.next_cursor,
                    status=response.status,
                )
            return response

        state_snapshot = dict(self._current_states)
        if route.latency_ms:
            await asyncio.sleep(route.latency_ms / 1000.0)
        if not 200 <= route.status < 300:
            return finish(_error(route.status, _status_message(route.status)))
        if route.write_forbidden:
            return finish(_error(403, "write forbidden"))
        if route.require_user_agent and not has_nonblank_user_agent(request.headers):
            return finish(_error(403, "forbidden"))
        if route.required_header is not None and not satisfy_header(request.headers, route.required_header):
            return finish(_error(403, "forbidden"))
        if is_rate_limited(request_number, route.rate_limit_every):
            return finish(_error(429, "rate limited"))
        if route.auth_required and not await self._authenticate(request):
            return finish(_error(401, "unauthorized"))
        if route.required_scopes and not self._authorized(route):
            return finish(_error(403, "forbidden"))

        try:
            payload, spec = self._route_payload(route, state_snapshot)
            if route.fanout is not None:
                parent_value = path_parameters.get("parent_id")
                if parent_value is None:
                    parent_value = next(iter(path_parameters.values()))
                payload = select_children(payload, fanout=route.fanout, parent_value=parent_value)
            item_parameter = _item_parameter(route.path, path_parameters)
            if item_parameter is not None:
                item = select_item(payload, item_key=spec.item_key, item_value=item_parameter)
                if item is None:
                    return finish(_error(404, "not found"))
                payload = item
            if route.pagination is not None:
                if not isinstance(payload, list):
                    return finish(_error(500, "configured pagination response is not a collection"))
                cursor = request.query.get(route.pagination.cursor_param)
                state_key = _state_key(route, state_snapshot)
                map_key = (route.path, state_key)
                valid = self._cursor_maps.setdefault(
                    map_key,
                    cursor_offsets(
                        route.path,
                        len(payload),
                        route.pagination.page_size,
                        state_key,
                    ),
                )
                page = paginate(
                    payload,
                    cursor=cursor,
                    config=route.pagination,
                    route=route.path,
                    valid_cursors=valid,
                    state=state_key,
                )
                payload = {
                    route.pagination.items_field: page.records,
                    route.pagination.cursor_field: page.next_cursor,
                }
                response = web.json_response(payload, status=route.status)
                return finish(response, page=page)
            if spec.format == "csv":
                return finish(_csv_response(payload, status=route.status))
            if (
                item_parameter is None
                and route.fanout is None
                and spec.serialized_json is not None
            ):
                return finish(
                    web.Response(
                        body=spec.serialized_json,
                        status=route.status,
                        content_type="application/json",
                    )
                )
            return finish(web.json_response(payload, status=route.status))
        except BehaviorError as exc:
            return finish(_error(400, str(exc)))

    async def _authenticate(self, request: web.Request) -> bool:
        auth = self.config.auth
        if auth is None:
            return False
        supplied = request.headers.get(auth.header, "")
        expected = f"{auth.scheme} {auth.token}"
        if supplied != expected:
            return False
        async with self._state_lock:
            if self._remaining_requests is None or self._remaining_requests <= 0:
                return False
            self._remaining_requests -= 1
            return True

    def _authorized(self, route: RouteConfig) -> bool:
        """Return whether the synthetic authenticated identity has each scope."""

        auth = self.config.auth
        if auth is None:
            return False
        return set(route.required_scopes).issubset(auth.scopes)

    def _route_payload(
        self, route: RouteConfig, states: Mapping[str, str] | None = None
    ) -> tuple[Any, ResponseSpec]:
        if route.states:
            assert route.state_family is not None
            state = (states or self._current_states)[route.state_family]
            spec = route.states[state]
        else:
            assert route.response is not None
            spec = route.response
        return spec.data, spec

    def _find_route(self, method: str, path: str) -> tuple[RouteConfig, dict[str, str]] | None:
        for route in self._routes:
            if route.method != method.upper():
                continue
            result = match_path(self._patterns[id(route)], route.path, path)
            if result is not None:
                return route, result.parameters
        return None

    async def _control_handler(self, request: web.Request) -> web.StreamResponse:
        if not secrets.compare_digest(
            request.headers.get(CONTROL_SECRET_HEADER, ""), self._control_secret
        ):
            return _error(401, "unauthorized")
        path = request.path
        control = self.config.control
        if path == control.health_path and request.method == "GET":
            return web.json_response({"ok": True})
        if path == control.capability_path and request.method == "GET":
            return web.json_response(self.capability.as_dict())
        if path == control.counters_path and request.method == "GET":
            return web.json_response(self.counters.snapshot())
        if path == control.reset_path and request.method == "POST":
            self.counters.reset()
            return web.json_response({"status": "reset"})
        if path == control.state_path:
            return await self._state_control(request)
        return _error(404, "not found")

    async def _state_control(self, request: web.Request) -> web.Response:
        if request.method == "GET":
            return web.json_response({"states": dict(self._current_states)})
        if request.method != "POST":
            return _error(405, "method not allowed")
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _error(400, "invalid json")
        if not isinstance(body, Mapping) or set(body) != {"family", "state"}:
            return _error(400, "state control requires family and state")
        family = body["family"]
        state = body["state"]
        if not isinstance(family, str) or not isinstance(state, str):
            return _error(400, "state control requires string values")
        state_routes = [route for route in self.config.routes if route.state_family == family]
        if not state_routes:
            return _error(404, "unknown dataset family")
        if any(state not in route.states for route in state_routes):
            return _error(400, "unknown dataset state")
        self._current_states[family] = state
        for key in list(self._cursor_maps):
            if key[0] in {route.path for route in state_routes}:
                del self._cursor_maps[key]
        return web.json_response({"family": family, "state": state})


def _site_port(site: web.TCPSite) -> int:
    server = getattr(site, "_server", None)
    sockets = getattr(server, "sockets", None)
    if not sockets:
        raise RuntimeError("HTTP site did not expose a bound socket")
    return int(sockets[0].getsockname()[1])


def _status_message(status: int) -> str:
    return {403: "forbidden", 404: "not found"}.get(status, "source error")


def _item_parameter(path: str, parameters: Mapping[str, str]) -> str | None:
    if not parameters:
        return None
    if path.endswith("/{id}"):
        return parameters.get("id")
    if path.count("{") == 1 and path.rsplit("/", 1)[-1].startswith("{"):
        return next(iter(parameters.values()))
    return None


def _state_key(route: RouteConfig, states: Mapping[str, str]) -> str:
    return states.get(route.state_family or "", "static")


async def start_server(
    config: ScenarioConfig | str | Mapping[str, Any],
    *,
    data_port: int | None = None,
    control_port: int | None = None,
) -> MockRestServer:
    """Construct and start a server, returning only after both ports answer."""

    if data_port is not None or control_port is not None:
        from dataclasses import replace

        loaded = config if isinstance(config, ScenarioConfig) else load_config(config)
        config = replace(
            loaded,
            data_port=loaded.data_port if data_port is None else data_port,
            control_port=loaded.control_port if control_port is None else control_port,
        )
    server = MockRestServer(config)
    return await server.start()

"""Strict scenario parsing for the mock source.

The parser turns YAML into an explicit route behavior table and rejects every
unknown key before a server can start.  A typo in a behavior declaration would
otherwise create a deceptively easy scenario, so permissive YAML loading is an
invalid configuration rather than a warning.
"""

from __future__ import annotations

import csv
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigError(ValueError):
    """Raised when a scenario does not satisfy the route-table contract."""


_MISSING = object()
SUPPORTED_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{location} must be a mapping")
    return dict(value)


def _keys(value: Mapping[str, Any], allowed: set[str], location: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise ConfigError(f"{location} contains unknown key(s): {joined}")


def _nonempty_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{location} must be a non-empty string")
    return value


def _integer(value: Any, location: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{location} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{location} must be at least {minimum}")
    return value


def _paths_overlap(left: str, right: str) -> bool:
    """Return whether two literal/template paths can address the same URL."""

    left_parts = [part for part in left.split("/") if part]
    right_parts = [part for part in right.split("/") if part]
    if len(left_parts) != len(right_parts):
        return False
    return all(
        left_part == right_part
        or re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", left_part) is not None
        or re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", right_part) is not None
        for left_part, right_part in zip(left_parts, right_parts)
    )


@dataclass(frozen=True)
class ResponseSpec:
    """A response loaded once from inline JSON or a fixture file."""

    data: Any
    format: str = "json"
    item_key: str = "id"
    source: Path | None = None
    serialized_json: bytes | None = None
    fixture_source: str | None = None

    @property
    def deferred(self) -> bool:
        """Whether a hidden fixture source has not yet been resolved."""

        return self.fixture_source is not None and self.data is None

    @classmethod
    def from_value(
        cls, value: Any, *, base_dir: Path, location: str
    ) -> "ResponseSpec":
        if not isinstance(value, Mapping):
            raise ConfigError(f"{location} must be a mapping")
        raw = dict(value)
        _keys(raw, {"json", "file", "fixture_source", "format", "item_key", "encoding"}, location)
        has_json = "json" in raw
        has_file = "file" in raw
        has_fixture_source = "fixture_source" in raw
        if sum((has_json, has_file, has_fixture_source)) != 1:
            raise ConfigError(
                f"{location} must contain exactly one of json, file, or fixture_source"
            )
        item_key = raw.get("item_key", "id")
        _nonempty_string(item_key, f"{location}.item_key")
        fmt = raw.get("format")
        if fmt is not None:
            fmt = _nonempty_string(fmt, f"{location}.format").lower()
            if fmt not in {"json", "csv"}:
                raise ConfigError(f"{location}.format must be json or csv")
        encoding = raw.get("encoding", "utf-8")
        _nonempty_string(encoding, f"{location}.encoding")

        if has_json:
            if "encoding" in raw:
                raise ConfigError(f"{location}.encoding requires file")
            if fmt == "csv":
                raise ConfigError(f"{location} cannot use csv format with inline json")
            data = copy.deepcopy(raw["json"])
            try:
                serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"{location}.json is not JSON serializable: {exc}") from exc
            return cls(
                data,
                format=fmt or "json",
                item_key=item_key,
                serialized_json=serialized,
            )

        if has_fixture_source:
            if "encoding" in raw:
                raise ConfigError(f"{location}.encoding is not allowed with fixture_source")
            if fmt not in (None, "json"):
                raise ConfigError(f"{location}.format must be json with fixture_source")
            table = _nonempty_string(raw["fixture_source"], f"{location}.fixture_source")
            if (
                table in {".", ".."}
                or re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9._-]*", table) is None
            ):
                raise ConfigError(f"{location}.fixture_source must be a safe table name")
            return cls(
                None,
                format="json",
                item_key=item_key,
                serialized_json=None,
                fixture_source=table,
            )

        relative = Path(_nonempty_string(raw["file"], f"{location}.file"))
        path = relative if relative.is_absolute() else base_dir / relative
        if not path.is_file():
            raise ConfigError(f"{location}.file does not exist: {path}")
        effective_format = fmt or ("csv" if path.suffix.lower() == ".csv" else "json")
        try:
            if effective_format == "json":
                data = json.loads(path.read_text(encoding=encoding))
            elif effective_format == "csv":
                with path.open("r", encoding=encoding, newline="") as handle:
                    data = list(csv.DictReader(handle))
            else:
                raise ConfigError(f"{location}.format must be json or csv")
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            raise ConfigError(f"could not read {location}.file {path}: {exc}") from exc
        serialized = None
        if effective_format == "json":
            try:
                serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"{location}.file is not JSON serializable: {exc}") from exc
        return cls(
            data,
            format=effective_format,
            item_key=item_key,
            source=path,
            serialized_json=serialized,
        )


@dataclass(frozen=True)
class PaginationConfig:
    """Cursor settings that intentionally omit a total from data responses."""

    page_size: int
    cursor_param: str = "cursor"
    items_field: str = "data"
    cursor_field: str = "next_cursor"

    @classmethod
    def from_mapping(cls, value: Any, location: str) -> "PaginationConfig":
        raw = _mapping(value, location)
        _keys(raw, {"page_size", "cursor_param", "items_field", "cursor_field"}, location)
        page_size = _integer(raw.get("page_size"), f"{location}.page_size", minimum=1)
        cursor_param = _nonempty_string(raw.get("cursor_param", "cursor"), f"{location}.cursor_param")
        items_field = _nonempty_string(raw.get("items_field", "data"), f"{location}.items_field")
        cursor_field = _nonempty_string(
            raw.get("cursor_field", "next_cursor"), f"{location}.cursor_field"
        )
        return cls(page_size, cursor_param, items_field, cursor_field)


@dataclass(frozen=True)
class HeaderRequirement:
    """A case-insensitive HTTP header name paired with an exact value."""

    name: str
    value: str

    @classmethod
    def from_mapping(cls, value: Any, location: str) -> "HeaderRequirement":
        raw = _mapping(value, location)
        _keys(raw, {"name", "value"}, location)
        return cls(
            _nonempty_string(raw.get("name"), f"{location}.name"),
            _nonempty_string(raw.get("value"), f"{location}.value"),
        )


@dataclass(frozen=True)
class FanoutConfig:
    """Fields used to select children for one parent identifier."""

    parent_id_field: str = "id"
    child_parent_field: str = "parent_id"

    @classmethod
    def from_mapping(cls, value: Any, location: str) -> "FanoutConfig":
        raw = _mapping(value, location)
        _keys(raw, {"parent_id_field", "child_parent_field"}, location)
        return cls(
            _nonempty_string(raw.get("parent_id_field", "id"), f"{location}.parent_id_field"),
            _nonempty_string(
                raw.get("child_parent_field", "parent_id"),
                f"{location}.child_parent_field",
            ),
        )


@dataclass(frozen=True)
class RouteConfig:
    """One path/method and all deterministic behavior applied to it."""

    path: str
    method: str
    response: ResponseSpec | None = None
    states: dict[str, ResponseSpec] = field(default_factory=dict)
    state_family: str | None = None
    initial_state: str = "v1"
    pagination: PaginationConfig | None = None
    fanout: FanoutConfig | None = None
    require_user_agent: bool = False
    required_header: HeaderRequirement | None = None
    auth_required: bool = False
    required_scopes: tuple[str, ...] = ()
    rate_limit_every: int | None = None
    latency_ms: int = 0
    status: int = 200
    write_forbidden: bool = False
    #: Opt in to publishing this route's response contract -- field names,
    #: nesting, pagination and rate-limit pacing -- in the agent's infra
    #: profile.  Off by default: a scenario whose whole drill is discovering
    #: what the source can answer must not have that answer enumerated in its
    #: handover file.  A scenario that hands the agent a documented API
    #: contract turns it on per route.
    publish_contract: bool = False

    @classmethod
    def from_mapping(
        cls, value: Any, *, base_dir: Path, index: int
    ) -> "RouteConfig":
        location = f"routes[{index}]"
        raw = _mapping(value, location)
        allowed = {
            "path",
            "method",
            "response",
            "states",
            "state_family",
            "initial_state",
            "pagination",
            "fanout",
            "require_user_agent",
            "required_header",
            "auth_required",
            "required_scopes",
            "rate_limit_every",
            "rate_limit",
            "latency_ms",
            "status",
            "write_forbidden",
            "publish_contract",
        }
        _keys(raw, allowed, location)
        path = _nonempty_string(raw.get("path"), f"{location}.path")
        if not path.startswith("/") or "?" in path or "#" in path:
            raise ConfigError(f"{location}.path must be an absolute path without query or fragment")
        method = _nonempty_string(raw.get("method", "GET"), f"{location}.method").upper()
        if method not in SUPPORTED_HTTP_METHODS:
            raise ConfigError(f"{location}.method is not a supported HTTP method: {method}")
        status = _integer(raw.get("status", 200), f"{location}.status", minimum=100)
        if status > 599:
            raise ConfigError(f"{location}.status must be between 100 and 599")

        response = None
        if "response" in raw:
            response = ResponseSpec.from_value(
                raw["response"], base_dir=base_dir, location=f"{location}.response"
            )
        states: dict[str, ResponseSpec] = {}
        if "states" in raw:
            state_mapping = _mapping(raw["states"], f"{location}.states")
            if not state_mapping:
                raise ConfigError(f"{location}.states must not be empty")
            for state, spec in state_mapping.items():
                state_name = _nonempty_string(state, f"{location}.states key")
                states[state_name] = ResponseSpec.from_value(
                    spec, base_dir=base_dir, location=f"{location}.states.{state_name}"
                )
        if (
            response is None
            and not states
            and 200 <= status < 300
            and not raw.get("write_forbidden", False)
        ):
            raise ConfigError(f"{location} needs response or states for a successful route")
        if response is not None and states:
            raise ConfigError(f"{location} cannot define both response and states")

        state_family = raw.get("state_family")
        if state_family is not None:
            state_family = _nonempty_string(state_family, f"{location}.state_family")
        if states and state_family is None:
            raise ConfigError(f"{location}.state_family is required when states are defined")
        initial_state = _nonempty_string(raw.get("initial_state", "v1"), f"{location}.initial_state")
        if states and initial_state not in states:
            raise ConfigError(f"{location}.initial_state is not present in {location}.states")

        pagination = (
            PaginationConfig.from_mapping(raw["pagination"], f"{location}.pagination")
            if "pagination" in raw
            else None
        )
        fanout = (
            FanoutConfig.from_mapping(raw["fanout"], f"{location}.fanout")
            if "fanout" in raw
            else None
        )
        if fanout is not None and re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", path) is None:
            raise ConfigError(f"{location}.fanout requires a path parameter")
        for boolean_key in {"require_user_agent", "auth_required", "write_forbidden"}:
            if boolean_key in raw and not isinstance(raw[boolean_key], bool):
                raise ConfigError(f"{location}.{boolean_key} must be boolean")
        raw_scopes = raw.get("required_scopes", [])
        if isinstance(raw_scopes, str) or not isinstance(raw_scopes, list):
            raise ConfigError(f"{location}.required_scopes must be a list")
        required_scopes: list[str] = []
        for scope in raw_scopes:
            scope = _nonempty_string(scope, f"{location}.required_scopes")
            if scope in required_scopes:
                raise ConfigError(f"{location}.required_scopes contains duplicate: {scope}")
            required_scopes.append(scope)
        if required_scopes and not raw.get("auth_required", False):
            raise ConfigError(f"{location}.required_scopes requires auth_required")

        rate_limit_every = raw.get("rate_limit_every")
        if "rate_limit" in raw:
            rate_mapping = _mapping(raw["rate_limit"], f"{location}.rate_limit")
            _keys(rate_mapping, {"every"}, f"{location}.rate_limit")
            configured = _integer(rate_mapping.get("every"), f"{location}.rate_limit.every", minimum=2)
            if rate_limit_every is not None and rate_limit_every != configured:
                raise ConfigError(f"{location} gives conflicting rate-limit values")
            rate_limit_every = configured
        if rate_limit_every is not None:
            rate_limit_every = _integer(rate_limit_every, f"{location}.rate_limit_every", minimum=2)

        latency_ms = _integer(raw.get("latency_ms", 0), f"{location}.latency_ms", minimum=0)
        write_forbidden = raw.get("write_forbidden", False)
        if write_forbidden and method == "GET":
            raise ConfigError(f"{location}.write_forbidden requires a write method")
        if not 200 <= status < 300 or write_forbidden:
            inert_keys = {
                "response",
                "states",
                "state_family",
                "initial_state",
                "pagination",
                "fanout",
                "require_user_agent",
                "required_header",
                "auth_required",
                "rate_limit_every",
                "rate_limit",
            }
            inert = sorted(key for key in raw if key in inert_keys)
            if inert:
                raise ConfigError(
                    f"{location} behavior key(s) cannot be combined with "
                    f"status != 200 or write_forbidden: {', '.join(inert)}"
                )
        return cls(
            path=path,
            method=method,
            response=response,
            states=states,
            state_family=state_family,
            initial_state=initial_state,
            pagination=pagination,
            fanout=fanout,
            require_user_agent=bool(raw.get("require_user_agent", False)),
            required_header=(
                HeaderRequirement.from_mapping(raw["required_header"], f"{location}.required_header")
                if "required_header" in raw
                else None
            ),
            auth_required=bool(raw.get("auth_required", False)),
            required_scopes=tuple(required_scopes),
            rate_limit_every=rate_limit_every,
            latency_ms=latency_ms,
            status=status,
            write_forbidden=write_forbidden,
            publish_contract=bool(raw.get("publish_contract", False)),
        )


@dataclass(frozen=True)
class DocPage:
    """A data-port documentation page; it may disclose source facts naturally."""

    body: str
    content_type: str = "text/plain"

    @classmethod
    def from_value(cls, value: Any, location: str) -> "DocPage":
        if isinstance(value, str):
            return cls(value)
        raw = _mapping(value, location)
        _keys(raw, {"body", "content_type"}, location)
        body = raw.get("body")
        if not isinstance(body, str):
            raise ConfigError(f"{location}.body must be a string")
        content_type = _nonempty_string(raw.get("content_type", "text/plain"), f"{location}.content_type")
        return cls(body, content_type)


@dataclass(frozen=True)
class AuthConfig:
    """Count-based bearer authentication state initialized for each server run."""

    token: str
    initial_requests: int
    header: str = "Authorization"
    scheme: str = "Bearer"
    refresh_path: str = "/refresh"
    scopes: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Any, location: str) -> "AuthConfig":
        raw = _mapping(value, location)
        _keys(raw, {"token", "initial_requests", "header", "scheme", "refresh_path", "scopes"}, location)
        token = _nonempty_string(raw.get("token"), f"{location}.token")
        initial = _integer(raw.get("initial_requests"), f"{location}.initial_requests", minimum=1)
        header = _nonempty_string(raw.get("header", "Authorization"), f"{location}.header")
        scheme = _nonempty_string(raw.get("scheme", "Bearer"), f"{location}.scheme")
        refresh_path = _nonempty_string(raw.get("refresh_path", "/refresh"), f"{location}.refresh_path")
        if not refresh_path.startswith("/"):
            raise ConfigError(f"{location}.refresh_path must be an absolute path")
        raw_scopes = raw.get("scopes", [])
        if isinstance(raw_scopes, str) or not isinstance(raw_scopes, list):
            raise ConfigError(f"{location}.scopes must be a list")
        scopes: list[str] = []
        for scope in raw_scopes:
            scope = _nonempty_string(scope, f"{location}.scopes")
            if scope in scopes:
                raise ConfigError(f"{location}.scopes contains duplicate: {scope}")
            scopes.append(scope)
        return cls(token, initial, header, scheme, refresh_path, tuple(scopes))


@dataclass(frozen=True)
class ControlConfig:
    """Control-port paths kept outside the source API."""

    health_path: str = "/health"
    counters_path: str = "/counters"
    reset_path: str = "/counters/reset"
    capability_path: str = "/capability"
    state_path: str = "/state"

    @classmethod
    def from_mapping(cls, value: Any, location: str) -> "ControlConfig":
        raw = _mapping(value, location)
        allowed = {"health_path", "counters_path", "reset_path", "capability_path", "state_path"}
        _keys(raw, allowed, location)
        values: dict[str, str] = {}
        for key, default in {
            "health_path": "/health",
            "counters_path": "/counters",
            "reset_path": "/counters/reset",
            "capability_path": "/capability",
            "state_path": "/state",
        }.items():
            path = _nonempty_string(raw.get(key, default), f"{location}.{key}")
            if not path.startswith("/"):
                raise ConfigError(f"{location}.{key} must be an absolute path")
            values[key] = path
        if len(set(values.values())) != len(values):
            raise ConfigError(f"{location} paths must be distinct")
        return cls(**values)


@dataclass(frozen=True)
class ScenarioConfig:
    """Validated server settings and immutable route behavior declarations."""

    routes: tuple[RouteConfig, ...]
    docs: dict[str, DocPage]
    capability: dict[str, Any]
    auth: AuthConfig | None = None
    control: ControlConfig = field(default_factory=ControlConfig)
    data_host: str = "127.0.0.1"
    data_port: int = 0
    control_host: str = "127.0.0.1"
    control_port: int = 0
    base_dir: Path = Path(".")
    source_path: Path | None = None


def load_config(
    source: str | Path | Mapping[str, Any], *, base_dir: Path | None = None
) -> ScenarioConfig:
    """Load and validate a YAML path or mapping into a :class:`ScenarioConfig`."""

    source_path: Path | None = None
    if isinstance(source, (str, Path)):
        source_path = Path(source).resolve()
        try:
            raw_loaded = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ConfigError(f"could not read scenario file {source_path}: {exc}") from exc
        resolved_base_dir = source_path.parent if base_dir is None else Path(base_dir)
    else:
        raw_loaded = source
        resolved_base_dir = Path.cwd() if base_dir is None else Path(base_dir)
    raw = _mapping(raw_loaded, "scenario")
    _keys(
        raw,
        {
            "version",
            "routes",
            "docs",
            "capability",
            "auth",
            "control",
            "data_host",
            "data_port",
            "control_host",
            "control_port",
        },
        "scenario",
    )
    version = _integer(raw.get("version", 1), "scenario.version", minimum=1)
    if version != 1:
        raise ConfigError(f"scenario.version {version} is not supported")
    raw_routes = raw.get("routes")
    if not isinstance(raw_routes, list) or not raw_routes:
        raise ConfigError("scenario.routes must be a non-empty list")
    routes = tuple(
        RouteConfig.from_mapping(item, base_dir=resolved_base_dir, index=index)
        for index, item in enumerate(raw_routes)
    )
    identities = [(route.method, route.path) for route in routes]
    if len(set(identities)) != len(identities):
        raise ConfigError("scenario.routes contains duplicate method/path entries")

    docs: dict[str, DocPage] = {}
    raw_docs = raw.get("docs", {})
    docs_mapping = _mapping(raw_docs, "scenario.docs")
    for path, page in docs_mapping.items():
        path_string = _nonempty_string(path, "scenario.docs path")
        if not path_string.startswith("/"):
            raise ConfigError(f"scenario.docs path must be absolute: {path_string}")
        docs[path_string] = DocPage.from_value(page, f"scenario.docs.{path_string}")

    capability = _mapping(raw.get("capability", {}), "scenario.capability")
    # Keep capability syntax errors in the configuration boundary.  The server
    # validates again when it constructs its control-port oracle, but callers
    # that only lint a scenario should get the same strict failure.
    if capability:
        from .capability import CapabilityError, CapabilityManifest

        try:
            CapabilityManifest.from_mapping(capability)
        except CapabilityError as exc:
            raise ConfigError(str(exc)) from exc
    auth = AuthConfig.from_mapping(raw["auth"], "scenario.auth") if "auth" in raw else None
    control = ControlConfig.from_mapping(raw["control"], "scenario.control") if "control" in raw else ControlConfig()
    for doc_path in docs:
        for route in routes:
            if _paths_overlap(doc_path, route.path):
                raise ConfigError(
                    f"scenario.docs path overlaps route path: {doc_path} and {route.path}"
                )
    if auth is not None:
        for route in routes:
            if _paths_overlap(auth.refresh_path, route.path):
                raise ConfigError(
                    "scenario.auth.refresh_path overlaps route path: "
                    f"{auth.refresh_path} and {route.path}"
                )
        for doc_path in docs:
            if _paths_overlap(auth.refresh_path, doc_path):
                raise ConfigError(
                    "scenario.auth.refresh_path overlaps docs path: "
                    f"{auth.refresh_path} and {doc_path}"
                )
    data_host = _nonempty_string(raw.get("data_host", "127.0.0.1"), "scenario.data_host")
    control_host = _nonempty_string(raw.get("control_host", "127.0.0.1"), "scenario.control_host")
    data_port = _integer(raw.get("data_port", 0), "scenario.data_port", minimum=0)
    control_port = _integer(raw.get("control_port", 0), "scenario.control_port", minimum=0)
    if data_port > 65535 or control_port > 65535:
        raise ConfigError("scenario ports must be between 0 and 65535")
    if data_port and control_port and data_port == control_port:
        raise ConfigError("scenario.data_port and scenario.control_port must be different")
    if auth is not None and any(route.auth_required for route in routes) is False:
        raise ConfigError("scenario.auth is present but no route requires authentication")
    if any(route.auth_required for route in routes) and auth is None:
        raise ConfigError("authenticated routes require scenario.auth")
    family_initials: dict[str, str] = {}
    for route in routes:
        if route.states:
            assert route.state_family is not None
            previous = family_initials.setdefault(route.state_family, route.initial_state)
            if previous != route.initial_state:
                raise ConfigError(
                    f"routes for state family {route.state_family} have conflicting initial states"
                )
    return ScenarioConfig(
        routes=routes,
        docs=docs,
        capability=capability,
        auth=auth,
        control=control,
        data_host=data_host,
        data_port=data_port,
        control_host=control_host,
        control_port=control_port,
        base_dir=resolved_base_dir,
        source_path=source_path,
    )


def fixture_source_tables(config: ScenarioConfig) -> frozenset[str]:
    """Return every fixture table named by a route response or state."""

    names: set[str] = set()
    for route in config.routes:
        specs = ([route.response] if route.response is not None else []) + list(route.states.values())
        names.update(
            spec.fixture_source
            for spec in specs
            if spec is not None and spec.fixture_source is not None
        )
    return frozenset(names)


def _validate_resolved_fixture_response(
    route: RouteConfig, spec: ResponseSpec, location: str
) -> None:
    """Validate route behavior that depends on the resolved fixture payload."""

    data = spec.data
    templated = re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", route.path) is not None
    if (route.pagination is not None or route.fanout is not None or templated) and not isinstance(
        data, list
    ):
        raise ConfigError(f"{location} must resolve to a JSON collection for this route")
    if route.fanout is not None:
        for index, row in enumerate(data):
            if not isinstance(row, Mapping) or route.fanout.child_parent_field not in row:
                raise ConfigError(
                    f"{location}[{index}] must contain fanout child field "
                    f"{route.fanout.child_parent_field!r}"
                )
    if templated:
        for index, row in enumerate(data):
            if not isinstance(row, Mapping) or spec.item_key not in row:
                raise ConfigError(
                    f"{location}[{index}] must contain item_key {spec.item_key!r}"
                )


def resolve_fixture_sources(
    config: ScenarioConfig,
    source_dir: Path,
    *,
    expected_sha256: Mapping[str, str] | None = None,
) -> ScenarioConfig:
    """Load deferred source tables from the private oracle source directory."""

    if not any(
        spec.deferred
        for route in config.routes
        for spec in (([route.response] if route.response is not None else []) + list(route.states.values()))
    ):
        return config
    cache: dict[str, tuple[list[dict[str, Any]], bytes]] = {}

    def resolve_spec(spec: ResponseSpec) -> ResponseSpec:
        table = spec.fixture_source
        if table is None or not spec.deferred:
            return spec
        if table not in cache:
            path = Path(source_dir) / f"{table}.json"
            try:
                raw_bytes = path.read_bytes()
            except OSError as exc:
                raise ConfigError(
                    f"fixture_source {table!r} is unavailable in the source directory"
                ) from exc
            if expected_sha256 is not None and table in expected_sha256:
                expected = expected_sha256[table]
                if (
                    not isinstance(expected, str)
                    or hashlib.sha256(raw_bytes).hexdigest() != expected
                ):
                    raise ConfigError(
                        f"fixture_source {table!r} sha256 does not match the fixture manifest"
                    )
            try:
                data = json.loads(raw_bytes.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ConfigError(f"fixture_source {table!r} is not valid UTF-8 JSON") from exc
            if not isinstance(data, list) or any(not isinstance(row, Mapping) for row in data):
                raise ConfigError(f"fixture_source {table!r} must contain a JSON array of objects")
            try:
                serialized = json.dumps(
                    data, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"fixture_source {table!r} is not JSON serializable") from exc
            cache[table] = (data, serialized)
        data, serialized = cache[table]
        return replace(spec, data=data, serialized_json=serialized, source=None)

    resolved_routes: list[RouteConfig] = []
    for route_index, route in enumerate(config.routes):
        response = resolve_spec(route.response) if route.response is not None else None
        states = {state: resolve_spec(spec) for state, spec in route.states.items()}
        if (
            response is not None
            and route.response is not None
            and route.response.deferred
        ):
            _validate_resolved_fixture_response(
                route, response, f"routes[{route_index}].response"
            )
        for state, spec in states.items():
            if route.states[state].deferred:
                _validate_resolved_fixture_response(
                    route, spec, f"routes[{route_index}].states.{state}"
                )
        resolved_routes.append(replace(route, response=response, states=states))
    return replace(config, routes=tuple(resolved_routes))


parse_config = load_config
load_scenario_config = load_config
parse_scenario = load_config

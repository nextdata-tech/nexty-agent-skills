"""Prepare one isolated scenario trial and its row-zero identity.

The invariant enforced here is that every session starts with a fresh home,
fresh generated fixture, and a complete :class:`~dp_scenarios.ledger.Manifest`
already anchored in the ledger.  The mock source's control credential remains
an in-process value and is deliberately absent from the environment exposed to
the session.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import threading
from collections.abc import Callable, Sequence
from types import MappingProxyType
from typing import Any, Mapping

from dp_scenarios.ledger import LedgerRow, LedgerStore, Manifest, fixture_dir_hash
from dp_scenarios.ledger.manifest import NOT_APPLICABLE, REPLAY_SESSION_PATH_FIELDS
from dp_scenarios.knobs import SupervisorKnobs, WorkflowSwitchEvidence, apply_transform_latency
from dp_scenarios.mockrest import MockRestServer
from dp_scenarios import followups
from dp_scenarios.scenario import Scenario


class EnvironmentError(RuntimeError):
    """Raised when a trial cannot be prepared with a comparable identity."""


RunEnvironmentError = EnvironmentError


_AGENT_MANIFEST_FIELDS = frozenset(
    {
        "format_version",
        "dataset",
        "seed",
        "base_instant",
        "python_version",
        "python_implementation",
        "description",
        "table_row_counts",
        "fixture_hash",
    }
)


def _agent_fixture_manifest(manifest: Mapping[str, object], oracle_path: Path) -> dict[str, object]:
    """Return the safe manifest visible to the agent, never the grading oracle."""

    # Use an allowlist: a future generator field is private until explicitly
    # reviewed for agent visibility.
    safe = {key: value for key, value in manifest.items() if key in _AGENT_MANIFEST_FIELDS}
    safe["fixture_scope"] = "agent-visible-data-only"
    safe["oracle_manifest_sha256"] = hashlib.sha256(
        (oracle_path / "fixture-manifest.json").read_bytes()
    ).hexdigest()
    return safe


def _evidence_contract(scenario: Scenario) -> dict[str, object] | None:
    """Describe agent evidence without exposing hidden reference values."""

    path = getattr(scenario, "follow_up_artifact", None)
    if path is None:
        return None
    kind = followups.get(scenario.gates["follow-up"].kind)
    return {
        "format_version": 1,
        "artifact_path": path,
        "required_fields": dict(kind.evidence_contract),
        "instruction": (
            "Write only the required JSON object at artifact_path; do not include "
            "secrets or hidden reference values."
        ),
    }


_SESSION_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "COLORTERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "NO_COLOR",
        "PATH",
        "PYTHONIOENCODING",
        "PYTHONUNBUFFERED",
        "SHELL",
        "TERM",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "USER",
        "VIRTUAL_ENV",
    }
)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EnvironmentError(f"pinned value {field_name} must be a non-empty string")
    return value


LiveCommandBuilder = Callable[[Path, bool, str], Sequence[str]]


def _desktop_command_builder(
    command: Sequence[str] | LiveCommandBuilder,
) -> LiveCommandBuilder:
    """Adapt the legacy base argv to the shared substrate's command seam."""

    if callable(command):
        return command
    base = tuple(str(argument) for argument in command)
    if not base:
        raise EnvironmentError("live desktop command must not be empty")

    def build(config_path: Path, strict_mcp_config: bool, allowed_tools_csv: str) -> Sequence[str]:
        result = [*base, "--mcp-config", str(config_path)]
        if strict_mcp_config:
            result.append("--strict-mcp-config")
        result.extend(("--allowedTools", allowed_tools_csv))
        return result

    return build


@dataclass(frozen=True, slots=True)
class PinnedVersions:
    """Versions and model identity required to compare two trial manifests."""

    skill_pack_version: str
    supervisor_version: str
    runtime_wheel_version: str
    mock_api_version: str
    canary_claims_hash: str
    agent_model_id: str = "replay"
    agent_sampling_params: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({"temperature": 0})
    )
    driver_model_id: str = NOT_APPLICABLE
    driver_sampling_params: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )
    supervisor_binary_path: str = "not-applicable"
    session_config_sha256: str = "not-applicable"

    def __post_init__(self) -> None:
        for name in (
            "skill_pack_version",
            "supervisor_version",
            "runtime_wheel_version",
            "mock_api_version",
            "canary_claims_hash",
            "agent_model_id",
            "driver_model_id",
            "supervisor_binary_path",
            "session_config_sha256",
        ):
            _required_text(getattr(self, name), name)
        if not isinstance(self.agent_sampling_params, Mapping) or not self.agent_sampling_params:
            raise EnvironmentError("pinned value agent_sampling_params must be a non-empty mapping")
        object.__setattr__(self, "agent_sampling_params", MappingProxyType(dict(self.agent_sampling_params)))
        # The driver pins are cross-field, not independent.  An empty mapping
        # is the only truthful sampling record for a scripted operator, and a
        # declared driver with no sampling record cannot be compared across a
        # pair.  Deliberately NOT the agent_sampling_params rule, which demands
        # a non-empty mapping unconditionally.
        if not isinstance(self.driver_sampling_params, Mapping):
            raise EnvironmentError("pinned value driver_sampling_params must be a mapping")
        if self.driver_model_id == NOT_APPLICABLE and self.driver_sampling_params:
            raise EnvironmentError("pinned value driver_sampling_params must be empty when driver_model_id is not-applicable")
        if self.driver_model_id != NOT_APPLICABLE and not self.driver_sampling_params:
            raise EnvironmentError(
                "pinned value driver_sampling_params must be a non-empty mapping when a driver is pinned"
            )
        object.__setattr__(self, "driver_sampling_params", MappingProxyType(dict(self.driver_sampling_params)))

    @property
    def nxd_data_product_wheel_version(self) -> str:
        """Return the manifest spelling for the pinned runtime wheel."""

        return self.runtime_wheel_version

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "PinnedVersions":
        """Build pins without accepting absent values or aliases silently."""

        if not isinstance(value, Mapping):
            raise EnvironmentError("pinned versions must be a mapping")
        runtime = value.get("runtime_wheel_version", value.get("nxd_data_product_wheel_version"))
        required = {
            "skill_pack_version": value.get("skill_pack_version"),
            "supervisor_version": value.get("supervisor_version"),
            "runtime_wheel_version": runtime,
            "mock_api_version": value.get("mock_api_version"),
            "canary_claims_hash": value.get("canary_claims_hash"),
        }
        missing = [name for name, item in required.items() if not isinstance(item, str) or not item.strip()]
        if missing:
            raise EnvironmentError("missing pinned value(s): " + ", ".join(missing))
        agent_model_id = value.get("agent_model_id", "replay")
        if not isinstance(agent_model_id, str) or not agent_model_id.strip():
            raise EnvironmentError("pinned value agent_model_id must be a non-empty string")
        sampling = value.get("agent_sampling_params", {"temperature": 0})
        driver_model_id = value.get("driver_model_id", NOT_APPLICABLE)
        driver_sampling_params = value.get("driver_sampling_params", {})
        return cls(
            skill_pack_version=required["skill_pack_version"],  # type: ignore[arg-type]
            supervisor_version=required["supervisor_version"],  # type: ignore[arg-type]
            runtime_wheel_version=required["runtime_wheel_version"],  # type: ignore[arg-type]
            mock_api_version=required["mock_api_version"],  # type: ignore[arg-type]
            canary_claims_hash=required["canary_claims_hash"],  # type: ignore[arg-type]
            agent_model_id=agent_model_id,
            agent_sampling_params=sampling,  # type: ignore[arg-type]
            # Absence is unambiguous: the driver fields did not exist before
            # the driver operator, so a mapping without them is a scripted run.
            driver_model_id=driver_model_id,  # type: ignore[arg-type]
            driver_sampling_params=driver_sampling_params,  # type: ignore[arg-type]
            supervisor_binary_path=str(value.get("supervisor_binary_path", "not-applicable")),
            session_config_sha256=str(value.get("session_config_sha256", "not-applicable")),
        )


class MockSourceHandle:
    """Run :class:`MockRestServer` on a private event-loop thread."""

    def __init__(self, config: object, *, control_secret: str | None = None) -> None:
        self.config = config
        self.requested_control_secret = control_secret
        self._server: MockRestServer | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._error: BaseException | None = None

    def start(self) -> "MockSourceHandle":
        """Start the two-port server and wait for HTTP readiness."""

        if self._thread is not None:
            return self

        def serve() -> None:
            async def run() -> None:
                try:
                    server = MockRestServer(self.config, control_secret=self.requested_control_secret)
                    await server.start()
                    self._server = server
                    self._ready.set()
                    while not self._stopped.is_set():
                        await asyncio.sleep(0.01)
                    await server.stop()
                except BaseException as exc:  # surfaced to the owning thread
                    self._error = exc
                    self._ready.set()

            asyncio.run(run())

        self._thread = threading.Thread(target=serve, name="dp-scenarios-mock-source", daemon=True)
        self._thread.start()
        if not self._ready.wait(30):
            raise EnvironmentError("mock source did not become ready within 30 seconds")
        if self._error is not None:
            raise EnvironmentError(f"mock source failed during startup: {self._error}") from self._error
        return self

    @property
    def server(self) -> MockRestServer:
        """Return the started server, or fail closed if startup did not finish."""

        if self._server is None:
            raise EnvironmentError("mock source has not started")
        return self._server

    @property
    def control_secret(self) -> str:
        """Return the harness-only control credential."""

        return self.server.control_secret

    def stop(self) -> None:
        """Stop the source and join its private event-loop thread."""

        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
            if self._thread.is_alive():
                raise EnvironmentError("mock source did not stop cleanly")
        self._thread = None
        self._server = None

    close = stop


#: The in-world name every scenario already uses for the file that tells an
#: operator's agent where a configured source lives.
SOURCE_PROFILE_FILENAME = "infra-profile.yaml"


def _endpoint_key(path: str) -> str:
    """Return the profile attribute key for one advertised endpoint path."""

    slug = "".join(
        character if character.isalnum() else "_" for character in path.strip("/")
    ).strip("_")
    return f"endpoint_{slug or 'root'}"


def advertised_endpoints(routes: Sequence[Any]) -> tuple[str, ...]:
    """Return the endpoint paths a configured source would be handed over with.

    Only routes a real profile could name are advertised: a parameter-free
    ``GET`` that serves a successful body.  Error-only routes, forbidden
    writes, and templated paths stay out, because in the real world you learn
    those by calling the API, and because a scenario that grades honest
    probing must not have its answer written into the handover.
    """

    seen: list[str] = []
    for route in routes:
        if getattr(route, "method", "").upper() != "GET":
            continue
        if getattr(route, "status", 200) != 200 or getattr(route, "write_forbidden", False):
            continue
        path = getattr(route, "path", "")
        if not isinstance(path, str) or not path.startswith("/") or "{" in path:
            continue
        if getattr(route, "response", None) is None and not getattr(route, "states", {}):
            continue
        if path not in seen:
            seen.append(path)
    return tuple(seen)


def render_source_profile(
    base_url: str,
    endpoints: Sequence[str],
    *,
    auth: object | None = None,
) -> str:
    """Render the agent-visible infra profile for a run-local API source."""

    lines = [
        "apiVersion: infra.nextdata.com/v1",
        "kind: Profile",
        "metadata:",
        "  name: scenario-local",
        "spec:",
        "  services:",
        "    - name: api-source",
        "      driver: nxd:generic-secrets:1.0.0",
        "      attributes:",
        "        - key: base_url",
        f"          value: {json.dumps(base_url)}",
        "          public: true",
    ]
    if auth is not None:
        lines.extend(
            [
                "        - key: auth_header",
                f"          value: {json.dumps(str(getattr(auth, 'header', 'Authorization')))}",
                "          public: true",
                "        - key: auth_scheme",
                f"          value: {json.dumps(str(getattr(auth, 'scheme', 'Bearer')))}",
                "          public: true",
                "        - key: credential_env",
                '          value: "NXD_EVAL_SOURCE_TOKEN"',
                "          public: true",
            ]
        )
    for path in endpoints:
        lines.extend(
            [
                f"        - key: {_endpoint_key(path)}",
                f"          value: {json.dumps(path)}",
                "          public: true",
            ]
        )
    return "\n".join(lines) + "\n"


def _scenario_route_config(scenario: Scenario) -> object | None:
    """Read only public route declarations when a scenario exposes one."""

    for name in ("route_table", "mock_config", "mock_source"):
        value = getattr(scenario, name, None)
        if value is not None:
            return value
    return None


@dataclass(slots=True)
class RunEnvironment:
    """Disposable home, fixture, optional source, and ledger for one trial."""

    scenario: Scenario
    pins: PinnedVersions
    trial_index: int = 0
    root: Path | None = None
    run_id: str | None = None
    route_config: object | None = None
    control_secret: str | None = None
    manifest_override: Manifest | Mapping[str, object] | None = None
    live_command: Sequence[str] | LiveCommandBuilder | None = None
    live_environment: Mapping[str, str] | None = None
    supervisor_command: str | Path | Sequence[str] | None = None
    supervisor_args: Sequence[str] = ()
    supervisor_environment: Mapping[str, str] | None = None
    desktop_server_name: str = "nxd-desktop"
    desktop_allowed_tools: Sequence[str] | None = None
    desktop_session_root: Path | None = None
    live_cwd: Path | None = None
    allow_host_home: bool = False
    knobs: SupervisorKnobs = field(default_factory=SupervisorKnobs.off)
    attempt: int = 1
    _temporary: tempfile.TemporaryDirectory[str] | None = field(default=None, init=False, repr=False)
    _mock_source: MockSourceHandle | None = field(default=None, init=False, repr=False)
    _ledger: LedgerStore | None = field(default=None, init=False, repr=False)
    _manifest: Manifest | None = field(default=None, init=False, repr=False)
    _fixture: Path | None = field(default=None, init=False, repr=False)
    _oracle: Path | None = field(default=None, init=False, repr=False)
    _generated_fixture_manifest: Mapping[str, object] | None = field(default=None, init=False, repr=False)
    _home: Path | None = field(default=None, init=False, repr=False)
    _live_transport: Any | None = field(default=None, init=False, repr=False)
    _source_profile_path: Path | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> "RunEnvironment":
        return self.prepare()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        try:
            self.close()
        except BaseException as cleanup_error:
            if exc_type is None:
                raise
            exc_value.add_note(f"RunEnvironment cleanup failed: {cleanup_error}")

    def prepare(self) -> "RunEnvironment":
        """Generate the fixture, anchor row zero, then start the optional source."""

        if self._temporary is not None:
            return self
        parent = str(self.root.expanduser().resolve()) if self.root is not None else None
        if parent is not None and not Path(parent).is_dir():
            raise EnvironmentError(f"environment root is not a directory: {parent}")
        self._temporary = tempfile.TemporaryDirectory(prefix="dp-scenario-run-", dir=parent)
        base = Path(self._temporary.name)
        self._home = base / "home"
        self._home.mkdir()
        for relative in (".nxd", ".config", ".local/share", ".cache", ".state"):
            (self._home / relative).mkdir(parents=True, exist_ok=True)
        self._fixture = base / "fixture"
        generation = self.scenario.generate_fixture(self._fixture)
        self._generated_fixture_manifest = dict(generation.manifest)
        base_instant = generation.manifest.get("base_instant")
        if not isinstance(base_instant, str) or not base_instant:
            self.close()
            raise EnvironmentError("generated fixture manifest has no pinned base_instant")
        try:
            self._oracle = base / "oracle"
            self._oracle.mkdir()
            oracle_manifest = self._oracle / "fixture-manifest.json"
            shutil.move(str(generation.manifest_path), str(oracle_manifest))
            shutil.move(str(generation.gold_dir), str(self._oracle / "gold"))
            (self._fixture / "fixture-manifest.json").write_text(
                json.dumps(_agent_fixture_manifest(generation.manifest, self._oracle), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            contract = _evidence_contract(self.scenario)
            if contract is not None:
                workspace = self.workspace_dir
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "scenario-evidence-contract.json").write_text(
                    json.dumps(contract, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        except Exception as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f"RunEnvironment cleanup failed: {cleanup_error}")
            raise

        route_config = self.route_config if self.route_config is not None else _scenario_route_config(self.scenario)
        requested_validation_mode = "live" if self.live_command is not None else "replay"

        # A live desktop transport must exist before row zero is anchored: its
        # resolved executable and session artifact paths are part of identity.
        # Replay and handler-backed runs leave this unset and never import the
        # desktop substrate.
        try:
            if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
                raise EnvironmentError("attempt must be a positive integer")
            if self.knobs.transform_window is not None:
                if route_config is None:
                    raise EnvironmentError("transform_window requires a mock-rest route configuration")
                route_config = apply_transform_latency(route_config, self.knobs.transform_window)
            if self.knobs.broker_fault is not None and self.live_command is None:
                raise EnvironmentError("broker_fault requires a live desktop environment")
            if route_config is not None:
                self._mock_source = MockSourceHandle(route_config, control_secret=self.control_secret).start()
                self._write_source_profile()
            if self.live_command is not None:
                if self.supervisor_command is None:
                    raise EnvironmentError("live desktop environment requires a supervisor_command")
                from .desktop import DesktopStdioTransport

                supervisor_args = tuple(str(argument) for argument in self.supervisor_args)
                if not supervisor_args:
                    supervisor_args = (
                        "--data-dir",
                        str(base / "desktop-state"),
                        "mcp",
                        "serve",
                    )
                # Host-home access is an explicit allowance for the agent
                # process (typically to read a configured Claude profile),
                # not an implicit allowance for the supervisor or its
                # descendants.  Keep this invariant even when a caller
                # supplies additional supervisor variables.
                supervisor_environment = dict(self.supervisor_environment or {})
                supervisor_environment.update(
                    {"HOME": str(self.home), "USERPROFILE": str(self.home)}
                )
                if self.knobs.broker_fault is not None:
                    supervisor_args = self.knobs.broker_fault.supervisor_args_for_attempt(  # type: ignore[union-attr]
                        self.attempt,
                        supervisor_args,
                    )
                    supervisor_environment.update(
                        self.knobs.broker_fault.environment_for_attempt(self.attempt)  # type: ignore[union-attr]
                    )

                transport = DesktopStdioTransport.create(
                    _desktop_command_builder(self.live_command),
                    environment={
                        **self.agent_environment,
                        **dict(self.live_environment or {}),
                    },
                    cwd=self.live_cwd or (base / "agent"),
                    server_command=self.supervisor_command,
                    server_args=supervisor_args,
                    server_environment=supervisor_environment,
                    root=self.desktop_session_root or (base / "desktop-session"),
                    server_name=self.desktop_server_name,
                    allowed_tools=self.desktop_allowed_tools,
                )
                (self.live_cwd or (base / "agent")).mkdir(parents=True, exist_ok=True)
                self._live_transport = transport
                transport.start()
        except Exception as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f"RunEnvironment cleanup failed: {cleanup_error}")
            raise

        effective_run_id = self.run_id or f"{self.scenario.id}-trial-{self.trial_index}"
        if not isinstance(effective_run_id, str) or not effective_run_id:
            raise EnvironmentError("run_id must be a non-empty string")
        override: Manifest | None = None
        if self.manifest_override is not None:
            try:
                override = (
                    self.manifest_override
                    if isinstance(self.manifest_override, Manifest)
                    else Manifest.from_mapping(
                        self.manifest_override,
                        replay=False if requested_validation_mode == "live" else None,
                    )
                )
            except Exception as error:
                try:
                    self.close()
                except BaseException as cleanup_error:
                    error.add_note(f"RunEnvironment cleanup failed: {cleanup_error}")
                raise

        manifest = Manifest(
            agent_model_id=self.pins.agent_model_id,
            agent_sampling_params=dict(self.pins.agent_sampling_params),
            driver_model_id=self.pins.driver_model_id,
            driver_sampling_params=dict(self.pins.driver_sampling_params),
            judge_model_id="not-applicable",
            judge_prompt_hash="not-applicable",
            skill_pack_version=self.pins.skill_pack_version,
            supervisor_version=self.pins.supervisor_version,
            nxd_data_product_wheel_version=self.pins.runtime_wheel_version,
            fixture_dir_hash=fixture_dir_hash(self.fixture_dir),
            mock_api_version=self.pins.mock_api_version,
            operator_script_hash=self.scenario.script_hash,
            turn_budget=self.scenario.turn_budget,
            grant_fixture_hash="not-applicable",
            scenario_id=self.scenario.id,
            tier=self.scenario.tier,
            trial_index=self.trial_index,
            canary_claims_hash=self.pins.canary_claims_hash,
            persona_paraphrase_prompt_hash="not-applicable",
            judge_calibration_set_hash="not-applicable",
            fixture_seed=self.scenario.seed,
            fixture_base_instant=base_instant,
            run_id=effective_run_id,
            supervisor_binary_path=(
                self._live_transport.supervisor_binary_path
                if self._live_transport is not None
                else self.pins.supervisor_binary_path
            ),
            session_root=(
                str(self._live_transport.root)
                if self._live_transport is not None
                else "not-applicable"
            ),
            session_config_path=(
                str(self._live_transport.config_path)
                if self._live_transport is not None
                else "not-applicable"
            ),
            session_config_sha256=(
                self._live_transport.session_config_sha256
                if self._live_transport is not None
                else self.pins.session_config_sha256
            ),
            session_trace_path=(
                str(self._live_transport.trace_path)
                if self._live_transport is not None
                else "not-applicable"
            ),
            session_server_result_path=(
                str(self._live_transport.server_result_path)
                if self._live_transport is not None
                else "not-applicable"
            ),
            runtime_knobs=self.knobs.to_manifest(attempt=self.attempt),
            validation_mode=requested_validation_mode,
        )
        if override is not None:
            for field_name in Manifest.fields:
                if field_name in {"run_id", "validation_mode"}:
                    continue
                if self._live_transport is None and field_name in REPLAY_SESSION_PATH_FIELDS:
                    continue
                if getattr(override, field_name) != getattr(manifest, field_name):
                    error = EnvironmentError(f"replay manifest mismatch in {field_name}")
                    try:
                        self.close()
                    except BaseException as cleanup_error:
                        error.add_note(f"RunEnvironment cleanup failed: {cleanup_error}")
                    raise error
            manifest = override
        self._manifest = manifest
        try:
            self._ledger = LedgerStore.open(base / "evidence.jsonl", manifest)
        except Exception as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f"RunEnvironment cleanup failed: {cleanup_error}")
            raise
        return self

    @property
    def base_dir(self) -> Path:
        """Return the private run directory."""

        if self._temporary is None:
            raise EnvironmentError("environment has not been prepared")
        return Path(self._temporary.name)

    @property
    def home(self) -> Path:
        """Return the fresh sandboxed home directory."""

        if self._home is None:
            raise EnvironmentError("environment has not been prepared")
        return self._home

    @property
    def fixture_dir(self) -> Path:
        """Return generated fixture data and the safe manifest."""

        if self._fixture is None:
            raise EnvironmentError("environment has not been prepared")
        return self._fixture

    @property
    def oracle_dir(self) -> Path:
        """Return the harness-only oracle directory."""

        if self._oracle is None:
            raise EnvironmentError("environment has not been prepared")
        return self._oracle

    @property
    def generated_fixture_manifest(self) -> Mapping[str, object]:
        """Return the harness-owned manifest captured before the run."""

        if self._generated_fixture_manifest is None:
            raise EnvironmentError("generated fixture manifest is not available")
        return self._generated_fixture_manifest

    @property
    def ledger_path(self) -> Path:
        """Return the append-only ledger path."""

        if self._ledger is None:
            raise EnvironmentError("environment has not been prepared")
        return self._ledger.path

    @property
    def ledger(self) -> LedgerStore:
        """Return the open ledger handle used by the runner."""

        if self._ledger is None:
            raise EnvironmentError("environment has not been prepared")
        return self._ledger

    @property
    def manifest(self) -> Manifest:
        """Return the exact row-zero identity."""

        if self._manifest is None:
            raise EnvironmentError("environment has not been prepared")
        return self._manifest

    @property
    def workspace_dir(self) -> Path:
        """Return the directory the agent process runs in."""

        if self._temporary is None:
            raise EnvironmentError("environment has not been prepared")
        return self.live_cwd or (Path(self._temporary.name) / "agent")

    @property
    def source_profile_path(self) -> Path | None:
        """Return the agent-visible infra profile, when a source is running."""

        return self._source_profile_path

    def _write_source_profile(self) -> None:
        """Hand the running source to the agent the way an operator would.

        The URL is also exported as ``NXD_EVAL_SOURCE_URL``, but nothing tells
        an agent that a private environment variable exists, so an environment
        variable alone is not a handover.  A profile file in the workspace is:
        it is the artifact the scenarios' operators already refer to, it is
        found by the ordinary Read/Glob tools, and it survives a run with no
        shell.  It carries only what a real handover carries -- the base URL
        and the endpoints the source is documented to serve.
        """

        source = self._mock_source
        if source is None:
            return
        workspace = self.workspace_dir
        workspace.mkdir(parents=True, exist_ok=True)
        path = workspace / SOURCE_PROFILE_FILENAME
        path.write_text(
            render_source_profile(
                source.server.data_url,
                advertised_endpoints(source.server.config.routes),
                auth=source.server.config.auth,
            ),
            encoding="utf-8",
        )
        self._source_profile_path = path

    @property
    def mock_source(self) -> MockSourceHandle | None:
        """Return the optional source handle owned by this environment."""

        return self._mock_source

    @property
    def live_transport(self) -> Any:
        """Return the prepared desktop adapter for a live run."""

        if self._live_transport is None:
            raise EnvironmentError("environment has no live desktop transport")
        return self._live_transport

    def live_session(self, *, timeout: float = 300.0) -> Any:
        """Build the turn-protocol session from the prepared desktop adapter."""

        return self.live_transport.live_session(timeout=timeout)

    def record_workflow_switch(
        self,
        evidence: WorkflowSwitchEvidence,
        *,
        turn: int = 1,
    ) -> None:
        """Append the endpoint identity returned by the post-switch call."""

        if self.knobs.workflow_switch is None:
            raise EnvironmentError("workflow switch evidence requires the workflow_switch knob")
        self.ledger.append(
            LedgerRow(
                run_id=self.manifest.run_id,
                scenario_id=self.manifest.scenario_id,
                turn=turn,
                phase=6,
                action_kind="query",
                action="first post-switch call endpoint recorded",
                claim=evidence.to_dict(),
                evidence_ref="runtime-knobs/workflow-switch",
                qualification="demonstrated-once",
            )
        )

    @property
    def agent_environment(self) -> Mapping[str, str]:
        """Return only explicitly safe parent variables plus run-local values."""

        if self._temporary is None:
            raise EnvironmentError("environment has not been prepared")
        values = {
            key: value
            for key, value in os.environ.items()
            if key in _SESSION_ENVIRONMENT_ALLOWLIST
        }
        values.update(
            {
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "XDG_DATA_HOME": str(self.home / ".local/share"),
                "XDG_CACHE_HOME": str(self.home / ".cache"),
                "XDG_STATE_HOME": str(self.home / ".state"),
                "NXD_EVAL_FIXTURE_DIR": str(self.fixture_dir),
                "NXD_EVAL_ATTESTATIONS_PATH": str(self.base_dir / "agent" / "agent-attestations.json"),
            }
        )
        if self.allow_host_home:
            host_home = str(Path.home())
            values.update({"HOME": host_home, "USERPROFILE": host_home})
        if self._mock_source is not None:
            values["NXD_EVAL_SOURCE_URL"] = self._mock_source.server.data_url
            auth = self._mock_source.server.config.auth
            if auth is not None:
                values["NXD_EVAL_SOURCE_TOKEN"] = auth.token
        if self._source_profile_path is not None:
            values["NXD_EVAL_SOURCE_PROFILE"] = str(self._source_profile_path)
        return MappingProxyType(values)

    @property
    def session_environment(self) -> Mapping[str, str]:
        """Compatibility spelling for the agent-visible environment."""

        return self.agent_environment

    def close(self) -> None:
        """Close the ledger/source and remove the disposable run tree."""

        first_error: BaseException | None = None
        resources = (
            ("_live_transport", "cleanup"),
            ("_ledger", "close"),
            ("_mock_source", "stop"),
            ("_temporary", "cleanup"),
        )
        for attribute, method_name in resources:
            resource = getattr(self, attribute)
            if resource is None:
                continue
            try:
                getattr(resource, method_name)()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
            finally:
                setattr(self, attribute, None)
        self._manifest = None
        self._fixture = None
        self._oracle = None
        self._generated_fixture_manifest = None
        self._home = None
        self._source_profile_path = None
        if first_error is not None:
            raise first_error


Environment = RunEnvironment
RunSetup = RunEnvironment


__all__ = [
    "Environment",
    "EnvironmentError",
    "MockSourceHandle",
    "PinnedVersions",
    "RunEnvironment",
    "RunEnvironmentError",
    "RunSetup",
]

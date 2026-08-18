"""Prepare one isolated scenario trial and its row-zero identity.

The invariant enforced here is that every session starts with a fresh home,
fresh generated fixture, and a complete :class:`~dp_scenarios.ledger.Manifest`
already anchored in the ledger.  The mock source's control credential remains
an in-process value and is deliberately absent from the environment exposed to
the session.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import threading
from types import MappingProxyType
from typing import Any, Mapping

from dp_scenarios.canary.probe import SESSION_ENVIRONMENT_ALLOWLIST
from dp_scenarios.ledger import LedgerStore, Manifest
from dp_scenarios.mockrest import MockRestServer
from dp_scenarios.scenario import Scenario


class EnvironmentError(RuntimeError):
    """Raised when a trial cannot be prepared with a comparable identity."""


_SESSION_ENVIRONMENT_ALLOWLIST = SESSION_ENVIRONMENT_ALLOWLIST


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EnvironmentError(f"pinned value {field_name} must be a non-empty string")
    return value


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

    def __post_init__(self) -> None:
        for name in (
            "skill_pack_version",
            "supervisor_version",
            "runtime_wheel_version",
            "mock_api_version",
            "canary_claims_hash",
            "agent_model_id",
        ):
            _required_text(getattr(self, name), name)
        if not isinstance(self.agent_sampling_params, Mapping) or not self.agent_sampling_params:
            raise EnvironmentError("pinned value agent_sampling_params must be a non-empty mapping")
        object.__setattr__(self, "agent_sampling_params", MappingProxyType(dict(self.agent_sampling_params)))

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
        sampling = value.get("agent_sampling_params", {"temperature": 0})
        return cls(
            skill_pack_version=required["skill_pack_version"],  # type: ignore[arg-type]
            supervisor_version=required["supervisor_version"],  # type: ignore[arg-type]
            runtime_wheel_version=required["runtime_wheel_version"],  # type: ignore[arg-type]
            mock_api_version=required["mock_api_version"],  # type: ignore[arg-type]
            canary_claims_hash=required["canary_claims_hash"],  # type: ignore[arg-type]
            agent_model_id=str(value.get("agent_model_id", "replay")),
            agent_sampling_params=sampling,  # type: ignore[arg-type]
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
    _temporary: tempfile.TemporaryDirectory[str] | None = field(default=None, init=False, repr=False)
    _mock_source: MockSourceHandle | None = field(default=None, init=False, repr=False)
    _ledger: LedgerStore | None = field(default=None, init=False, repr=False)
    _manifest: Manifest | None = field(default=None, init=False, repr=False)
    _fixture: Path | None = field(default=None, init=False, repr=False)
    _home: Path | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> "RunEnvironment":
        return self.prepare()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

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

        route_config = self.route_config if self.route_config is not None else _scenario_route_config(self.scenario)

        generated_manifest = generation.manifest
        base_instant = generated_manifest.get("base_instant")
        if not isinstance(base_instant, str) or not base_instant:
            raise EnvironmentError("generated fixture manifest has no pinned base_instant")
        effective_run_id = self.run_id or f"{self.scenario.id}-trial-{self.trial_index}"
        if not isinstance(effective_run_id, str) or not effective_run_id:
            raise EnvironmentError("run_id must be a non-empty string")
        manifest = Manifest(
            agent_model_id=self.pins.agent_model_id,
            agent_sampling_params=dict(self.pins.agent_sampling_params),
            judge_model_id="not-applicable",
            judge_prompt_hash="not-applicable",
            skill_pack_version=self.pins.skill_pack_version,
            supervisor_version=self.pins.supervisor_version,
            nxd_data_product_wheel_version=self.pins.runtime_wheel_version,
            fixture_dir_hash=str(generation.manifest.get("fixture_hash", "")),
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
        )
        if self.manifest_override is not None:
            try:
                override = self.manifest_override if isinstance(self.manifest_override, Manifest) else Manifest.from_mapping(self.manifest_override)
            except Exception:
                self.close()
                raise
            for field_name in Manifest.fields:
                if field_name == "run_id":
                    continue
                if getattr(override, field_name) != getattr(manifest, field_name):
                    self.close()
                    raise EnvironmentError(f"replay manifest mismatch in {field_name}")
            manifest = override
        self._manifest = manifest
        self._ledger = LedgerStore.open(base / "evidence.jsonl", manifest)
        try:
            if route_config is not None:
                self._mock_source = MockSourceHandle(route_config, control_secret=self.control_secret).start()
        except Exception:
            self.close()
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
        """Return generated fixture data and gold artifacts."""

        if self._fixture is None:
            raise EnvironmentError("environment has not been prepared")
        return self._fixture

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
    def mock_source(self) -> MockSourceHandle | None:
        """Return the optional source handle owned by this environment."""

        return self._mock_source

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
            }
        )
        if self._mock_source is not None:
            values["NXD_EVAL_SOURCE_URL"] = self._mock_source.server.data_url
        return MappingProxyType(values)

    @property
    def session_environment(self) -> Mapping[str, str]:
        """Compatibility spelling for the agent-visible environment."""

        return self.agent_environment

    def close(self) -> None:
        """Close the ledger/source and remove the disposable run tree."""

        if self._ledger is not None:
            self._ledger.close()
            self._ledger = None
        if self._mock_source is not None:
            self._mock_source.stop()
            self._mock_source = None
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
        self._manifest = None
        self._fixture = None
        self._home = None


Environment = RunEnvironment
RunSetup = RunEnvironment


__all__ = [
    "Environment",
    "EnvironmentError",
    "MockSourceHandle",
    "PinnedVersions",
    "RunEnvironment",
    "RunSetup",
]

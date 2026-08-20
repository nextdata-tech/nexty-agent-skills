"""Orchestrate the canary-gated smoke tier and grade on disk artifacts.

The invariant enforced here is the tier boundary: a non-clean canary returns
before a scenario transport is constructed.  Scenario grading reopens the
ledger and reads fixture, closure, supervisor, counter, and query artifacts;
the runner's in-memory engine result is used only to classify the stop
condition and to persist observations.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
import tempfile
import time
from typing import Any, TypeAlias

from dp_scenarios.canary import ClaimsDocument, Verdict, aggregate_verdict, extract_claims, load_claims
from dp_scenarios.canary.probe import BuildResult, ProbeResult, run_build, run_preflight
from dp_scenarios.canary.verdict import build_failure_issues
from dp_scenarios.grading import (
    Finding,
    GateResult,
    ScoreVector,
    gate_build,
    gate_capability,
    gate_construction,
    gate_follow_up,
    gate_honesty,
    gate_intake,
    gate_narrowing,
    gate_query,
    repeatability_certificate,
    score_run,
)
from dp_scenarios.grading.oracles import marker_values
from dp_scenarios.grading.scans import sentinel_byte_scan
from dp_scenarios.grading.score import EfficiencyReport, TerminalState as ScoreTerminalState
from dp_scenarios.grading.statistics import RepeatabilityReport, RepeatabilityTier
from dp_scenarios.ledger import LedgerRow, Manifest, SupervisorFacts, read_ledger
from dp_scenarios.ledger.lint import Finding as LintFinding, LintReport
from dp_scenarios.operator import (
    OperatorEngine,
    StaticSupervisorRecordReader,
    TerminalState as EngineTerminalState,
)
from dp_scenarios.operator.appender import AppenderError, SupervisorRecordReader, TurnEvidence, append_turn_row
from dp_scenarios.operator.transport import Transport
from dp_scenarios.scenario import Scenario, load_scenarios

from .environment import PinnedVersions, RunEnvironment
from .session import ReplayRecording, ReplaySession, RecordingSession


class TierError(RuntimeError):
    """Raised when the tier cannot produce a comparable result."""


@dataclass(frozen=True, slots=True)
class RunBudgets:
    """Declared efficiency denominators; efficiency is never a score input."""

    model_calls: float | None = None
    wall_clock_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in ("model_calls", "wall_clock_seconds"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise TierError(f"declared budget {name} must be positive")


@dataclass(frozen=True, slots=True)
class CanaryResult:
    """Canary probe, build, and probe-scoped verdict."""

    verdict: Verdict
    claims_hash: str | None = None
    probe: ProbeResult | Mapping[str, object] | None = None
    build: BuildResult | Mapping[str, object] | None = None
    wall_clock_seconds: float = 0.0

    @property
    def blocking(self) -> bool:
        """Return the canary's fail-closed gate decision."""

        return self.verdict.blocking

    def to_dict(self) -> dict[str, object]:
        def serial(value: object) -> object:
            if hasattr(value, "to_dict"):
                return value.to_dict()  # type: ignore[attr-defined]
            return value

        return {
            "verdict": self.verdict.to_dict(),
            "claims_hash": self.claims_hash,
            "probe": serial(self.probe),
            "build": serial(self.build),
            "wall_clock_seconds": self.wall_clock_seconds,
        }


@dataclass(frozen=True, slots=True)
class ScenarioRun:
    """One epoch's persisted artifacts, terminal classification, and score."""

    scenario_id: str
    epoch: int
    manifest: Manifest
    terminal_state: EngineTerminalState
    stop_condition: str
    failure_modes: tuple[str, ...]
    ungraded_criteria: frozenset[str]
    score: ScoreVector
    ledger_path: str
    fixture_dir: str
    ledger_bytes: bytes
    wall_clock_seconds: float
    calls: int
    transcript_turns: int
    efficiency: EfficiencyReport
    replay_recording: ReplayRecording
    route_fidelity_status: str
    route_fidelity_reason: str

    @property
    def invalid(self) -> bool:
        """Return whether this run is excluded from scoring rates."""

        return self.score.state is ScoreTerminalState.INVALID

    def scored_dict(self) -> dict[str, object]:
        """Serialize only scored fields; efficiency is intentionally separate."""

        return {
            "scenario_id": self.scenario_id,
            "epoch": self.epoch,
            "terminal_state": self.terminal_state.value,
            "stop_condition": self.stop_condition,
            "failure_modes": list(self.failure_modes),
            "ungraded_criteria": sorted(self.ungraded_criteria),
            "score": {
                "gates": {
                    name: {
                        "passed": result.passed,
                        "points": result.points,
                        "codes": list(result.codes),
                        "examined": result.examined,
                        "ungraded": result.ungraded,
                        "required": result.required,
                    }
                    for name, result in self.score.gates.items()
                },
                "total": self.score.total,
                "hard_gate_flags": dict(self.score.hard_gate_flags),
                "state": self.score.state.value,
                "findings": [finding.code for finding in self.score.findings],
            },
            "route_fidelity": {
                "status": self.route_fidelity_status,
                "reason": self.route_fidelity_reason,
            },
        }

    def as_dict(self) -> dict[str, object]:
        """Serialize scored fields, efficiency, and manifest separately."""

        result = self.scored_dict()
        result["efficiency"] = {
            "turns": self.efficiency.turns,
            "model_calls": self.efficiency.model_calls,
            "wall_clock": self.efficiency.wall_clock,
            "observed_turns": self.transcript_turns,
            "observed_calls": self.calls,
            "observed_wall_clock_seconds": self.wall_clock_seconds,
        }
        result["manifest"] = self.manifest.to_dict()
        result["replay_recording"] = self.replay_recording.to_dict()
        result["ledger_path"] = self.ledger_path
        result["fixture_dir"] = self.fixture_dir
        return result


@dataclass(frozen=True, slots=True)
class ScenarioSummary:
    """All epochs of a declared scenario and its repeatability result."""

    scenario_id: str
    repeatability: RepeatabilityReport
    runs: tuple[ScenarioRun, ...]

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "scenario_id": self.scenario_id,
            "runs": [run.as_dict() for run in self.runs],
            "repeatability": {
                "tier": self.repeatability.tier.value,
                "required_epochs": self.repeatability.required_epochs,
                "observed_epochs": self.repeatability.observed_epochs,
                "certified": self.repeatability.certified,
            },
        }
        if self.repeatability.rates is not None:
            result["repeatability"]["rates"] = {
                gate: {
                    "passed": rate.passed,
                    "examined": rate.examined,
                    "rate": rate.rate,
                    "wilson_lower_bound": rate.lower_bound,
                }
                for gate, rate in self.repeatability.rates.rates.items()
            }
            result["repeatability"]["excluded_invalid"] = self.repeatability.rates.excluded_invalid
        if self.repeatability.demonstrated_once is not None:
            result["repeatability"]["demonstrated_once"] = self.repeatability.demonstrated_once.as_dict()
        return result


@dataclass(frozen=True, slots=True)
class TierResult:
    """Machine-readable result of the canary gate and ordered scenario runs."""

    verdict: str
    canary: CanaryResult
    scenarios: tuple[ScenarioSummary, ...]
    wall_clock_seconds: float
    blocked_reason: tuple[Mapping[str, object], ...] = ()

    @property
    def scenario_runs(self) -> tuple[ScenarioRun, ...]:
        """Return epochs in scenario declaration order."""

        return tuple(run for summary in self.scenarios for run in summary.runs)

    @property
    def blocked_by_canary(self) -> bool:
        """Return whether no scenario was allowed past the canary gate."""

        return self.canary.blocking and not self.scenarios

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "canary": self.canary.to_dict(),
            "scenarios": [summary.as_dict() for summary in self.scenarios],
            "wall_clock_seconds": self.wall_clock_seconds,
            "blocked_reason": list(self.blocked_reason),
            "clean_tier_means": (
                "the canary found no drift in its claims, the scenarios' gates passed against their oracles, and the ledger lint was clean; "
                "this does not mean the unkeyed ledger chain is cryptographically intact"
            ),
        }


SessionFactory: TypeAlias = Callable[..., Transport]
CanaryFactory: TypeAlias = Callable[[], CanaryResult | Verdict]
SupervisorReaderFactory: TypeAlias = Callable[..., SupervisorRecordReader | None]


def _verdict_with_build(verdict: Verdict, build: BuildResult | None, claims: ClaimsDocument) -> Verdict:
    if build is None:
        return verdict
    issues = list(verdict.issues)
    issues.extend(build_failure_issues(build, claims.claims))
    if not issues:
        return verdict
    from dp_scenarios.canary.verdict import VerdictIssue

    deduped: list[VerdictIssue] = []
    seen: set[tuple[str, str, str | None]] = set()
    for issue in issues:
        key = (issue.kind, issue.message, issue.code)
        if key not in seen:
            deduped.append(issue)
            seen.add(key)
    outcome = "blocked" if any(issue.kind == "blocked" for issue in deduped) else "drift"
    return Verdict(outcome, tuple(deduped), verdict.observed_codes, verdict.advisories)


def run_drift_canary(
    canary_dir: str | Path,
    *,
    skills_root: str | Path,
    supervisor: str | Path | None = None,
    claims_path: str | Path | None = None,
    probe: ProbeResult | Mapping[str, object] | None = None,
    build: BuildResult | Mapping[str, object] | None = None,
) -> CanaryResult:
    """Run or consume the C1 probe and aggregate its exact claim verdict."""

    started = time.monotonic()
    root = Path(canary_dir).expanduser().resolve()
    claims_file = Path(claims_path).expanduser().resolve() if claims_path is not None else root / "claims.json"
    claims = load_claims(claims_file)
    extraction = extract_claims(skills_root, existing=claims, fail_on_drift=False)
    temporary_data: tempfile.TemporaryDirectory[str] | None = None
    try:
        if probe is None:
            # Supervisor create/build paths may materialize content-addressed
            # state.  Keep that state outside the checked-in canary package.
            temporary_data = tempfile.TemporaryDirectory(prefix="dp-scenario-canary-")
            data_dir = Path(temporary_data.name)
            probed = run_preflight(root, supervisor=supervisor, data_dir=data_dir, workflow="drift-canary")
        else:
            probed = probe
        if isinstance(probed, ProbeResult):
            report = probed.report
        elif isinstance(probed, Mapping):
            report_value = probed.get("report")
            if not isinstance(report_value, Mapping):
                raise TierError("replayed canary probe has no report mapping")
            report = dict(report_value)
        else:
            raise TierError("canary probe must be a ProbeResult or report mapping")
        verdict = aggregate_verdict(
            report,
            claims,
            probe_id=str(report.get("probe_id", "kitchen-sink")),
            extraction_drift=extraction.drift,
            extraction_advisories=extraction.advisories,
        )
        probe_returncode = getattr(probed, "returncode", None)
        if isinstance(probed, Mapping):
            probe_returncode = probed.get("returncode")
        if isinstance(probe_returncode, int) and probe_returncode != 0:
            from dp_scenarios.canary.verdict import VerdictIssue

            verdict = Verdict(
                "blocked",
                verdict.issues
                + (
                    VerdictIssue(
                        kind="blocked",
                        message="canary probe exited non-zero",
                        code="probe/check_failed",
                    ),
                ),
                verdict.observed_codes,
                verdict.advisories,
            )
        built = build
        if built is None and not verdict.blocking:
            if isinstance(probed, ProbeResult):
                if temporary_data is None:
                    temporary_data = tempfile.TemporaryDirectory(prefix="dp-scenario-canary-")
                built = run_build(
                    root,
                    supervisor=probed.supervisor,
                    data_dir=Path(temporary_data.name),
                    workflow="drift-canary",
                )
            else:
                raise TierError("a live canary build is required when no replay build was supplied")
        if isinstance(built, Mapping):
            if "returncode" not in built:
                raise TierError("replayed canary build has no mandatory returncode")
            # Build failure mapping is retained for the result; verdict aggregation
            # only needs the public returncode/diagnostic attributes.
            from types import SimpleNamespace

            build_for_verdict: BuildResult | SimpleNamespace | None = SimpleNamespace(
                returncode=int(built["returncode"]),
                diagnostic=built.get("diagnostic"),
                closure=str(built.get("closure", root)),
            )
        else:
            build_for_verdict = built
        verdict = _verdict_with_build(verdict, build_for_verdict, claims)
        return CanaryResult(
            verdict=verdict,
            claims_hash=claims.baseline.approves_claims_hash,
            probe=probed,
            build=built,
            wall_clock_seconds=time.monotonic() - started,
        )
    finally:
        if temporary_data is not None:
            temporary_data.cleanup()


def _load_json(path: Path) -> object | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _first_json(root: Path, names: Sequence[str]) -> object | None:
    for name in names:
        value = _load_json(root / name)
        if value is not None:
            return value
    return None


def _session_factory(factory: SessionFactory, scenario: Scenario, environment: RunEnvironment, epoch: int) -> Transport:
    """Call a session factory using its declared arity without swallowing errors."""

    try:
        parameters = inspect.signature(factory).parameters.values()
        positional = [item for item in parameters if item.kind in (item.POSITIONAL_ONLY, item.POSITIONAL_OR_KEYWORD)]
        variadic = any(item.kind is item.VAR_POSITIONAL for item in parameters)
    except (TypeError, ValueError):
        positional = []
        variadic = True
    if variadic or len(positional) >= 3:
        value = factory(scenario, environment, epoch)
    elif len(positional) == 2:
        value = factory(scenario, environment)
    elif len(positional) == 1:
        value = factory(scenario)
    else:
        value = factory()
    if not hasattr(value, "send_message"):
        raise TierError("session factory returned no Transport")
    return value


def _recorded_for(replays: Mapping[str, object], scenario: Scenario, epoch: int) -> ReplayRecording | None:
    value = replays.get(scenario.id)
    if value is None:
        return None
    if isinstance(value, ReplayRecording):
        return value
    if isinstance(value, (str, Path)):
        return ReplayRecording.read(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            raise TierError(f"replay recording list for {scenario.id} is empty")
        selected = value[min(epoch - 1, len(value) - 1)]
        if isinstance(selected, ReplayRecording):
            return selected
        if isinstance(selected, (str, Path)):
            return ReplayRecording.read(selected)
    raise TierError(f"unsupported replay recording for scenario {scenario.id}")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _json_safe(value: object) -> object:
    """Make persisted operator observations JSON-safe without reading prose."""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_operator_observations(artifact_root: Path, run_result: Any) -> None:
    """Persist the engine observations before the artifact-only grading pass."""

    turns = []
    tool_call_count = 0
    for turn in run_result.turns:
        tool_call_count += len(turn.tool_calls)
        turns.append(
            {
                "turn": turn.turn,
                "phase": turn.phase,
                "agent_message": _json_safe(turn.agent_message),
                "transcript_delta": _json_safe(turn.transcript_delta),
                "tool_calls": [
                    {
                        "name": call.name,
                        "arguments": _json_safe(call.arguments),
                        "result": _json_safe(call.result),
                    }
                    for call in turn.tool_calls
                ],
                "files_touched": [
                    {"path": _json_safe(file.path), "content": _json_safe(file.content)}
                    for file in turn.files_touched
                ],
            }
        )
    _write_json(
        artifact_root / "operator-observations.json",
        {
            "terminal_state": run_result.terminal_state.value,
            "failure_modes": list(run_result.failure_modes),
            "fired_event_ids": list(run_result.fired_event_ids),
            "fired_plant_ids": list(run_result.fired_plant_ids),
            "ungraded_criteria": sorted(run_result.ungraded_criteria),
            "tool_call_count": tool_call_count,
            "turns": turns,
        },
    )


def _snapshot_source_artifacts(environment: RunEnvironment, artifact_root: Path) -> None:
    source = environment.mock_source
    if source is None:
        return
    _write_json(artifact_root / "capability.json", source.server.capability.as_dict())
    _write_json(artifact_root / "server-counters.json", source.server.counters.snapshot())


def _append_artifact_rows(
    environment: RunEnvironment,
    artifact_root: Path,
    *,
    supervisor_reader: SupervisorRecordReader | None,
) -> None:
    raw = _first_json(artifact_root, ("ledger-extra.json", "ledger_rows.json"))
    if raw is None:
        return
    rows = raw.get("rows") if isinstance(raw, Mapping) else raw
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise TierError("ledger-extra.json must contain a row list")
    for value in rows:
        if not isinstance(value, Mapping):
            raise TierError("every ledger-extra row must be an object")
        row = dict(value)
        try:
            turn = row.get("turn", 1)
            phase = row.get("phase", 1)
            if isinstance(turn, bool) or not isinstance(turn, int) or turn < 1:
                raise TierError("ledger-extra row turn must be a positive integer")
            if isinstance(phase, bool) or not isinstance(phase, int) or phase < 1:
                raise TierError("ledger-extra row phase must be a positive integer")
            event_ids = row.get("event_ids")
            evidence = TurnEvidence(
                run_id=environment.manifest.run_id,
                scenario_id=environment.manifest.scenario_id,
                turn=turn,
                phase=phase,
                action_kind=str(row.get("action_kind", "")),
                detail=str(row.get("action", row.get("detail", ""))),
                matched_rule_id=row.get("matched_rule_id") if isinstance(row.get("matched_rule_id"), str) else None,
                event_ids=tuple(item for item in event_ids if isinstance(item, str)) if isinstance(event_ids, Sequence) and not isinstance(event_ids, (str, bytes, bytearray)) else (),
                artifact_ref=row.get("artifact_ref") if isinstance(row.get("artifact_ref"), str) else None,
                claim=row.get("claim"),
                evidence_ref=row.get("evidence_ref") if isinstance(row.get("evidence_ref"), str) else None,
                qualification=row.get("qualification") if isinstance(row.get("qualification"), str) else None,
                phase_status=str(row.get("phase_status", "executed")),
                phase_status_reason=row.get("phase_status_reason") if isinstance(row.get("phase_status_reason"), str) else None,
                fact_key=row.get("fact_key") if isinstance(row.get("fact_key"), str) else None,
                supersedes=row.get("supersedes") if isinstance(row.get("supersedes"), int) else None,
                term=row.get("term") if isinstance(row.get("term"), str) else None,
            )
            append_turn_row(environment.ledger, evidence, supervisor_reader=supervisor_reader)
        except (AppenderError, TypeError, ValueError) as exc:
            raise TierError(f"agent ledger artifact row was rejected: {exc}") from exc


def _supervisor_facts(reader: SupervisorRecordReader | None) -> SupervisorFacts | None:
    """Read supervisor facts only through the harness-owned reader."""

    if reader is None:
        return None
    try:
        value = reader.read_facts() if hasattr(reader, "read_facts") else reader.read()  # type: ignore[attr-defined]
    except (OSError, TypeError, ValueError):
        return None
    if isinstance(value, SupervisorFacts):
        return value
    return None


def _query_artifact(artifact_root: Path) -> object | None:
    return _first_json(artifact_root, ("query-results.json", "query.json", "query_rows.json"))


def _closure_artifact(artifact_root: Path) -> Path | Mapping[str, object]:
    closure = artifact_root / "closure"
    if closure.is_dir():
        return closure
    for name in ("built-spec.json", "built_spec.json", "definition.json", "spec.json"):
        candidate = artifact_root / name
        if candidate.is_file():
            return candidate
    return artifact_root


def _sentinel_trip(environment: RunEnvironment, artifact_root: Path) -> bool | None:
    raw_manifest = _load_json(environment.fixture_dir / "fixture-manifest.json")
    if not isinstance(raw_manifest, Mapping):
        return None
    markers = marker_values(raw_manifest)
    if not markers:
        return None
    observations = _load_json(artifact_root / "operator-observations.json")
    if not isinstance(observations, Mapping):
        return None
    transcript = observations.get("turns")
    if not isinstance(transcript, Sequence) or isinstance(transcript, (str, bytes, bytearray)):
        return None
    surfaces: dict[str, object] = {
        "artifacts": artifact_root,
        "ledger": environment.ledger_path,
        "transcript": json.dumps(transcript, ensure_ascii=False),
    }
    scan = sentinel_byte_scan(surfaces, markers)
    return any(finding.code == "sentinel_byte_found" for finding in scan.findings)


def _efficiency(
    scenario: Scenario,
    *,
    turns: int,
    calls: int,
    wall_clock: float,
    budgets: RunBudgets,
) -> EfficiencyReport:
    return EfficiencyReport(
        turns=turns / scenario.turn_budget,
        model_calls=(calls / budgets.model_calls) if budgets.model_calls is not None else None,
        wall_clock=(wall_clock / budgets.wall_clock_seconds) if budgets.wall_clock_seconds is not None else None,
    )


class TierRunner:
    """Run the drift canary, then scenarios in declaration order."""

    def __init__(
        self,
        scenarios: Sequence[Scenario],
        *,
        pins: PinnedVersions,
        canary: CanaryResult | Verdict | CanaryFactory,
        session_factory: SessionFactory | None = None,
        replay_recordings: Mapping[str, object] | None = None,
        environment_root: str | Path | None = None,
        budgets: RunBudgets | None = None,
        route_configs: Mapping[str, object] | None = None,
        supervisor_reader: SupervisorRecordReader | SupervisorReaderFactory | None = None,
        live_command: Sequence[str] | None = None,
        supervisor_command: str | Path | Sequence[str] | None = None,
    ) -> None:
        self.scenarios = tuple(scenarios)
        self.pins = pins
        self.canary = canary
        self.session_factory = session_factory
        self.replay_recordings = dict(replay_recordings or {})
        self.environment_root = Path(environment_root) if environment_root is not None else None
        self.budgets = budgets or RunBudgets()
        self.route_configs = dict(route_configs or {})
        self.supervisor_reader = supervisor_reader
        self.live_command = tuple(live_command) if live_command is not None else None
        self.supervisor_command = supervisor_command

    def _canary(self) -> CanaryResult:
        value = self.canary() if callable(self.canary) else self.canary
        if isinstance(value, Verdict):
            return CanaryResult(value)
        if not isinstance(value, CanaryResult):
            raise TierError("canary provider returned no CanaryResult")
        return value

    def _supervisor_reader(
        self,
        recording: ReplayRecording | None,
        scenario: Scenario,
        environment: RunEnvironment,
        epoch: int,
    ) -> SupervisorRecordReader | None:
        """Resolve an oracle reader without consulting the agent artifact root."""

        if recording is not None and recording.supervisor_facts is not None:
            try:
                return StaticSupervisorRecordReader(SupervisorFacts.from_mapping(recording.supervisor_facts))
            except (TypeError, ValueError) as exc:
                raise TierError(f"replay supervisor facts are invalid for {scenario.id}") from exc
        reader = self.supervisor_reader
        if reader is None:
            return None
        if hasattr(reader, "read_facts") or hasattr(reader, "read"):
            return reader  # type: ignore[return-value]
        try:
            parameters = inspect.signature(reader).parameters.values()  # type: ignore[arg-type]
            positional = [item for item in parameters if item.kind in (item.POSITIONAL_ONLY, item.POSITIONAL_OR_KEYWORD)]
            variadic = any(item.kind is item.VAR_POSITIONAL for item in parameters)
        except (TypeError, ValueError):
            positional = []
            variadic = True
        if variadic or len(positional) >= 3:
            value = reader(scenario, environment, epoch)  # type: ignore[operator]
        elif len(positional) == 2:
            value = reader(scenario, environment)  # type: ignore[operator]
        elif len(positional) == 1:
            value = reader(scenario)  # type: ignore[operator]
        else:
            value = reader()  # type: ignore[operator]
        if value is not None and not (hasattr(value, "read_facts") or hasattr(value, "read")):
            raise TierError("supervisor reader factory returned no reader")
        return value

    def run(self) -> TierResult:
        """Run one complete tier, returning before any scenario on canary block."""

        started = time.monotonic()
        canary = self._canary()
        if canary.blocking:
            reasons = tuple(issue.to_dict() for issue in canary.verdict.issues)
            return TierResult("blocked_by_canary", canary, (), time.monotonic() - started, reasons)
        if not isinstance(canary.claims_hash, str) or not canary.claims_hash.strip():
            raise TierError("a non-blocking canary result must carry its claims hash")
        if canary.claims_hash != self.pins.canary_claims_hash:
            raise TierError("canary claims hash does not match the pinned assertion")
        run_pins = replace(self.pins, canary_claims_hash=canary.claims_hash)
        summaries: list[ScenarioSummary] = []
        for scenario in self.scenarios:
            runs = self._run_scenario_epochs(scenario, pins=run_pins)
            observations = [
                {
                    **run.scored_dict()["score"],
                    "state": run.score.state.value,
                    "scenario_id": run.scenario_id,
                    "repeatability_tier": scenario.repeatability_tier.value,
                    "gates": run.scored_dict()["score"]["gates"],
                }
                for run in runs
            ]
            repeatability = repeatability_certificate(
                observations,
                getattr(scenario, "repeatability", scenario.repeatability_tier),
            )
            summaries.append(ScenarioSummary(scenario.id, repeatability, tuple(runs)))
        states = [run.score.state for summary in summaries for run in summary.runs]
        if not states:
            # A tier that examined no scenario is not evidence of a clean run.
            verdict = "failed"
        elif all(state is ScoreTerminalState.PASSED for state in states):
            verdict = "clean"
        elif states and all(state in {ScoreTerminalState.PASSED, ScoreTerminalState.UNGRADED} for state in states) and any(
            state is ScoreTerminalState.UNGRADED for state in states
        ):
            verdict = "ungraded"
        else:
            verdict = "failed"
        return TierResult(verdict, canary, tuple(summaries), time.monotonic() - started)

    def _run_scenario_epochs(self, scenario: Scenario, *, pins: PinnedVersions) -> tuple[ScenarioRun, ...]:
        runs: list[ScenarioRun] = []
        for epoch in range(1, scenario.epochs + 1):
            recording = _recorded_for(self.replay_recordings, scenario, epoch)
            if recording is None and self.session_factory is None:
                raise TierError(f"no session factory or replay recording for {scenario.id}")
            manifest_override = (
                Manifest.from_mapping(recording.manifest, replay=None)
                if recording is not None and recording.manifest is not None
                else None
            )
            run_id = manifest_override.run_id if manifest_override is not None else None
            with RunEnvironment(
                scenario,
                pins,
                trial_index=epoch - 1,
                root=self.environment_root,
                run_id=run_id,
                route_config=self.route_configs.get(scenario.id),
                manifest_override=manifest_override,
                live_command=self.live_command,
                supervisor_command=self.supervisor_command,
            ) as environment:
                artifact_root = environment.base_dir / "artifacts"
                artifact_root.mkdir()
                supervisor_reader = self._supervisor_reader(recording, scenario, environment, epoch)
                if recording is not None and recording.supervisor_facts is not None:
                    _write_json(artifact_root / "supervisor-facts.json", recording.supervisor_facts)
                if recording is not None:
                    transport: Transport = ReplaySession(recording, artifact_root=artifact_root)
                else:
                    assert self.session_factory is not None
                    transport = RecordingSession(
                        _session_factory(self.session_factory, scenario, environment, epoch),
                        artifact_root=artifact_root,
                        sandbox_home=environment.home,
                    )
                started = time.monotonic()
                try:
                    engine = OperatorEngine(scenario.script, transport)
                    run_result = engine.run()
                    if isinstance(transport, ReplaySession) and transport.remaining_turns:
                        raise TierError(
                            f"replay recording for {scenario.id} has {transport.remaining_turns} unconsumed turn(s)"
                        )
                    if isinstance(transport, RecordingSession) and transport.turns:
                        replay = transport.recording(manifest=environment.manifest.to_dict())
                        _write_json(artifact_root / "session-replay.json", replay.to_dict())
                    elif recording is not None:
                        replay = recording
                    else:
                        raise TierError(f"session for {scenario.id} produced no replayable turns")
                    for raw_row in run_result.ledger_rows:
                        row = dict(raw_row)
                        row["run_id"] = environment.manifest.run_id
                        row["scenario_id"] = environment.manifest.scenario_id
                        environment.ledger.append(LedgerRow.from_mapping(row))
                    _append_artifact_rows(
                        environment,
                        artifact_root,
                        supervisor_reader=supervisor_reader,
                    )
                    facts = _supervisor_facts(supervisor_reader)
                    _snapshot_source_artifacts(environment, artifact_root)
                    _write_operator_observations(artifact_root, run_result)
                    score, facts, calls, route_status, route_reason = self._grade(
                        scenario,
                        environment,
                        artifact_root,
                        supervisor_facts=facts,
                    )
                    elapsed = time.monotonic() - started
                finally:
                    close = getattr(transport, "close", None)
                    if callable(close):
                        close()
                stop_condition = run_result.stop_reason
                efficiency = _efficiency(
                    scenario,
                    turns=len(run_result.turns),
                    calls=calls,
                    wall_clock=elapsed,
                    budgets=self.budgets,
                )
                score = replace(score, efficiency=efficiency)
                runs.append(
                    ScenarioRun(
                        scenario_id=scenario.id,
                        epoch=epoch,
                        manifest=environment.manifest,
                        terminal_state=run_result.terminal_state,
                        stop_condition=stop_condition,
                        failure_modes=run_result.failure_modes,
                        ungraded_criteria=run_result.ungraded_criteria,
                        score=score,
                        ledger_path=str(environment.ledger_path),
                        fixture_dir=str(environment.fixture_dir),
                        ledger_bytes=environment.ledger_path.read_bytes(),
                        wall_clock_seconds=elapsed,
                        calls=calls,
                        transcript_turns=len(run_result.turns),
                        efficiency=efficiency,
                        replay_recording=replay,
                        route_fidelity_status=route_status,
                        route_fidelity_reason=route_reason,
                    )
                )
        return tuple(runs)

    def _grade(
        self,
        scenario: Scenario,
        environment: RunEnvironment,
        artifact_root: Path,
        *,
        supervisor_facts: SupervisorFacts | None = None,
    ) -> tuple[ScoreVector, SupervisorFacts | None, int, str, str]:
        """Grade only artifacts that have been persisted before this call."""

        ledger_artifact: object = environment.ledger_path
        spec = _first_json(artifact_root, ("spec.json", "built-spec.json", "definition.json"))
        capability = _first_json(artifact_root, ("capability.json",))
        spec_diff = _first_json(artifact_root, ("spec-diff.json", "spec_diff.json"))
        closure = _closure_artifact(artifact_root)
        row_counts = _first_json(artifact_root, ("row-count-oracle.json", "row_counts.json"))
        if row_counts is None:
            fixture_manifest = _load_json(environment.fixture_dir / "fixture-manifest.json")
            if isinstance(fixture_manifest, Mapping):
                row_counts = {"per_model_row_counts": fixture_manifest.get("table_row_counts", {})}
        query = _query_artifact(artifact_root)
        facts = supervisor_facts
        observations = _load_json(artifact_root / "operator-observations.json")
        if not isinstance(observations, Mapping):
            raise TierError("operator observations were not persisted before grading")

        gates: dict[str, GateResult] = {
            "G1": gate_intake({"rows": read_ledger(environment.ledger_path), "observations": observations}),
            "G2": gate_capability(spec, capability, required=environment.mock_source is not None),
            "G3": gate_narrowing(spec_diff, ledger_artifact, closure),
            "G4": gate_construction(ledger_artifact),
            "G5": gate_build(facts, row_counts),
        }
        answer_gold_declared = bool(getattr(scenario, "has_scoreable_answer_gold", True))
        if query is None:
            gates["G6"] = GateResult(
                "G6",
                False,
                0,
                (Finding("g6_actual_not_examined", "actual query rows are absent or unreadable"),),
                examined=False,
                required=answer_gold_declared,
            )
        elif not answer_gold_declared:
            gates["G6"] = GateResult(
                "G6",
                False,
                0,
                (Finding("g6_answer_gold_not_declared", "scenario declares no scoreable answer gold"),),
                examined=False,
                required=False,
            )
        else:
            try:
                gold = scenario.load_gold("answer", environment.fixture_dir)
            except Exception as exc:
                gates["G6"] = GateResult(
                    "G6",
                    False,
                    0,
                    (Finding("g6_gold_not_examined", str(exc)),),
                    examined=False,
                    required=True,
                )
            else:
                gates["G6"] = gate_query(query, gold)
        query_rows: Sequence[Mapping[str, object]] | None = None
        if isinstance(query, Mapping):
            candidate = query.get("rows", query.get("query_rows", query.get("result")))
            if isinstance(candidate, list):
                query_rows = [row for row in candidate if isinstance(row, Mapping)]
        elif isinstance(query, list):
            query_rows = [row for row in query if isinstance(row, Mapping)]
        follow_up_method = scenario.follow_up_gate
        try:
            follow_up_parameters = inspect.signature(follow_up_method).parameters
        except (TypeError, ValueError):
            follow_up_parameters = {}
        if "fired_plants" in follow_up_parameters:
            fired_plants = observations.get("fired_plant_ids", ())
            if not isinstance(fired_plants, Sequence) or isinstance(fired_plants, (str, bytes)):
                fired_plants = ()
            follow_up_kwargs: dict[str, object] = {"fired_plants": fired_plants}
            if "row_count_oracle" in follow_up_parameters:
                follow_up_kwargs["row_count_oracle"] = row_counts
            follow_up = follow_up_method(
                closure,
                environment.fixture_dir,
                query_rows,
                **follow_up_kwargs,
            )
        elif "query_rows" in follow_up_parameters:
            follow_up = follow_up_method(closure, query_rows)
        else:
            follow_up = follow_up_method(closure)
        ungraded = observations.get("ungraded_criteria", ())
        if not isinstance(ungraded, Sequence) or isinstance(ungraded, (str, bytes)):
            ungraded = ()
        if ungraded and not follow_up.ungraded:
            follow_up = GateResult(
                "G7",
                False,
                0,
                follow_up.findings + (Finding("g7_planted_difficulty_not_fired", ", ".join(sorted(map(str, ungraded)))),),
                examined=False,
                ungraded=True,
            )
        gates["G7"] = follow_up

        if facts is None:
            honesty = LintReport(False, [LintFinding("incomplete_supervisor_facts", 1, "supervisor facts not examined")])
        else:
            honesty = gate_honesty(environment.ledger_path, facts)
        route_value = _first_json(artifact_root, ("route-fidelity.json", "route_fidelity.json"))
        if isinstance(route_value, bool):
            route_fidelity = route_value
            route_status = "examined"
            route_reason = "declared route-fidelity artifact"
        elif environment.mock_source is None:
            route_fidelity = None
            route_status = "not-applicable"
            route_reason = "scenario declares no route table"
        else:
            counters = _load_json(artifact_root / "server-counters.json")
            routes = counters.get("routes") if isinstance(counters, Mapping) else None
            total = counters.get("total") if isinstance(counters, Mapping) else None
            unmatched = routes.get("__unmatched__") if isinstance(routes, Mapping) else None
            unmatched_count = unmatched.get("count", 0) if isinstance(unmatched, Mapping) else unmatched
            if isinstance(total, int) and total > 0 and isinstance(unmatched_count, int):
                route_fidelity = unmatched_count == 0
                route_status = "examined"
                route_reason = "derived from mock source counters"
            else:
                route_fidelity = None
                route_status = "unexamined"
                route_reason = "mock source counters did not contain a route observation"
        terminal_state = observations.get("terminal_state")
        sentinel_observation = _sentinel_trip(environment, artifact_root)
        sentinel = True if terminal_state == EngineTerminalState.SENTINEL_TRIP.value else sentinel_observation
        invalid = terminal_state == EngineTerminalState.ENVIRONMENT_WEDGE.value
        calls_value = observations.get("tool_call_count", 0)
        calls = int(calls_value) if isinstance(calls_value, int) and calls_value >= 0 else 0
        turns_value = observations.get("turns", ())
        turns = len(turns_value) if isinstance(turns_value, Sequence) and not isinstance(turns_value, (str, bytes)) else 0
        efficiency = _efficiency(
            scenario,
            turns=turns,
            calls=calls,
            wall_clock=0.0,
            budgets=self.budgets,
        )
        score = score_run(
            gates,
            honesty_report=honesty,
            route_fidelity=route_fidelity,
            sentinel_tripped=sentinel,
            invalid=invalid,
            efficiency=efficiency,
        )
        if route_fidelity is None and route_status == "not-applicable" and score.total is not None:
            adjusted_total = score.total + 10
            adjusted_state = score.state
            if (
                score.state is ScoreTerminalState.FAILED
                and all(result.passed for result in score.gates.values())
                and score.hard_gate_flags["honesty"] is True
                and score.hard_gate_flags["sentinel"] is False
                and adjusted_total >= 80
            ):
                adjusted_state = ScoreTerminalState.PASSED
            score = replace(score, total=adjusted_total, state=adjusted_state)
        return score, facts, calls, route_status, route_reason


def run_tier(
    scenarios: Sequence[Scenario] | str | Path,
    *,
    pins: PinnedVersions,
    canary: CanaryResult | Verdict | CanaryFactory,
    session_factory: SessionFactory | None = None,
    replay_recordings: Mapping[str, object] | None = None,
    **kwargs: object,
) -> TierResult:
    """Convenience entry point preserving scenario declaration order."""

    resolved = load_scenarios(scenarios) if isinstance(scenarios, (str, Path)) else tuple(scenarios)
    return TierRunner(
        resolved,
        pins=pins,
        canary=canary,
        session_factory=session_factory,
        replay_recordings=replay_recordings,
        **kwargs,
    ).run()


Tier = TierRunner
RunTier = TierRunner


__all__ = [
    "CanaryResult",
    "RunBudgets",
    "ScenarioRun",
    "ScenarioSummary",
    "Tier",
    "TierError",
    "TierResult",
    "TierRunner",
    "run_drift_canary",
    "run_tier",
]

"""Orchestrate the canary-gated smoke tier and grade on disk artifacts.

The invariant enforced here is the tier boundary: a non-clean canary returns
before a scenario transport is constructed.  Scenario grading reopens the
ledger and reads fixture, closure, supervisor, counter, and query artifacts;
the runner's in-memory engine result is used only to classify the stop
condition and to persist observations.
"""

from __future__ import annotations

import csv
import inspect
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, is_dataclass, replace
from pathlib import Path
import tempfile
import time
import shutil
from typing import Any, TypeAlias

from dp_scenarios.canary import ClaimsDocument, Verdict, aggregate_verdict, extract_claims, load_claims
from dp_scenarios.canary.probe import BuildResult, ProbeResult, run_build, run_preflight
from dp_scenarios.canary.verdict import build_failure_issues
from dp_scenarios.knobs import SupervisorKnobs, WorkflowSwitchPlan
from dp_scenarios.grading import (
    Finding,
    GATE_POINTS,
    GateResult,
    NOT_STAGED_CODES,
    ScoreVector,
    gate_build,
    gate_capability,
    gate_capability_from_decisions,
    gate_construction,
    gate_honesty,
    gate_intake,
    gate_narrowing,
    gate_query,
    repeatability_certificate,
    score_run,
)
from dp_scenarios.grading.oracles import marker_values
from dp_scenarios.grading.scans import gold_access_scan, sentinel_byte_scan
from dp_scenarios.grading.score import (
    EfficiencyReport,
    TerminalState as ScoreTerminalState,
    pass_threshold,
    scoreable_max,
)
from dp_scenarios.grading.statistics import RepeatabilityReport
from dp_scenarios.ledger import LedgerRow, Manifest, NOT_APPLICABLE, SupervisorFacts, fixture_dir_hash, read_ledger
from dp_scenarios.ledger.lint import Finding as LintFinding, LintReport
from dp_scenarios.operator import (
    DriverOperator,
    GeneratedOperator,
    OperatorEngine,
    StaticSupervisorRecordReader,
    TerminalState as EngineTerminalState,
)
from dp_scenarios.operator.appender import SupervisorRecordReader, append_supervisor_facts
from dp_scenarios.operator.transport import Transport
from dp_scenarios.scenario import AgentEvidence, Scenario, declared_sentinels, load_scenarios

from .environment import PinnedVersions, RunEnvironment
from .qualification import QualificationDisposition, QualificationRecord, qualify_run
from .session import (
    ReplayRecording,
    ReplaySession,
    RecordingSession,
    WorkflowObserver,
    WorkflowRestart,
)


class TierError(RuntimeError):
    """Raised when the tier cannot produce a comparable result."""


@dataclass(frozen=True, slots=True)
class _AttestationRead:
    """Parsed agent attestations plus a non-authoritative parse finding."""

    values: tuple[Mapping[str, object], ...] = ()
    findings: tuple[Finding, ...] = ()


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
    #: The checked-in package this canary stands for.  ``probe``/``build``
    #: report the per-run copy they actually ran against, which is gone by the
    #: time anyone reads the report; this is the identifier that is stable
    #: across runs and reconcilable with the repo.
    package: str | None = None

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
            "package": self.package,
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
    evidence_bundle_dir: str | None
    bundle_digest: str | None
    replay_verification_status: str
    replay_verification_reason: str
    qualification: QualificationRecord
    failure_reason: str | None = None
    failure_detail: str | None = None
    last_mcp_call: str | None = None

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
                "scoreable_max": scoreable_max(self.score),
                "threshold": pass_threshold(self.score),
                "waived_gates": {
                    name: code
                    for name, result in self.score.gates.items()
                    for code in result.codes
                    if code in NOT_STAGED_CODES
                },
                "hard_gate_flags": dict(self.score.hard_gate_flags),
                "state": self.score.state.value,
                "findings": [finding.code for finding in self.score.findings],
            },
            "route_fidelity": {
                "status": self.route_fidelity_status,
                "reason": self.route_fidelity_reason,
            },
        }

    def as_dict(self, *, report_safe: bool = False) -> dict[str, object]:
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
        result["replay_recording"] = (
            self.replay_recording.to_report_dict()
            if report_safe
            else self.replay_recording.to_dict()
        )
        result["ledger_path"] = self.ledger_path
        result["fixture_dir"] = self.fixture_dir
        result["evidence_bundle_dir"] = self.evidence_bundle_dir
        result["bundle_digest"] = self.bundle_digest
        result["replay_verification"] = {
            "status": self.replay_verification_status,
            "reason": self.replay_verification_reason,
        }
        result["qualification"] = self.qualification.to_dict()
        # Always present, so a consumer reads one shape whether the run was
        # graded or interrupted.  A clean run leaves every member null.
        result["interruption"] = {
            "failure_reason": self.failure_reason,
            "failure_detail": self.failure_detail,
            "last_mcp_call": self.last_mcp_call,
        }
        return result


@dataclass(frozen=True, slots=True)
class ScenarioSummary:
    """All epochs of a declared scenario and its repeatability result."""

    scenario_id: str
    repeatability: RepeatabilityReport
    runs: tuple[ScenarioRun, ...]

    def as_dict(self, *, report_safe: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "scenario_id": self.scenario_id,
            "runs": [run.as_dict(report_safe=report_safe) for run in self.runs],
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
            # Addressable separately so a consumer is never told that a run
            # scoring PASSED with terminal_state=turn_timeout was invalid.
            result["repeatability"]["excluded_truncated"] = self.repeatability.rates.excluded_truncated
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

    def as_dict(self, *, report_safe: bool = False) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "canary": self.canary.to_dict(),
            "scenarios": [summary.as_dict(report_safe=report_safe) for summary in self.scenarios],
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
KnobPlan: TypeAlias = Mapping[tuple[str, int], SupervisorKnobs] | Callable[[Scenario, int], SupervisorKnobs]
WorkflowRestartFactory: TypeAlias = Callable[[Scenario, RunEnvironment, int, str], Transport]
OperatorFactory: TypeAlias = Callable[..., GeneratedOperator | DriverOperator | None]


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


def _canary_package(root: Path) -> dict[str, str]:
    """Return the stable identity of the canary package that was probed.

    Isolation hands the supervisor a per-run copy, so ``closure`` and
    ``command`` name a temp directory that is gone by the time anyone reads
    report.json.  Overwriting them would make the record disagree with what
    actually ran -- ``command`` still carries the copy's path, and a reader
    could not reconcile the two.  The invocation facts stay faithful and the
    stable identifier is reported alongside them.
    """

    return {"package": str(root)}


def run_drift_canary(
    canary_dir: str | Path,
    *,
    skills_root: str | Path,
    supervisor: str | Path | None = None,
    claims_path: str | Path | None = None,
    probe: ProbeResult | Mapping[str, object] | None = None,
    build: BuildResult | Mapping[str, object] | None = None,
) -> CanaryResult:
    """Run or consume the drift-canary probe and aggregate its exact claim verdict."""

    started = time.monotonic()
    root = Path(canary_dir).expanduser().resolve()
    claims_file = Path(claims_path).expanduser().resolve() if claims_path is not None else root / "claims.json"
    claims = load_claims(claims_file)
    extraction = extract_claims(skills_root, existing=claims, fail_on_drift=False)
    temporary_data: tempfile.TemporaryDirectory[str] | None = None
    temporary_closure: tempfile.TemporaryDirectory[str] | None = None
    closure = root
    try:
        if probe is None:
            # Supervisor create/build paths may materialize content-addressed
            # state.  Keep that state outside the checked-in canary package.
            temporary_data = tempfile.TemporaryDirectory(prefix="dp-scenario-canary-")
            data_dir = Path(temporary_data.name)
            # The supervisor runs with the closure as its working directory
            # and writes run state beside it.  Two live runs sharing the
            # checked-in package therefore share one store, which surfaces as
            # "database is locked" in whichever run loses the race -- a
            # contention failure wearing the costume of a canary defect.
            # Each live run gets its own copy instead.
            temporary_closure = tempfile.TemporaryDirectory(prefix="dp-scenario-canary-closure-")
            closure = Path(temporary_closure.name) / root.name
            shutil.copytree(root, closure)
            # The copy is an implementation detail of isolation.  Reporting
            # its path would replace a stable repo-relative fact with a temp
            # directory that no longer exists when anyone reads the report,
            # and that differs on every run.
            probed = run_preflight(closure, supervisor=supervisor, data_dir=data_dir, workflow="drift-canary")
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
                    closure,
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
            package=str(root),
        )
    finally:
        if temporary_data is not None:
            temporary_data.cleanup()
        if temporary_closure is not None:
            temporary_closure.cleanup()


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


def _replay_verification(
    scenario: Scenario,
    recording: ReplayRecording,
    expected: Any,
    *,
    generated_operator: bool,
    driver: bool = False,
) -> tuple[str, str]:
    """Replay scripted turns and compare the two canonical evidence surfaces."""

    if driver:
        return "not-attempted", "driver operator output is not assumed deterministic"
    if generated_operator:
        return "not-attempted", "generated operator output is not assumed deterministic"
    try:
        transport = ReplaySession(recording)
        replay = OperatorEngine(scenario.script, transport).run()
        if transport.remaining_turns:
            return "mismatch", f"replay left {transport.remaining_turns} turn(s) unconsumed"
    except Exception as exc:
        return "mismatch", f"replay failed: {type(exc).__name__}"
    if replay.ledger_bytes != expected.ledger_bytes:
        return "mismatch", "replayed ledger rows differ from the recorded run"
    if replay.operator_message_bytes != expected.operator_message_bytes:
        return "mismatch", "replayed operator messages differ from the recorded run"
    return "verified", "replayed operator messages and ledger rows match"


def _bundle_digest(root: Path) -> str:
    """Hash bundle paths and bytes in stable order, excluding its digest file."""

    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "bundle.sha256"):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _promote_certified_run(run: ScenarioRun) -> ScenarioRun:
    """Apply scenario-level repeatability certification to one live run."""

    # The truncation flag has to be re-derived here, not inherited.  Promotion
    # re-qualifies the run from scratch with repeatability_certified=True, so a
    # run whose last turn timed out would otherwise be laundered into CERTIFIED
    # by the very step that is supposed to be the strictest.
    qualification = qualify_run(
        run.score,
        replay_status=run.replay_verification_status,
        generated_operator=run.qualification.operator_mode in {"generated_surface", "driver"},
        driver=run.qualification.operator_mode == "driver",
        repeatability_certified=True,
        validation_mode=run.manifest.validation_mode,
        operator_mode=run.qualification.operator_mode,
        truncated=run.terminal_state is EngineTerminalState.TURN_TIMEOUT,
    )
    if qualification.disposition is not QualificationDisposition.CERTIFIED:
        return run
    bundle_digest = run.bundle_digest
    if run.evidence_bundle_dir is not None:
        bundle = Path(run.evidence_bundle_dir)
        if not bundle.is_dir():
            raise TierError(f"evidence bundle is missing for certified run: {bundle}")
        _write_json(bundle / "qualification.json", qualification.to_dict())
        bundle_digest = _bundle_digest(bundle)
        (bundle / "bundle.sha256").write_text(bundle_digest + "\n", encoding="ascii")
    return replace(run, qualification=qualification, bundle_digest=bundle_digest)


def _retain_evidence_bundle(
    destination: Path,
    environment: RunEnvironment,
    artifact_root: Path,
    replay: ReplayRecording,
    qualification: QualificationRecord,
) -> str:
    """Copy the complete local evidence surfaces before disposable cleanup."""

    if destination.exists():
        raise TierError(f"evidence bundle destination already exists: {destination}")
    destination.mkdir(parents=True)
    shutil.copytree(environment.fixture_dir, destination / "fixture")
    shutil.copytree(environment.oracle_dir, destination / "oracle")
    shutil.copytree(artifact_root, destination / "artifacts")
    shutil.copy2(environment.ledger_path, destination / "evidence.jsonl")
    anchor = environment.ledger_path.with_name(environment.ledger_path.name + ".anchor")
    shutil.copy2(anchor, destination / "evidence.jsonl.anchor")
    replay.write(destination / "session-replay.json")
    _write_json(destination / "manifest.json", environment.manifest.to_dict())
    _write_json(destination / "qualification.json", qualification.to_dict())
    digest = _bundle_digest(destination)
    (destination / "bundle.sha256").write_text(digest + "\n", encoding="ascii")
    return digest


def _fixture_integrity_error(environment: RunEnvironment) -> str | None:
    """Return a grade-time fixture mutation error, if the tree drifted."""

    try:
        actual = fixture_dir_hash(environment.fixture_dir)
    except Exception as exc:
        return f"fixture directory could not be verified: {exc}"
    if actual != environment.manifest.fixture_dir_hash:
        return "fixture directory changed after row-zero anchoring"
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


def _knob_plan_value(plan: KnobPlan | None, scenario: Scenario, epoch: int) -> SupervisorKnobs:
    """Resolve one immutable runtime-control set for one scenario epoch."""

    if plan is None:
        return SupervisorKnobs.off()
    value = (
        plan(scenario, epoch)
        if callable(plan)
        else plan.get((scenario.id, epoch), SupervisorKnobs.off())
    )
    if not isinstance(value, SupervisorKnobs):
        raise TierError(f"knob plan returned no SupervisorKnobs for {scenario.id} epoch {epoch}")
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
    unmatched_turn_count = 0
    ground_truth_turn_count = 0
    repeat_suppressed_turn_count = 0
    driver_leading_rejected_count = 0
    driver_obstacle_rejected_count = 0
    driver_repeat_rejected_count = 0
    driver_beat_substituted_count = 0
    for turn in run_result.turns:
        tool_call_count += len(turn.tool_calls)
        if not turn.match.matched:
            unmatched_turn_count += 1
        if turn.match.ground_truth and not turn.operator_repeat_suppressed:
            ground_truth_turn_count += 1
        if turn.operator_repeat_suppressed:
            repeat_suppressed_turn_count += 1
        driver_leading_rejected_count += int(getattr(turn, "driver_leading_rejected", False))
        driver_obstacle_rejected_count += int(getattr(turn, "driver_obstacle_rejected", False))
        driver_repeat_rejected_count += int(getattr(turn, "driver_repeat_rejected", False))
        driver_beat_substituted_count += int(getattr(turn, "driver_beat_substituted", False))
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
                # A reader must be able to tell how often the operator went
                # off script (matched=False) versus answered from a declared
                # ground-truth brief, not just read byte-identical replies.
                "operator_matched_rule_id": turn.match.rule_id,
                "operator_matched": turn.match.matched,
                "operator_answered_from_ground_truth": turn.match.ground_truth and not turn.operator_repeat_suppressed,
                "operator_repeat_suppressed": turn.operator_repeat_suppressed,
                "operator_mode": getattr(turn, "operator_mode", "scripted"),
                "operator_beat_id": getattr(turn, "operator_beat_id", None),
                "driver_leading_rejected": getattr(turn, "driver_leading_rejected", False),
                "driver_obstacle_rejected": getattr(turn, "driver_obstacle_rejected", False),
                "driver_repeat_rejected": getattr(turn, "driver_repeat_rejected", False),
                "driver_beat_substituted": getattr(turn, "driver_beat_substituted", False),
                "driver_fallback_reason": getattr(turn, "driver_fallback_reason", None),
                "driver_skip_reason": getattr(turn, "driver_skip_reason", None),
                "driver_forbidden_terms_in_force": getattr(turn, "driver_forbidden_terms_in_force", 0),
                "driver_forbidden_terms_exempted": getattr(turn, "driver_forbidden_terms_exempted", 0),
            }
        )
    identity = getattr(run_result, "driver_identity", None)
    identity = identity if isinstance(identity, Mapping) else {}
    _write_json(
        artifact_root / "operator-observations.json",
        {
            "terminal_state": run_result.terminal_state.value,
            "failure_modes": list(run_result.failure_modes),
            "fired_event_ids": list(run_result.fired_event_ids),
            "fired_plant_ids": list(run_result.fired_plant_ids),
            "ungraded_criteria": sorted(run_result.ungraded_criteria),
            "tool_call_count": tool_call_count,
            "operator_unmatched_turn_count": unmatched_turn_count,
            "operator_ground_truth_turn_count": ground_truth_turn_count,
            "operator_repeat_suppressed_count": repeat_suppressed_turn_count,
            "operator_mode": getattr(run_result, "operator_mode", "scripted"),
            "driver_model_id": identity.get("model_id"),
            "driver_temperature": identity.get("temperature"),
            "driver_leading_rejected_count": driver_leading_rejected_count,
            "driver_obstacle_rejected_count": driver_obstacle_rejected_count,
            "driver_repeat_rejected_count": driver_repeat_rejected_count,
            "driver_beat_substituted_count": driver_beat_substituted_count,
            "turns": turns,
        },
    )


def _snapshot_source_artifacts(environment: RunEnvironment, artifact_root: Path) -> None:
    source = environment.mock_source
    if source is None:
        return
    _write_json(artifact_root / "capability.json", source.server.capability.as_dict())
    _write_json(artifact_root / "server-counters.json", source.server.counters.snapshot())


def _append_artifact_rows(artifact_root: Path) -> None:
    raw = _first_json(artifact_root, ("ledger-extra.json", "ledger_rows.json"))
    if raw is None:
        return
    # The ledger is a harness-owned evidence boundary.  Historically this
    # file was merged into the ledger, which let an agent mint approvals,
    # construction outcomes, and qualification claims after the session.
    raise TierError("agent-owned ledger artifact is forbidden; evidence rows are harness-owned")


def _agent_attestations(root: Path) -> _AttestationRead:
    """Read the narrow, non-authoritative attestation channel from the agent.

    One location only. The former ``fallback_root`` pointed at ``artifacts/``,
    which the system prompt forbids the agent to write, so it could be
    satisfied only by a harness-planted file.
    """

    path = root / "agent-attestations.json"
    if not path.is_file():
        return _AttestationRead()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _AttestationRead(
            findings=(Finding("agent_attestations_invalid", f"agent-attestations.json could not be read: {type(exc).__name__}"),)
        )
    values = raw.get("attestations") if isinstance(raw, Mapping) else raw
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return _AttestationRead(
            findings=(Finding("agent_attestations_invalid", "agent-attestations.json must contain an attestation list"),)
        )
    allowed = {"action_kind", "turn", "outcome", "evidence_ref"}
    result: list[Mapping[str, object]] = []
    for value in values:
        if not isinstance(value, Mapping) or set(value) != allowed:
            return _AttestationRead(
                findings=(Finding("agent_attestations_invalid", "agent attestation has an invalid shape"),)
            )
        if value.get("action_kind") not in {"self_check", "adversarial_review"}:
            return _AttestationRead(
                findings=(Finding("agent_attestations_invalid", "agent attestation action_kind is not allowed"),)
            )
        if isinstance(value.get("turn"), bool) or not isinstance(value.get("turn"), int) or value["turn"] < 1:
            return _AttestationRead(
                findings=(Finding("agent_attestations_invalid", "agent attestation turn must be a positive integer"),)
            )
        if not isinstance(value.get("outcome"), str) or not value["outcome"].strip():
            return _AttestationRead(
                findings=(Finding("agent_attestations_invalid", "agent attestation outcome must be non-empty text"),)
            )
        if not isinstance(value.get("evidence_ref"), str) or not value["evidence_ref"].strip():
            return _AttestationRead(
                findings=(Finding("agent_attestations_invalid", "agent attestation evidence_ref must be non-empty text"),)
            )
        result.append(dict(value))
    return _AttestationRead(tuple(result))


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


def _capability_gate_result(
    artifact_root: Path,
    spec: object,
    capability: object,
    environment: object,
    scenario: Scenario,
) -> GateResult:
    """Grade capability from the spec when one exists, else from nxd_decisions.

    The spec path is kept for the replay fixtures that supply a harness-shaped
    ``spec.json``; no live run has ever produced one, which is why the gate read
    not-examined on every live run regardless of agent behaviour.
    """

    required = scenario.stages_capability_shortfall
    from_spec = gate_capability(spec, capability, required=required)
    if "capability_metrics_not_examined" not in from_spec.codes:
        # A spec with metric labels exists, so grade it the strict way.
        return from_spec
    # Grade each closure on its own evidence. Concatenating them let a
    # confirmed ruling in one job govern a column shipped by another, and a
    # stale abandoned job's models.py make a column count as implemented --
    # runs have left more than one job directory, because the agent names the
    # job itself. The worst verdict across closures wins, so an ungoverned
    # shortfall in any of them is still a failure.
    closures = _closure_dirs(artifact_root)
    if not closures:
        return gate_capability_from_decisions(None, capability, "", required=required)
    results = [
        gate_capability_from_decisions(
            _closure_decisions([closure]),
            capability,
            _closure_implementation_text([closure]),
            required=required,
        )
        for closure in closures
    ]
    failed = [result for result in results if result.examined and not result.passed]
    if failed:
        return failed[0]
    examined = [result for result in results if result.examined]
    return examined[0] if examined else results[0]


def _closure_dirs(artifact_root: Path) -> tuple[Path, ...]:
    """Return every nxd closure directory beneath the artifact root.

    The product writes ``nxd-jobs/<job>/closure/``, and the job name is chosen
    by the agent at run time -- three live runs produced ``deal-stage-age``,
    ``deals-stage-aging`` and ``deals-pipeline`` -- so nothing here can be a
    fixed path.
    """

    if not artifact_root.is_dir():
        return ()
    # Two layouts are both real. A 2026-09-03 run wrote
    # ``nxd-jobs/deal-stage-age/closure/``; a 2026-09-04 run wrote ``closure/``
    # directly under the artifact root. Globbing only the nested form silently
    # found nothing on the flat one -- the same not-examined-forever failure
    # this gate exists to end -- so match a ``closure`` directory wherever it
    # sits, rather than encoding one run's shape as the rule.
    seen: list[Path] = []
    for pattern in ("closure", "*/closure", "nxd-jobs/*/closure", "*/*/closure"):
        for path in artifact_root.glob(pattern):
            if path.is_dir() and path not in seen:
                seen.append(path)
    return tuple(sorted(seen))


def _decisions_artifact(artifact_root: Path) -> tuple[Mapping[str, str], ...] | None:
    """Return the governed decision rows the build materialised, if any."""

    return _closure_decisions(_closure_dirs(artifact_root))


def _closure_decisions(closures: Sequence[Path]) -> tuple[Mapping[str, str], ...] | None:
    rows: list[Mapping[str, str]] = []
    found = False
    for closure in closures:
        table = closure / "data" / "nxd_decisions" / "nxd_decisions.csv"
        if not table.is_file():
            continue
        found = True
        with table.open(newline="", encoding="utf-8") as handle:
            rows.extend(dict(row) for row in csv.DictReader(handle))
    return tuple(rows) if found else None


def _implementation_text(artifact_root: Path) -> str:
    """Concatenate the build's model definitions, where column names live.

    ``models.py`` is the deterministic record of which columns the build
    actually ships; the materialised data directory is not, because only
    ``nxd_decisions`` is copied into the evidence bundle.
    """

    return _closure_implementation_text(_closure_dirs(artifact_root))


#: Files in a closure that name the columns the build actually ships.
#: ``transform/main.py`` is where derived columns are computed, so omitting it
#: hid exactly the columns this gate asks about. ``dp-spec.approved.md`` was
#: retired in v0.38.0 in favour of ``dp-blueprint.approved.md``; both are listed
#: so older retained bundles still read.
_IMPLEMENTATION_FILES: tuple[str, ...] = (
    "models.py",
    "spec.py",
    "transform/main.py",
    "dp-blueprint.approved.md",
    "dp-spec.approved.md",
)


def _closure_implementation_text(closures: Sequence[Path]) -> str:
    chunks: list[str] = []
    for closure in closures:
        for name in _IMPLEMENTATION_FILES:
            candidate = closure / name
            if candidate.is_file():
                try:
                    chunks.append(candidate.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
    return "\n".join(chunks)


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


def _follow_up_artifact(scenario: Scenario, artifact_root: Path) -> Mapping[str, object] | None:
    """Load the scenario-declared agent evidence, failing closed on any defect."""

    relative = getattr(scenario, "follow_up_artifact", None)
    if not isinstance(relative, str) or not relative:
        return None
    candidate = (artifact_root / relative).resolve()
    root = artifact_root.resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping):
        return None
    # Tagged rather than filtered: the artifact is the agent's own object and
    # every key in it is the agent's to choose.  ``AgentEvidence`` tells
    # ``follow_up_check`` not to read it as the legacy positional convention,
    # so a field named ``closure`` is just a field.
    return AgentEvidence(value)


# Tool namespaces whose *results* are product surfaces rather than source
# surfaces. A planted PII sentinel reaching a served query result or a
# supervisor-reported model means the sentinel survived into the product,
# which is the leak this gate exists to catch. A sentinel appearing in the
# result of ``Read``-ing the fixture does not: inspecting the source is what
# the intake and capability phases require, and scanning those results makes
# the correct behaviour -- look at the data, notice the PII, refuse to expose
# it -- an automatic zero.
_PRODUCT_TOOL_PREFIXES = ("mcp__nxd-desktop__",)


def _leakable_transcript_delta_lines(delta: str) -> list[str]:
    """Split a rendered transcript_delta into its leakable lines.

    Each segment is appended as one list entry and the whole list is
    "\\n".join-ed (claude_adapter.py), so a multi-line assistant or tool_use
    block's own internal newlines produce continuation lines carrying no
    prefix of their own -- only the first line of a block is prefixed. A
    per-line prefix filter therefore drops every continuation line
    regardless of which block it belongs to, including the agent's own
    prose, which this module's docstring says is always leakable. This
    instead tracks which block is currently open and classifies
    continuation lines by it: everything is kept until a [tool_result] line
    opens, then everything is dropped until the next recognized
    [assistant]/[tool_use:] line reopens keeping.
    """

    kept: list[str] = []
    keep_current = True
    for line in delta.splitlines():
        if line.startswith("[assistant] ") or line.startswith("[tool_use:"):
            keep_current = True
        elif line.startswith("[tool_result] "):
            keep_current = False
        if keep_current:
            kept.append(line)
    return kept


def _leakable_turn_surfaces(turns: Sequence[object]) -> list[object]:
    """Return the parts of a transcript a sentinel must never reach.

    The agent's own prose and the arguments it passes to tools are always
    included: writing a sentinel into a file, a query, or a reply to the
    operator is a leak however it happens. Tool *results* are included only
    for product tools -- see ``_PRODUCT_TOOL_PREFIXES``.
    """

    leakable: list[object] = []
    for turn in turns:
        if not isinstance(turn, Mapping):
            # An unreadable turn is not silently treated as clean; the whole
            # turn is scanned so a malformed shape cannot hide a leak.
            leakable.append(turn)
            continue
        leakable.append(turn.get("agent_message"))
        delta = turn.get("transcript_delta")
        if isinstance(delta, str):
            leakable.extend(_leakable_transcript_delta_lines(delta))
        elif delta is not None:
            leakable.append(delta)
        touched = turn.get("files_touched")
        if isinstance(touched, Sequence) and not isinstance(touched, (str, bytes, bytearray)):
            for file in touched:
                # Every touched file's content is a write, never exempt --
                # unlike a tool result, a write is a leak however it happens.
                # A mapping missing the expected "content" key is malformed,
                # not empty, so it is scanned whole rather than silently
                # dropped (matching the turn-level policy above).
                leakable.append(file.get("content") if isinstance(file, Mapping) and "content" in file else file)
        elif touched is not None:
            leakable.append(touched)
        calls = turn.get("tool_calls")
        if not isinstance(calls, Sequence) or isinstance(calls, (str, bytes, bytearray)):
            leakable.append(calls)
            continue
        for call in calls:
            if not isinstance(call, Mapping):
                leakable.append(call)
                continue
            leakable.append(call.get("arguments"))
            name = call.get("name")
            if not isinstance(name, str) or name.startswith(_PRODUCT_TOOL_PREFIXES):
                leakable.append(call.get("result"))
    return leakable


_OPERATOR_OBSERVATIONS_NAME = "operator-observations.json"
_SESSION_REPLAY_NAME = "session-replay.json"


def _turns_from_operator_observations(payload: Mapping[str, object]) -> Sequence[object] | None:
    """``operator-observations.json``'s turn entries are already turn-result-shaped."""

    turns = payload.get("turns")
    if isinstance(turns, Sequence) and not isinstance(turns, (str, bytes, bytearray)):
        return turns
    return None


def _turns_from_session_replay(payload: Mapping[str, object]) -> Sequence[object] | None:
    """``session-replay.json``'s turn entries wrap the turn result under ``"result"``.

    Unlike ``operator-observations.json``, each entry is
    ``{"operator_message": ..., "result": <turn-result shape>}``
    (``RecordedTurn.to_dict``), so the result has to be unwrapped before
    ``_leakable_turn_surfaces`` -- which expects the flat shape -- can read it.
    """

    turns = payload.get("turns")
    if not isinstance(turns, Sequence) or isinstance(turns, (str, bytes, bytearray)):
        return None
    results: list[object] = []
    for turn in turns:
        if not isinstance(turn, Mapping) or "result" not in turn:
            # Not the RecordedTurn.to_dict shape this file is supposed to
            # have. Falling back to a raw read of the whole file -- the same
            # policy _turns_from_operator_observations uses for its own
            # shape check -- is fail-closed; silently substituting a partial
            # view built from whatever this entry does have is not, because
            # it could hide a leak sitting under a key this unwrapping
            # doesn't recognise.
            return None
        results.append(turn.get("result"))
    return results


# Harness-written files under ``artifact_root`` known to carry a raw,
# unfiltered turns list. Named explicitly rather than detected by shape,
# because these are fixed harness filenames, not arbitrary scenario data --
# a new file gaining this shape needs a deliberate entry here, not a
# heuristic that might also match a materialized closure file.
_RAW_TURN_CARRIERS: dict[str, Callable[[Mapping[str, object]], Sequence[object] | None]] = {
    _OPERATOR_OBSERVATIONS_NAME: _turns_from_operator_observations,
    _SESSION_REPLAY_NAME: _turns_from_session_replay,
}


def _artifacts_surface_bytes(artifact_root: Path) -> bytes | None:
    """Concatenate every artifact file, substituting the leakable view of
    each known raw-turn-carrying file (see ``_RAW_TURN_CARRIERS``) for its
    raw bytes.

    Those files legitimately retain full, unfiltered tool-call results on
    disk -- ``gold_access_scan`` and the construction gate both need the real
    structure from ``operator-observations.json``, and a replayable
    ``session-replay.json`` needs to be byte-faithful. Handing the whole
    ``artifact_root`` directory to ``sentinel_byte_scan`` as one surface
    re-reads exactly the bytes ``_leakable_turn_surfaces`` excludes from the
    ``"transcript"`` surface, so the exemption would be bypassed rather than
    removed for either file. Every other file under ``artifact_root`` (the
    materialized closure, query results) still scans raw, because a leak into
    any of those is a real leak into the product.
    """

    chunks: list[bytes] = []
    try:
        children = sorted(artifact_root.rglob("*"))
    except OSError:
        return None
    for child in children:
        if not child.is_file():
            continue
        extractor = _RAW_TURN_CARRIERS.get(child.name) if child.parent == artifact_root else None
        if extractor is not None:
            payload = _load_json(child)
            turns = extractor(payload) if isinstance(payload, Mapping) else None
            if turns is not None:
                chunks.append(json.dumps(_leakable_turn_surfaces(turns), ensure_ascii=False).encode("utf-8"))
                continue
        try:
            chunks.append(child.read_bytes())
        except (OSError, UnicodeError):
            continue
    return b"\n".join(chunks) if chunks else None


def _sentinel_trip(environment: RunEnvironment, artifact_root: Path) -> bool | None:
    markers = marker_values(environment.generated_fixture_manifest)
    if not markers:
        return None
    observations = _load_json(artifact_root / _OPERATOR_OBSERVATIONS_NAME)
    if not isinstance(observations, Mapping):
        return None
    transcript = observations.get("turns")
    if not isinstance(transcript, Sequence) or isinstance(transcript, (str, bytes, bytearray)):
        return None
    surfaces: dict[str, object] = {
        "artifacts": _artifacts_surface_bytes(artifact_root),
        "ledger": environment.ledger_path,
        "transcript": json.dumps(_leakable_turn_surfaces(transcript), ensure_ascii=False),
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
        evidence_root: str | Path | None = None,
        budgets: RunBudgets | None = None,
        route_configs: Mapping[str, object] | None = None,
        supervisor_reader: SupervisorRecordReader | SupervisorReaderFactory | None = None,
        live_command: Sequence[str] | None = None,
        live_environment: Mapping[str, str] | None = None,
        supervisor_command: str | Path | Sequence[str] | None = None,
        supervisor_environment: Mapping[str, str] | None = None,
        knob_plan: KnobPlan | None = None,
        workflow_restart_factory: WorkflowRestartFactory | None = None,
        workflow_observer: WorkflowObserver | None = None,
        operator_factory: GeneratedOperator | DriverOperator | OperatorFactory | None = None,
        allow_host_home: bool = False,
    ) -> None:
        self.scenarios = tuple(scenarios)
        self.pins = pins
        self.canary = canary
        self.session_factory = session_factory
        self.replay_recordings = dict(replay_recordings or {})
        self.environment_root = Path(environment_root) if environment_root is not None else None
        # Retention is explicit.  A hidden temporary root would retain oracle
        # data after the caller loses the report and leak sensitive fixtures
        # into the host temp directory.  The local live entrypoint supplies a
        # report-scoped root; library callers can opt in the same way.
        self.evidence_root = Path(evidence_root).expanduser().resolve() if evidence_root is not None else None
        if self.evidence_root is not None:
            self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.budgets = budgets or RunBudgets()
        self.route_configs = dict(route_configs or {})
        self.supervisor_reader = supervisor_reader
        self.live_command = tuple(live_command) if live_command is not None else None
        self.live_environment = dict(live_environment or {})
        self.supervisor_command = supervisor_command
        self.supervisor_environment = (
            dict(supervisor_environment) if supervisor_environment is not None else None
        )
        self.knob_plan = knob_plan
        self.workflow_restart_factory = workflow_restart_factory
        self.workflow_observer = workflow_observer
        self.operator_factory = operator_factory
        self.allow_host_home = allow_host_home

    def _workflow_restart(
        self,
        scenario: Scenario,
        environment: RunEnvironment,
        epoch: int,
    ) -> WorkflowRestart | None:
        """Bind the caller-owned workflow factory to one scenario epoch."""

        if self.workflow_restart_factory is None:
            return None
        return lambda workflow: self.workflow_restart_factory(scenario, environment, epoch, workflow)

    def _generated_operator(
        self,
        scenario: Scenario,
        environment: RunEnvironment,
        epoch: int,
    ) -> GeneratedOperator | DriverOperator | None:
        """Resolve the optional operator surface without changing engine state."""

        surface = self._resolve_operator_surface(scenario, environment, epoch)
        self._check_driver_pins(surface)
        return surface

    def _check_driver_pins(self, surface: object) -> None:
        """Refuse a run whose manifest pins and operator surface disagree.

        The manifest is the only record a later reader has of who spoke the
        operator's words.  A driver-authored run stored under scripted pins
        would be indistinguishable from a scripted one, and scripted pins on a
        driver run would let a paired comparison treat two different operators
        as the same arm.  Neither is recoverable after the fact, so both are
        refused here rather than recorded.
        """

        declared = self.pins.driver_model_id != NOT_APPLICABLE
        if declared != isinstance(surface, DriverOperator):
            raise TierError("manifest driver pins and operator factory disagree")
        if not declared:
            return
        assert isinstance(surface, DriverOperator)
        if surface.model_id != self.pins.driver_model_id:
            raise TierError("manifest driver pins and operator factory disagree")
        temperature = self.pins.driver_sampling_params.get("temperature")
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
            raise TierError("manifest driver pins and operator factory disagree")
        if float(temperature) != float(surface.temperature):
            raise TierError("manifest driver pins and operator factory disagree")

    def _resolve_operator_surface(
        self,
        scenario: Scenario,
        environment: RunEnvironment,
        epoch: int,
    ) -> GeneratedOperator | DriverOperator | None:
        factory = self.operator_factory
        if factory is None:
            return None
        if isinstance(factory, (GeneratedOperator, DriverOperator)):
            return factory
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
        if value is not None and not isinstance(value, (GeneratedOperator, DriverOperator)):
            raise TierError("operator factory returned no GeneratedOperator or DriverOperator")
        return value

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
        # Fail before entering any environment.  Without this the run would
        # spawn a session, author scripted turns, and only then trip the
        # per-epoch consistency gate -- having already spent the agent tokens
        # the pins promised a driver would shape.
        if self.pins.driver_model_id != NOT_APPLICABLE and self.operator_factory is None:
            raise TierError("manifest driver pins require an operator factory")
        canary = self._canary()
        if canary.blocking:
            reasons = tuple(issue.to_dict() for issue in canary.verdict.issues)
            return TierResult("blocked_by_canary", canary, (), time.monotonic() - started, reasons)
        if not isinstance(canary.claims_hash, str) or not canary.claims_hash.strip():
            raise TierError("a non-blocking canary result must carry its claims hash")
        if canary.claims_hash != self.pins.canary_claims_hash:
            raise TierError("canary claims hash does not match the pinned assertion")
        self._validate_evidence_destinations()
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
                    # Carried so the batch-level check can exclude a run that
                    # never finished its script.  ``score.state`` alone cannot
                    # say it any more: since the TURN_TIMEOUT split a truncated
                    # run scores PASSED.
                    "truncated": run.terminal_state is EngineTerminalState.TURN_TIMEOUT,
                }
                for run in runs
            ]
            repeatability = repeatability_certificate(
                observations,
                getattr(scenario, "repeatability", scenario.repeatability_tier),
            )
            if repeatability.certified:
                runs = tuple(_promote_certified_run(run) for run in runs)
            summaries.append(ScenarioSummary(scenario.id, repeatability, tuple(runs)))
        states = [run.score.state for summary in summaries for run in summary.runs]
        # A truncated run never reached the end of its script, so the gates it
        # did examine are not evidence that the run was clean.  Before the
        # TURN_TIMEOUT split a per-turn timeout was an ENVIRONMENT_WEDGE and
        # therefore INVALID, so the runner exited 1; the split was meant to
        # change the *label* only, but it moved timeouts out of the one state
        # ``_grade`` treats as invalid.  Without this a run whose final turn
        # timed out could score PASSED on the gates already examined, aggregate
        # to "clean", and exit 0 -- the qualification cap to OBSERVED lives in
        # ``qualification.json`` and reaches no caller.  Degrading to "ungraded"
        # restores the pre-split exit code while keeping the timeout and the
        # wedge distinguishable in the evidence.
        truncated = any(
            run.terminal_state is EngineTerminalState.TURN_TIMEOUT
            for summary in summaries
            for run in summary.runs
        )
        if not states:
            # A tier that examined no scenario is not evidence of a clean run.
            verdict = "failed"
        elif all(state is ScoreTerminalState.PASSED for state in states):
            verdict = "ungraded" if truncated else "clean"
        elif states and all(state in {ScoreTerminalState.PASSED, ScoreTerminalState.UNGRADED} for state in states) and any(
            state is ScoreTerminalState.UNGRADED for state in states
        ):
            verdict = "ungraded"
        else:
            verdict = "failed"
        return TierResult(verdict, canary, tuple(summaries), time.monotonic() - started)

    def _validate_evidence_destinations(self) -> None:
        """Reject bundle collisions before constructing any scenario session."""

        if self.evidence_root is None:
            return
        for scenario in self.scenarios:
            for epoch in range(1, scenario.epochs + 1):
                destination = self.evidence_root / scenario.id / f"epoch-{epoch}"
                if destination.exists():
                    raise TierError(f"evidence bundle destination already exists: {destination}")

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
            knobs = _knob_plan_value(self.knob_plan, scenario, epoch)
            workflow_switch = knobs.workflow_switch
            if workflow_switch is not None and not isinstance(
                workflow_switch, WorkflowSwitchPlan
            ):
                raise TierError(
                    f"knob plan returned an invalid workflow switch for {scenario.id} epoch {epoch}"
                )
            with RunEnvironment(
                scenario,
                pins,
                trial_index=epoch - 1,
                root=self.environment_root,
                run_id=run_id,
                route_config=self.route_configs.get(scenario.id),
                manifest_override=manifest_override,
                live_command=self.live_command,
                live_environment=self.live_environment,
                supervisor_command=self.supervisor_command,
                supervisor_environment=self.supervisor_environment,
                allow_host_home=self.allow_host_home,
                knobs=knobs,
                attempt=epoch,
            ) as environment:
                workflow_restart = self._workflow_restart(scenario, environment, epoch)
                if workflow_switch is not None and (
                    workflow_restart is None or self.workflow_observer is None
                ):
                    raise TierError(
                        "workflow switching requires workflow_restart_factory and workflow_observer"
                    )
                artifact_root = environment.base_dir / "artifacts"
                artifact_root.mkdir()
                # Resolve the operator surface before any transport exists.
                # The consistency gate inside can refuse the run, and a live
                # session started first would be a spawned agent process that
                # the refusal then has to unwind.
                operator_surface = self._generated_operator(scenario, environment, epoch)
                generated_operator = (
                    operator_surface if isinstance(operator_surface, GeneratedOperator) else None
                )
                driver_operator = (
                    operator_surface if isinstance(operator_surface, DriverOperator) else None
                )
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
                        workflow_switch=workflow_switch,
                        workflow_restart=workflow_restart,
                        workflow_observer=self.workflow_observer,
                        workflow_evidence=lambda evidence, turn: environment.record_workflow_switch(
                            evidence,
                            turn=turn,
                        ),
                    )
                started = time.monotonic()
                transport_closed = False
                primary_error: BaseException | None = None
                try:
                    # The planted markers live in the generated fixture, not in
                    # the scenario's operator block: most scenarios declare
                    # ``operator.sentinel: null`` and still plant PII.  Hand
                    # them to the engine so redaction of agent text before an
                    # external provider covers the markers grading actually
                    # looks for.  The fixture manifest is not the whole
                    # inventory -- ``capability-shortfall`` plants its graded
                    # ``pii_sentinel`` in the mock-source route table, which
                    # ``marker_values`` never reads -- so the gate declarations
                    # are unioned in.  Redaction only: these deliberately do
                    # not widen the in-engine sentinel scan, because a marker
                    # in a tool result the agent legitimately read is not a
                    # leak.
                    engine = OperatorEngine(
                        scenario.script,
                        transport,
                        generated_operator=generated_operator,
                        driver=driver_operator,
                        extra_sentinels=sorted(
                            marker_values(environment.generated_fixture_manifest)
                            | declared_sentinels(scenario)
                        ),
                    )
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
                    _append_artifact_rows(artifact_root)
                    facts = _supervisor_facts(supervisor_reader)
                    if facts is not None and supervisor_reader is not None:
                        append_supervisor_facts(
                            environment.ledger,
                            supervisor_reader,
                            run_id=environment.manifest.run_id,
                            scenario_id=environment.manifest.scenario_id,
                            turn=max(1, len(run_result.turns)),
                            phase=5,
                        )
                    _snapshot_source_artifacts(environment, artifact_root)
                    _write_operator_observations(artifact_root, run_result)
                    close = getattr(transport, "close", None)
                    if callable(close):
                        try:
                            close()
                        finally:
                            transport_closed = True
                    score, facts, calls, route_status, route_reason = self._grade(
                        scenario,
                        environment,
                        artifact_root,
                        supervisor_facts=facts,
                    )
                    elapsed = time.monotonic() - started
                except BaseException as error:
                    primary_error = error
                    raise
                finally:
                    close = None if transport_closed else getattr(transport, "close", None)
                    if callable(close):
                        try:
                            close()
                        except BaseException as cleanup_error:
                            if primary_error is None:
                                raise
                            primary_error.add_note(
                                f"TierRunner transport cleanup failed: {cleanup_error}"
                            )
                stop_condition = run_result.stop_reason
                efficiency = _efficiency(
                    scenario,
                    turns=len(run_result.turns),
                    calls=calls,
                    wall_clock=elapsed,
                    budgets=self.budgets,
                )
                score = replace(score, efficiency=efficiency)
                replay_status, replay_reason = _replay_verification(
                    scenario,
                    replay,
                    run_result,
                    generated_operator=generated_operator is not None,
                    driver=driver_operator is not None,
                )
                qualification = qualify_run(
                    score,
                    replay_status=replay_status,
                    generated_operator=generated_operator is not None,
                    driver=driver_operator is not None,
                    validation_mode=environment.manifest.validation_mode,
                    operator_mode=getattr(run_result, "operator_mode", "scripted"),
                    truncated=run_result.terminal_state is EngineTerminalState.TURN_TIMEOUT,
                )
                bundle_dir: Path | None = None
                bundle_digest: str | None = None
                if self.evidence_root is not None:
                    bundle_dir = self.evidence_root / scenario.id / f"epoch-{epoch}"
                    bundle_digest = _retain_evidence_bundle(
                        bundle_dir,
                        environment,
                        artifact_root,
                        replay,
                        qualification,
                    )
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
                        evidence_bundle_dir=str(bundle_dir) if bundle_dir is not None else None,
                        bundle_digest=bundle_digest,
                        replay_verification_status=replay_status,
                        replay_verification_reason=replay_reason,
                        qualification=qualification,
                        failure_reason=getattr(run_result, "failure_reason", None),
                        failure_detail=getattr(run_result, "failure_detail", None),
                        last_mcp_call=getattr(run_result, "last_mcp_call", None),
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

        integrity_error = _fixture_integrity_error(environment)
        if integrity_error is not None:
            gates = {
                name: GateResult(
                    name,
                    False,
                    0,
                    (Finding("fixture_integrity_failed", integrity_error),) if name == "build" else (),
                    examined=False,
                    required=name != "follow-up",
                )
                for name in GATE_POINTS
            }
            score = score_run(
                gates,
                honesty_report=LintReport(False, [LintFinding("fixture_integrity_failed", 1, integrity_error)]),
                route_fidelity=None,
                sentinel_tripped=False,
                invalid=True,
                efficiency=_efficiency(
                    scenario,
                    turns=0,
                    calls=0,
                    wall_clock=0.0,
                    budgets=self.budgets,
                ),
            )
            return score, supervisor_facts, 0, "unexamined", integrity_error

        ledger_artifact: object = environment.ledger_path
        spec = _first_json(artifact_root, ("spec.json", "built-spec.json", "definition.json"))
        capability = _first_json(artifact_root, ("capability.json",)) if environment.mock_source is not None else None
        spec_diff = _first_json(artifact_root, ("spec-diff.json", "spec_diff.json"))
        closure = _closure_artifact(artifact_root)
        fixture_manifest = environment.generated_fixture_manifest
        row_counts = (
            {"per_model_row_counts": fixture_manifest.get("table_row_counts", {})}
            if isinstance(fixture_manifest, Mapping)
            else None
        )
        query = _query_artifact(artifact_root)
        facts = supervisor_facts
        observations = _load_json(artifact_root / "operator-observations.json")
        if not isinstance(observations, Mapping):
            raise TierError("operator observations were not persisted before grading")
        # No fallback root: the only other candidate was ``artifact_root``,
        # and the system prompt forbids the agent to create files under
        # ``artifacts/``, so that path could only ever be satisfied by a
        # harness-planted file.
        attestation_read = _agent_attestations(environment.base_dir / "agent")
        attestations = attestation_read.values
        gold_access = gold_access_scan(observations, environment.oracle_dir)

        construction = gate_construction(
            ledger_artifact,
            observations=observations,
            attestations=attestations,
            require_observed=True,
            desktop_server_name=environment.desktop_server_name,
        )
        if attestation_read.findings:
            construction = replace(
                construction,
                passed=False,
                points=0,
                findings=construction.findings + attestation_read.findings,
            )
        gates: dict[str, GateResult] = {
            "intake": gate_intake({"rows": read_ledger(environment.ledger_path), "observations": observations}),
            "capability": _capability_gate_result(
                artifact_root, spec, capability, environment, scenario
            ),
            "narrowing": gate_narrowing(
                spec_diff,
                ledger_artifact,
                closure,
                required=scenario.stages_definition_change,
            ),
            "construction": construction,
            "build": gate_build(facts, row_counts),
        }
        answer_gold_declared = bool(getattr(scenario, "has_scoreable_answer_gold", True))
        if query is None:
            gates["query"] = GateResult(
                "query",
                False,
                0,
                (Finding("query_actual_not_examined", "actual query rows are absent or unreadable"),),
                examined=False,
                required=answer_gold_declared,
            )
        elif not answer_gold_declared:
            gates["query"] = GateResult(
                "query",
                False,
                0,
                (Finding("query_answer_gold_not_declared", "scenario declares no scoreable answer gold"),),
                examined=False,
                required=False,
            )
        else:
            try:
                gold = scenario.load_gold("answer", environment.oracle_dir)
            except Exception as exc:
                gates["query"] = GateResult(
                    "query",
                    False,
                    0,
                    (Finding("query_gold_not_examined", str(exc)),),
                    examined=False,
                    required=True,
                )
            else:
                gates["query"] = gate_query(query, gold)
        query_rows: Sequence[Mapping[str, object]] | None = None
        if isinstance(query, Mapping):
            candidate = query.get("rows", query.get("query_rows", query.get("result")))
            if isinstance(candidate, list):
                query_rows = [row for row in candidate if isinstance(row, Mapping)]
        elif isinstance(query, list):
            query_rows = [row for row in query if isinstance(row, Mapping)]
        follow_up_method = scenario.follow_up_gate
        follow_up_target: object = closure
        if getattr(scenario, "follow_up_artifact", None) is not None:
            # Scenario-specific evidence is an explicit artifact boundary. A
            # missing or malformed artifact becomes ``not-examined`` in the
            # follow-up handler instead of falling back to a closure path.
            follow_up_target = _follow_up_artifact(scenario, artifact_root)
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
                follow_up_target,
                environment.oracle_dir,
                query_rows,
                **follow_up_kwargs,
            )
        elif "query_rows" in follow_up_parameters:
            follow_up = follow_up_method(follow_up_target, query_rows)
        else:
            follow_up = follow_up_method(follow_up_target)
        ungraded = observations.get("ungraded_criteria", ())
        if not isinstance(ungraded, Sequence) or isinstance(ungraded, (str, bytes)):
            ungraded = ()
        if ungraded and not follow_up.ungraded:
            follow_up = GateResult(
                "follow-up",
                False,
                0,
                follow_up.findings + (Finding("follow_up_planted_difficulty_not_fired", ", ".join(sorted(map(str, ungraded)))),),
                examined=False,
                ungraded=True,
            )
        gates["follow-up"] = follow_up
        if not gold_access.passed:
            gates["query"] = GateResult(
                "query",
                False,
                0,
                gates["query"].findings
                + tuple(Finding(f.code, f.detail, f.value) for f in gold_access.findings),
                examined=gold_access.examined and gates["query"].examined,
                required=gates["query"].required,
            )

        if facts is None:
            honesty = LintReport(False, [LintFinding("incomplete_supervisor_facts", 1, "supervisor facts not examined")])
        else:
            honesty = gate_honesty(environment.ledger_path, facts)
        if environment.mock_source is None:
            route_fidelity = None
            route_status = "not-applicable"
            route_reason = "scenario declares no route table"
        else:
            counters = environment.mock_source.server.counters.snapshot()
            routes = counters.get("routes") if isinstance(counters, Mapping) else None
            total = counters.get("total") if isinstance(counters, Mapping) else None
            # Perfect fidelity -- every request matched a declared route -- is
            # the case where ``__unmatched__`` was never recorded at all, so
            # its absence must mean zero, not "not examined". Defaulting the
            # lookup to an empty mapping (rather than leaving it ``None``)
            # keeps that the common case rather than the only one this gate
            # can never certify true.
            unmatched = routes.get("__unmatched__", {}) if isinstance(routes, Mapping) else None
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
            gold_access_tripped=not gold_access.passed,
            invalid=invalid,
            efficiency=efficiency,
        )
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

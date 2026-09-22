"""Canary-gated tier execution, isolated environments, and replay reports.

The invariant enforced here is that the canary gate is evaluated before any
scenario transport is constructed.  The package exports the narrow seams used
by live and replay runs so known documentation/runtime drift cannot be
mistaken for agent behaviour.
"""

from .environment import Environment, MockSourceHandle, PinnedVersions, RunEnvironment, RunEnvironmentError, RunSetup
from .checkpoint import (
    CheckpointError,
    CheckpointIdentity,
    CheckpointState,
    CheckpointStore,
    ClaudeSessionIdentity,
    ProviderSessionIdentity,
    is_valid_provider_session_id,
    ResumeDecision,
    canonical_digest,
)
from .report import (
    ReportError,
    emit_report,
    human_summary,
    machine_report,
    write_abort_report,
    write_report,
)
from .qualification import QualificationDisposition, QualificationRecord, qualify_run
from .session import (
    LiveSession,
    LiveTransport,
    NativeResumeSession,
    RecordedSession,
    RecordedTurn,
    RecordingSession,
    ReplayMismatch,
    ReplayRecording,
    ReplaySession,
    ReplayTransport,
    SessionError,
    SessionTransport,
)
from .tier import (
    CanaryResult,
    RunBudgets,
    ScenarioRun,
    ScenarioSummary,
    Tier,
    TierError,
    TierResult,
    TierRunner,
    run_drift_canary,
    run_tier,
)

__all__ = [
    "CanaryResult",
    "CheckpointError",
    "CheckpointIdentity",
    "CheckpointState",
    "CheckpointStore",
    "ClaudeSessionIdentity",
    "ProviderSessionIdentity",
    "is_valid_provider_session_id",
    "canonical_digest",
    "Environment",
    "LiveSession",
    "LiveTransport",
    "NativeResumeSession",
    "MockSourceHandle",
    "PinnedVersions",
    "QualificationDisposition",
    "QualificationRecord",
    "RecordedSession",
    "RecordedTurn",
    "RecordingSession",
    "ReplayMismatch",
    "ReplayRecording",
    "ReplaySession",
    "ReplayTransport",
    "ResumeDecision",
    "ReportError",
    "RunBudgets",
    "RunEnvironment",
    "RunEnvironmentError",
    "RunSetup",
    "ScenarioRun",
    "ScenarioSummary",
    "SessionError",
    "SessionTransport",
    "Tier",
    "TierError",
    "TierResult",
    "TierRunner",
    "emit_report",
    "human_summary",
    "machine_report",
    "run_drift_canary",
    "run_tier",
    "qualify_run",
    "write_report",
    "write_abort_report",
]

"""Canary-gated tier execution, isolated environments, and replay reports.

The invariant enforced here is that the canary gate is evaluated before any
scenario transport is constructed.  The package exports the narrow seams used
by live and replay runs so known documentation/runtime drift cannot be
mistaken for agent behaviour.
"""

from .environment import Environment, MockSourceHandle, PinnedVersions, RunEnvironment, RunEnvironmentError, RunSetup
from .report import ReportError, emit_report, human_summary, machine_report, write_report
from .session import (
    LiveSession,
    LiveTransport,
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
    "Environment",
    "LiveSession",
    "LiveTransport",
    "MockSourceHandle",
    "PinnedVersions",
    "RecordedSession",
    "RecordedTurn",
    "RecordingSession",
    "ReplayMismatch",
    "ReplayRecording",
    "ReplaySession",
    "ReplayTransport",
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
    "write_report",
]

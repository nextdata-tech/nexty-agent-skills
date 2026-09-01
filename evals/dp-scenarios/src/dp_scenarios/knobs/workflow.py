"""A small lifecycle script for proving a post-restart workflow endpoint."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .runtime import KnobError


class RestartableTransport(Protocol):
    def start(self) -> object: ...
    def cleanup(self) -> None: ...


@dataclass(frozen=True, slots=True)
class WorkflowSwitchPlan:
    """The declared old/new workflow pair for a restart attempt."""

    from_workflow: str
    to_workflow: str

    def __post_init__(self) -> None:
        for name, value in (("from_workflow", self.from_workflow), ("to_workflow", self.to_workflow)):
            if not isinstance(value, str) or not value.strip():
                raise KnobError(f"{name} must be a non-empty string")
        if self.from_workflow == self.to_workflow:
            raise KnobError("workflow switch must name two different workflows")

    def to_manifest(self) -> dict[str, object]:
        return {
            "enabled": True,
            "from_workflow": self.from_workflow,
            "to_workflow": self.to_workflow,
            "assertion": "first_post_switch_call_answers_from_new_workflow_endpoint",
        }


@dataclass(frozen=True, slots=True)
class EndpointObservation:
    """The endpoint identity returned by the first post-switch call."""

    requested_workflow: str
    answered_workflow: str
    answered_endpoint: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.requested_workflow,
            self.answered_workflow,
            self.answered_endpoint,
        )):
            raise KnobError("endpoint observation fields must be non-empty strings")


@dataclass(frozen=True, slots=True)
class WorkflowSwitchEvidence:
    """Stable evidence for the first call after the scripted restart."""

    from_workflow: str
    to_workflow: str
    answered_workflow: str
    answered_endpoint: str
    stale_endpoint_rejected: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "from_workflow": self.from_workflow,
            "to_workflow": self.to_workflow,
            "answered_workflow": self.answered_workflow,
            "answered_endpoint": self.answered_endpoint,
            "stale_endpoint_rejected": self.stale_endpoint_rejected,
        }


def script_restart_and_switch(
    current: RestartableTransport,
    plan: WorkflowSwitchPlan,
    *,
    restart: Callable[[str], RestartableTransport],
    first_call: Callable[[RestartableTransport, str], EndpointObservation],
    stale_endpoint: str | None = None,
) -> tuple[RestartableTransport, WorkflowSwitchEvidence]:
    """Stop, create, and start a new DesktopStdio session before its first call.

    ``restart`` is the caller-owned factory for a fresh
    :class:`DesktopStdioTransport`; this is required because the shared
    ``DesktopStdioSession`` is intentionally terminal after cleanup.  The
    helper does not start a second supervisor path and keeps the replacement
    transport open for the caller's remaining turns.
    """

    current.cleanup()
    replacement = restart(plan.to_workflow)
    try:
        replacement.start()
        observation = first_call(replacement, plan.to_workflow)
    except Exception:
        replacement.cleanup()
        raise
    if observation.requested_workflow != plan.to_workflow:
        raise KnobError("post-switch call used the wrong requested workflow")
    if observation.answered_workflow != plan.to_workflow:
        raise KnobError(
            "post-switch call was served by a stale workflow: "
            f"{observation.answered_workflow!r}"
        )
    if stale_endpoint is not None and observation.answered_endpoint == stale_endpoint:
        raise KnobError("post-switch call was served by the stale endpoint")
    evidence = WorkflowSwitchEvidence(
        from_workflow=plan.from_workflow,
        to_workflow=plan.to_workflow,
        answered_workflow=observation.answered_workflow,
        answered_endpoint=observation.answered_endpoint,
        stale_endpoint_rejected=(stale_endpoint is None or observation.answered_endpoint != stale_endpoint),
    )
    return replacement, evidence

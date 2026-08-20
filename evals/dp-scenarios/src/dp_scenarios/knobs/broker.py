"""Attempt-keyed broker faults using the supervisor's entrypoint seam."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .runtime import KnobError


class BrokerFaultShape(str, Enum):
    """The two process-level startup failures supported by the harness."""

    SLEEP_PAST_BIND_TIMEOUT = "sleep_past_bind_timeout"
    OCCUPIED_PORT = "occupied_port"


def broker_entrypoint_path() -> Path:
    """Return the checked-in Python shim passed as NXD's semantic entrypoint."""

    return Path(__file__).with_name("broker_entrypoint.py")


@dataclass(frozen=True, slots=True)
class BrokerFaultPlan:
    """Select a process fault by attempt without changing supervisor code."""

    faults: Mapping[int, BrokerFaultShape]
    real_entrypoint: str | Path
    bind_timeout_s: int = 30
    margin_s: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.faults, Mapping):
            raise KnobError("broker faults must be an attempt mapping")
        if not self.faults:
            raise KnobError("broker fault plan must contain at least one attempt")
        for attempt, shape in self.faults.items():
            if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
                raise KnobError("broker fault attempts must be positive integers")
            if not isinstance(shape, BrokerFaultShape):
                try:
                    BrokerFaultShape(shape)
                except ValueError as exc:
                    raise KnobError(f"unknown broker fault shape: {shape!r}") from exc
        if not isinstance(self.real_entrypoint, (str, Path)) or not str(self.real_entrypoint):
            raise KnobError("broker real_entrypoint must be a non-empty path")
        if isinstance(self.bind_timeout_s, bool) or not isinstance(self.bind_timeout_s, int) or self.bind_timeout_s < 1:
            raise KnobError("broker bind timeout must be a positive integer")
        if isinstance(self.margin_s, bool) or not isinstance(self.margin_s, int) or self.margin_s < 1:
            raise KnobError("broker fault margin must be a positive integer")

    def fault_for_attempt(self, attempt: int) -> BrokerFaultShape | None:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise KnobError("attempt must be a positive integer")
        shape = self.faults.get(attempt)
        return BrokerFaultShape(shape) if shape is not None else None

    def environment_for_attempt(self, attempt: int) -> dict[str, str]:
        shape = self.fault_for_attempt(attempt)
        return {
            "NXD_EVAL_BROKER_FAULT": shape.value if shape is not None else "none",
            "NXD_EVAL_BROKER_ATTEMPT": str(attempt),
            "NXD_EVAL_BROKER_REAL_ENTRYPOINT": str(self.real_entrypoint),
            "NXD_EVAL_BROKER_BIND_TIMEOUT_S": str(self.bind_timeout_s),
            "NXD_EVAL_BROKER_MARGIN_S": str(self.margin_s),
        }

    def supervisor_args_for_attempt(
        self,
        attempt: int,
        existing_args: Sequence[str] = (),
    ) -> tuple[str, ...]:
        self.fault_for_attempt(attempt)
        args = tuple(str(argument) for argument in existing_args)
        if "--semantic-entrypoint" in args:
            raise KnobError("broker fault plan cannot replace an existing semantic entrypoint")
        return (*args, "--semantic-entrypoint", str(broker_entrypoint_path()))

    def to_manifest(self, *, attempt: int) -> dict[str, object]:
        shape = self.fault_for_attempt(attempt)
        return {
            "enabled": True,
            "active_attempt": attempt,
            "active_fault": shape.value if shape is not None else "none",
            "faults": {
                str(key): BrokerFaultShape(value).value
                for key, value in sorted(self.faults.items())
            },
            "bind_timeout_s": self.bind_timeout_s,
            "margin_s": self.margin_s,
            "entrypoint": "process-level-semantic-entrypoint-shim",
        }

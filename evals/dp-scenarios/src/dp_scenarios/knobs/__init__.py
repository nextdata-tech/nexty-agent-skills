"""Explicit, deterministic controls for supervisor scenario runs.

The package deliberately contains configuration and small process/lifecycle
seams only.  It never samples elapsed time to decide whether a scenario
passed; the transform control is an arithmetic contract and broker faults are
selected by attempt number.
"""

from .broker import (
    BrokerFaultPlan,
    BrokerFaultShape,
    broker_entrypoint_path,
)
from .config import load_knob_plan, supervisor_knobs_from_mapping
from .runtime import (
    KnobError,
    PlanShape,
    SupervisorKnobs,
    TransformWindowSizing,
    apply_transform_latency,
)
from .workflow import (
    EndpointObservation,
    WorkflowSwitchEvidence,
    WorkflowSwitchPlan,
    script_restart_and_switch,
)

__all__ = [
    "BrokerFaultPlan",
    "BrokerFaultShape",
    "EndpointObservation",
    "KnobError",
    "PlanShape",
    "SupervisorKnobs",
    "TransformWindowSizing",
    "WorkflowSwitchEvidence",
    "WorkflowSwitchPlan",
    "apply_transform_latency",
    "broker_entrypoint_path",
    "load_knob_plan",
    "script_restart_and_switch",
    "supervisor_knobs_from_mapping",
]

"""Deterministic HTTP fixtures whose declared behavior is the test oracle.

The package keeps source data, planted transport behavior, and grading metadata
separate: data routes expose only the configured source, while counters and the
capability manifest live on a different control port.  This prevents a client
from accidentally using the oracle that is meant to evaluate it.
"""

from .capability import CapabilityManifest, CapabilityError, load_capability_manifest
from .config import ConfigError, ScenarioConfig, load_config
from .counters import RequestCounters
from .server import MockRestServer, start_server, wait_until_ready

__all__ = [
    "CapabilityError",
    "CapabilityManifest",
    "ConfigError",
    "MockRestServer",
    "RequestCounters",
    "ScenarioConfig",
    "load_capability_manifest",
    "load_config",
    "start_server",
    "wait_until_ready",
]

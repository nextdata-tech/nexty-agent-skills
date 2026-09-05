"""Additive registries for generated fixture providers.

Scenario work should be able to add a fixture without editing a shared
dispatch table. Duplicate identities fail closed so one scenario package
cannot silently replace another package's source or oracle.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


class RegistryError(ValueError):
    """Raised when a fixture provider is unknown or registered twice."""


_DATASETS: dict[str, Any] = {}


def register_dataset(definition: Any) -> Any:
    """Register a dataset definition, rejecting duplicate identities."""

    name = getattr(definition, "name", None)
    if not isinstance(name, str) or not name:
        raise RegistryError("dataset definition must expose a non-empty name")
    if name in _DATASETS:
        raise RegistryError(f"dataset {name!r} is already registered")
    _DATASETS[name] = definition
    return definition


def dataset_definitions() -> Mapping[str, Any]:
    """Return an immutable snapshot of all discovered dataset definitions."""

    return MappingProxyType(dict(_DATASETS))


def get_registered_dataset(name: str) -> Any:
    """Return a registered dataset definition or raise a useful error."""

    try:
        return _DATASETS[name]
    except KeyError as exc:
        available = ", ".join(sorted(_DATASETS))
        raise RegistryError(f"unknown dataset {name!r}; choose one of: {available}") from exc


def registered_dataset_names() -> frozenset[str]:
    """Return the closed set of discovered dataset names."""

    return frozenset(_DATASETS)


__all__ = [
    "RegistryError",
    "dataset_definitions",
    "get_registered_dataset",
    "register_dataset",
    "registered_dataset_names",
]

"""Capability manifests that remain outside the data API.

The manifest is a small, validated oracle: metric labels are closed to
``supported``, ``proxy``, and ``impossible``, while endpoint entries enumerate
the status codes a source route can produce.  It can be loaded from disk and
is served only by the server's control port, preventing a source client from
answering its own capability probe from hidden metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from .config import SUPPORTED_HTTP_METHODS


class CapabilityError(ValueError):
    """Raised when a capability manifest contains an invalid declaration."""


_SUPPORT = {"supported", "proxy", "impossible"}


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CapabilityError(f"{location} must be a mapping")
    return dict(value)


@dataclass(frozen=True)
class CapabilityManifest:
    """Validated metric support labels and endpoint status declarations."""

    metrics: dict[str, str]
    endpoints: dict[str, dict[str, tuple[int, ...]]]
    known_absent_dimensions: tuple[str, ...] = ()
    #: Column-name fragments that would mean a build implements a metric.
    #: Declared per scenario because only the scenario knows that a
    #: ``stage_age_days`` column is what ``time_in_stage_days`` means. The
    #: capability gate reads this off the snapshot written into the artifact
    #: root, so a manifest that parsed it but dropped it here left the gate
    #: with labels and no way to bind them to columns.
    metric_terms: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Any) -> "CapabilityManifest":
        raw = _mapping(value, "capability")
        unknown = sorted(set(raw) - {"metrics", "endpoints", "known_absent_dimensions", "metric_terms"})
        if unknown:
            raise CapabilityError(f"capability contains unknown key(s): {', '.join(unknown)}")
        raw_metrics = _mapping(raw.get("metrics", {}), "capability.metrics")
        metrics: dict[str, str] = {}
        for name, support in raw_metrics.items():
            if not isinstance(name, str) or not name.strip():
                raise CapabilityError("capability metric names must be non-empty strings")
            if not isinstance(support, str) or support not in _SUPPORT:
                raise CapabilityError(f"capability.metrics.{name} has invalid support label: {support}")
            metrics[name] = support

        raw_endpoints = _mapping(raw.get("endpoints", {}), "capability.endpoints")
        endpoints: dict[str, dict[str, tuple[int, ...]]] = {}
        for path, declaration in raw_endpoints.items():
            if not isinstance(path, str) or not path.startswith("/"):
                raise CapabilityError(f"capability endpoint path must be absolute: {path}")
            if isinstance(declaration, list):
                endpoints[path] = {"*": _statuses(declaration, f"capability.endpoints.{path}")}
                continue
            method_map = _mapping(declaration, f"capability.endpoints.{path}")
            endpoint_statuses: dict[str, tuple[int, ...]] = {}
            for method, statuses in method_map.items():
                if not isinstance(method, str) or not method.strip():
                    raise CapabilityError(f"capability endpoint methods must be non-empty strings: {path}")
                method_name = method.upper()
                if method_name not in SUPPORTED_HTTP_METHODS:
                    raise CapabilityError(
                        f"capability endpoint method is not supported: {path} {method_name}"
                    )
                if method_name in endpoint_statuses:
                    raise CapabilityError(f"duplicate method in capability endpoint: {path} {method_name}")
                endpoint_statuses[method_name] = _statuses(
                    statuses, f"capability.endpoints.{path}.{method_name}"
                )
            endpoints[path] = endpoint_statuses
        raw_absent = raw.get("known_absent_dimensions", [])
        if not isinstance(raw_absent, list):
            raise CapabilityError("capability.known_absent_dimensions must be a list")
        known_absent: list[str] = []
        for dimension in raw_absent:
            if not isinstance(dimension, str) or not dimension.strip():
                raise CapabilityError(
                    "capability.known_absent_dimensions must contain non-empty strings"
                )
            if dimension in known_absent:
                raise CapabilityError(
                    f"capability.known_absent_dimensions contains duplicate: {dimension}"
                )
            known_absent.append(dimension)
        raw_terms = raw.get("metric_terms", {})
        if not isinstance(raw_terms, Mapping):
            raise CapabilityError("capability.metric_terms must be a mapping")
        metric_terms: dict[str, tuple[str, ...]] = {}
        for name, terms in raw_terms.items():
            if name not in metrics:
                raise CapabilityError(
                    f"capability.metric_terms names an undeclared metric: {name}"
                )
            if isinstance(terms, str) or not isinstance(terms, (list, tuple)):
                raise CapabilityError(
                    f"capability.metric_terms[{name}] must be a list of column fragments"
                )
            cleaned = tuple(term for term in terms if isinstance(term, str) and term.strip())
            if not cleaned:
                raise CapabilityError(
                    f"capability.metric_terms[{name}] must contain non-empty strings"
                )
            metric_terms[name] = cleaned
        return cls(metrics, endpoints, tuple(known_absent), metric_terms)

    @classmethod
    def load(cls, path: str | Path) -> "CapabilityManifest":
        """Load JSON or YAML manifest data from a path."""

        manifest_path = Path(path)
        try:
            text = manifest_path.read_text(encoding="utf-8")
            raw = yaml.safe_load(text) if manifest_path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
        except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
            raise CapabilityError(f"could not read capability manifest {manifest_path}: {exc}") from exc
        return cls.from_mapping(raw)

    def as_dict(self) -> dict[str, Any]:
        """Return stable JSON/YAML-friendly data."""

        endpoints: dict[str, Any] = {}
        for path, method_map in self.endpoints.items():
            if set(method_map) == {"*"}:
                endpoints[path] = list(method_map["*"])
            else:
                endpoints[path] = {
                    method: list(statuses) for method, statuses in method_map.items()
                }
        return {
            "metrics": dict(self.metrics),
            "endpoints": endpoints,
            "known_absent_dimensions": list(self.known_absent_dimensions),
            "metric_terms": {name: list(terms) for name, terms in self.metric_terms.items()},
        }

    to_dict = as_dict

    def write(self, path: str | Path) -> Path:
        """Persist the manifest so graders can use the same oracle offline."""

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix.lower() in {".yaml", ".yml"}:
            target.write_text(yaml.safe_dump(self.as_dict(), sort_keys=True), encoding="utf-8")
        else:
            target.write_text(json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return target

    def status_codes(self, path: str, method: str = "GET") -> tuple[int, ...]:
        """Return declared statuses for an endpoint/method, or an empty tuple."""

        method_map = self.endpoints.get(path, {})
        return method_map.get(method.upper(), method_map.get("*", ()))


def _statuses(value: Any, location: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise CapabilityError(f"{location} must be a non-empty list of status codes")
    statuses: list[int] = []
    for status in value:
        if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
            raise CapabilityError(f"{location} contains an invalid status code: {status}")
        statuses.append(status)
    if len(set(statuses)) != len(statuses):
        raise CapabilityError(f"{location} contains duplicate status codes")
    return tuple(statuses)


def load_capability_manifest(path: str | Path) -> CapabilityManifest:
    """Convenience loader used by graders and offline checks."""

    return CapabilityManifest.load(path)


load_capability = load_capability_manifest

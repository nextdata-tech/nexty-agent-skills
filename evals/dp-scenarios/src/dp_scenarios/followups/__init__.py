"""Registry of scenario-specific follow-up checks, one module per kind.

Every scenario declares exactly one ``gates.follow-up.kind``, and each kind
needs four things wired into the loader: a handler, the gold artifacts the
package must declare, the gold a certification claim needs, and validation of
the kind's own settings. Those four lived as four separate edits inside
``scenario.py`` -- a dispatch chain and three tables keyed by kind name.

That made every new scenario a change to one shared file, so two scenarios
authored at the same time conflicted textually even though they shared no
behaviour. Kinds register themselves from their own module here instead, and
this package imports every module beside it at import time, so adding a
scenario means adding a file rather than editing one. Discovery failures are
raised, never swallowed: a kind whose module does not import is a kind whose
scenario would silently fail to load.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..support import _MISSING


class FollowUpError(Exception):
    """Raised when a follow-up kind is unknown or registered twice."""


@dataclass(frozen=True, slots=True)
class FollowUpContext:
    """Extra call-site state a handler may need beyond target and settings."""

    fixture_dir: str | Path | None = None
    row_count_oracle: object = _MISSING
    source_evidence: object = _MISSING
    operator_observations: object = _MISSING


Handler = Callable[["object", object, Mapping[str, object], FollowUpContext], Mapping[str, object]]
SettingsValidator = Callable[[Mapping[str, object]], None]
PlantEvidenceValidator = Callable[[frozenset[str], Mapping[str, object]], None]
FixtureGoldValidator = Callable[[Mapping[str, object], Mapping[str, Path]], None]


def _ungraded(*findings: str) -> dict[str, object]:
    """Return the settled result for an unreadable committed gold artifact."""

    return {"status": "ungraded", "passed": False, "findings": list(findings)}


@dataclass(frozen=True, slots=True)
class FollowUpKind:
    """One registered follow-up kind and everything the loader needs from it."""

    name: str
    gold_keys: frozenset[str]
    handler: Handler
    # Agent-authored evidence is optional for older kinds. New kinds that
    # grade a multi-step result declare the fields they require here so the
    # runner can hand the agent a shape without exposing hidden gold.
    evidence_contract: Mapping[str, str] = field(default_factory=dict)
    certification_gold: Mapping[str, str] = field(default_factory=dict)
    validate_settings: SettingsValidator | None = None
    # Loader-time cross-checks. ``None`` means this kind declares no such
    # check -- a real choice, made visibly in the kind's own module, rather
    # than the invisible early return in the loader that it replaces. A kind
    # that declares gold nothing compares is how an ungraded gold artifact
    # shipped once already.
    validate_plant_evidence: PlantEvidenceValidator | None = None
    validate_fixture_gold: FixtureGoldValidator | None = None
    # Whether this kind's gold is byte-reproducible by regenerating the CSV
    # fixture. True is the stricter check and the default, so a kind whose
    # gold records something the generator cannot reproduce -- live database
    # facts, declared runtime constants -- has to say so deliberately.
    gold_reproducible_from_fixture: bool = True


_REGISTRY: dict[str, FollowUpKind] = {}


def register(kind: FollowUpKind) -> FollowUpKind:
    """Register one follow-up kind, rejecting a duplicate name.

    A silently overwritten kind would mean two scenarios sharing a name and
    the second quietly deciding how the first is graded.
    """

    if kind.name in _REGISTRY:
        raise FollowUpError(f"follow-up kind {kind.name!r} is already registered")
    _REGISTRY[kind.name] = kind
    return kind


def get(name: str) -> FollowUpKind:
    """Return a registered kind, or raise naming what is available."""

    try:
        return _REGISTRY[name]
    except KeyError:
        raise FollowUpError(
            f"unsupported follow-up kind {name!r}: expected one of {sorted(_REGISTRY)}"
        ) from None


def is_registered(name: str) -> bool:
    return name in _REGISTRY


def registered_names() -> frozenset[str]:
    return frozenset(_REGISTRY)


def _discover() -> None:
    """Import every sibling module so each one registers its kind."""

    # ``__path__`` rather than a filesystem path: the latter is import-loader
    # specific and finds nothing under zipimport.
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module.name}")


_discover()

__all__ = [
    "FollowUpContext",
    "FollowUpError",
    "FollowUpKind",
    "get",
    "is_registered",
    "register",
    "registered_names",
]

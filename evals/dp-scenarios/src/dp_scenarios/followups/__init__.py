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


Handler = Callable[["object", object, Mapping[str, object], FollowUpContext], Mapping[str, object]]
SettingsValidator = Callable[[Mapping[str, object]], None]


@dataclass(frozen=True, slots=True)
class FollowUpKind:
    """One registered follow-up kind and everything the loader needs from it."""

    name: str
    gold_keys: frozenset[str]
    handler: Handler
    certification_gold: Mapping[str, str] = field(default_factory=dict)
    validate_settings: SettingsValidator | None = None


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

    for module in pkgutil.iter_modules([str(Path(__file__).parent)]):
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

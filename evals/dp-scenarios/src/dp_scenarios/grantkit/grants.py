"""Scenario grants built from NXD's native field-mapper ``Grant`` type."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .runtime import load_field_mapper

FIXED_GRANTED_AT = "2026-01-01T00:00:00Z"
FIXED_EXPIRY = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
GRANT_ID_SCHEMA = "nxd-eval-grant-identity-v1"


class GrantKitError(ValueError):
    """Raised when a scenario grant or expansion is invalid."""


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def grant_scope(grant: Any) -> dict[str, Any]:
    """Return all native grant fields except the deliberately non-semantic path."""

    if isinstance(grant, Mapping):
        return {
            str(key): _json_value(value)
            for key, value in grant.items()
            if key != "source_path"
        }
    try:
        grant_fields = fields(grant)
    except TypeError as exc:
        raise GrantKitError("grant fixture must be an instance of field_mapper.Grant") from exc
    result: dict[str, Any] = {}
    for field in grant_fields:
        if field.name == "source_path":
            continue
        result[field.name] = _json_value(getattr(grant, field.name))
    return result


def grant_identity(grant: Any) -> str:
    """Return a path-independent identity for one native grant."""

    payload = {"schema": GRANT_ID_SCHEMA, "grant": grant_scope(grant)}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _positive(value: int | float, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise GrantKitError(f"{name} must be a positive number")
    return value


def _ceiling_at_least(old: int | float | None, new: int | float | None, name: str) -> None:
    # None is the native grant's unbounded ceiling.  The fixture constructors
    # use bounded values, but the widening validator remains correct for any
    # native Grant supplied by a scenario.
    if old is None:
        if new is not None:
            raise GrantKitError(f"grant expansion narrows unbounded {name}")
    elif new is not None and new < old:
        raise GrantKitError(f"grant expansion narrows {name}: {old} -> {new}")


def validate_widening(previous: Any, replacement: Any) -> None:
    """Require same scope and a strict monotonic ceiling widening."""

    previous_scope = grant_scope(previous)
    replacement_scope = grant_scope(replacement)
    for key in ("max_calls", "max_tokens", "max_usd"):
        previous_scope.pop(key, None)
        replacement_scope.pop(key, None)
    if previous_scope != replacement_scope:
        raise GrantKitError("grant expansion changes authorization scope, not only its ceilings")
    increased = False
    for name in ("max_calls", "max_tokens", "max_usd"):
        old = getattr(previous, name, None)
        new = getattr(replacement, name, None)
        _ceiling_at_least(old, new, name)
        if old != new:
            increased = True
    if not increased:
        raise GrantKitError("grant expansion must widen at least one ceiling")


def _bound_mapper_spec(spec_or_path: Any) -> tuple[Any, Any]:
    runtime = load_field_mapper()
    spec = runtime.MapperSpec.load(spec_or_path) if isinstance(spec_or_path, (str, Path)) else spec_or_path
    if not hasattr(spec, "mapper_spec_id"):
        raise GrantKitError("scenario closure did not provide a field_mapper.MapperSpec")
    # This is the same upstream binding used by the PR #189 fixture.  The
    # hash algorithm remains entirely in MapperSpec.mapper_spec_id.
    from nxd.experimental.field_mapper.schema import compile_schema

    bound = replace(spec, wire_schema=compile_schema(spec), harness_version=runtime.__version__)
    return runtime, bound


@dataclass(frozen=True, slots=True)
class GrantFixture:
    """The initial and explicitly wider native grants for one scenario."""

    spec: Any
    initial: Any
    expanded: Any

    @property
    def mapper_spec_id(self) -> str:
        return self.spec.mapper_spec_id

    @property
    def initial_id(self) -> str:
        return grant_identity(self.initial)

    @property
    def expanded_id(self) -> str:
        return grant_identity(self.expanded)


def make_grant_fixture(
    spec_or_path: Any,
    *,
    provider: str = "recorded",
    purpose: str = "Synthetic evaluation provider calls.",
    input_fields: tuple[str, ...] = (),
    document_classes: tuple[str, ...] = (),
    recurring: bool = True,
    initial_max_calls: int = 2,
    initial_max_tokens: int = 100,
    initial_max_usd: float = 0.01,
    expanded_max_calls: int = 10,
    expanded_max_tokens: int = 1000,
    expanded_max_usd: float = 0.10,
    granted_by: str = "evaluation-runner",
) -> GrantFixture:
    """Construct two native grants bound to the closure's bound spec hash."""

    runtime, spec = _bound_mapper_spec(spec_or_path)
    for name, value in (
        ("initial_max_calls", initial_max_calls),
        ("initial_max_tokens", initial_max_tokens),
        ("initial_max_usd", initial_max_usd),
        ("expanded_max_calls", expanded_max_calls),
        ("expanded_max_tokens", expanded_max_tokens),
        ("expanded_max_usd", expanded_max_usd),
    ):
        _positive(value, name)
    Grant = runtime.Grant
    common = dict(
        mapper_spec_id=spec.mapper_spec_id,
        provider=provider,
        model=spec.model,
        corroboration_model=getattr(spec, "corroboration_model", ""),
        purpose=purpose,
        input_fields=tuple(input_fields),
        document_classes=tuple(document_classes),
        pii_category="none",
        recurring=recurring,
        expires_at=FIXED_EXPIRY,
        granted_by=granted_by,
        granted_at=FIXED_GRANTED_AT,
    )
    initial = Grant(
        **common,
        max_calls=initial_max_calls,
        max_tokens=initial_max_tokens,
        max_usd=initial_max_usd,
    )
    expanded = Grant(
        **common,
        max_calls=expanded_max_calls,
        max_tokens=expanded_max_tokens,
        max_usd=expanded_max_usd,
    )
    validate_widening(initial, expanded)
    return GrantFixture(spec=spec, initial=initial, expanded=expanded)


@dataclass(frozen=True, slots=True)
class GrantExpansionStep:
    """One declared operator turn that performs exactly one grant widening."""

    turn: int
    replacement: Any
    justification: str = "Operator-approved cumulative budget expansion."

    def __post_init__(self) -> None:
        if isinstance(self.turn, bool) or not isinstance(self.turn, int) or self.turn < 1:
            raise GrantKitError("grant expansion turn must be a positive integer")
        if not self.justification.strip():
            raise GrantKitError("grant expansion requires a non-empty justification")


class ScriptedGrantOperator:
    """Select the initial grant until the declared turn, then widen once."""

    def __init__(self, fixture: GrantFixture, *, expansion_turn: int, justification: str = "Operator-approved cumulative budget expansion."):
        self.fixture = fixture
        self.step = GrantExpansionStep(expansion_turn, fixture.expanded, justification)
        self._installed = False
        self._expanded = False

    def install(self, ledger: Any) -> Any:
        if self._installed:
            raise GrantKitError("initial grant has already been installed")
        ledger.issue(self.fixture.initial, turn=0)
        self._installed = True
        return self.fixture.initial

    def grant_for_turn(self, turn: int, ledger: Any) -> Any:
        if not self._installed:
            raise GrantKitError("install the initial grant before selecting a turn grant")
        if turn < 1:
            raise GrantKitError("operator turn must be positive")
        if turn < self.step.turn:
            if self._expanded:
                raise GrantKitError("grant expansion was applied after its declared turn")
            return self.fixture.initial
        if turn == self.step.turn:
            if self._expanded:
                raise GrantKitError("grant expansion step was applied more than once")
            ledger.expand(
                self.fixture.expanded,
                turn=turn,
                justification=self.step.justification,
            )
            self._expanded = True
            return self.fixture.expanded
        if not self._expanded:
            raise GrantKitError("operator skipped the declared grant-expansion turn")
        return self.fixture.expanded


__all__ = [
    "FIXED_EXPIRY",
    "FIXED_GRANTED_AT",
    "GrantExpansionStep",
    "GrantFixture",
    "GrantKitError",
    "ScriptedGrantOperator",
    "grant_identity",
    "grant_scope",
    "make_grant_fixture",
    "validate_widening",
]

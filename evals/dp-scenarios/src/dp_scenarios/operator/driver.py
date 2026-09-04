"""Free-authoring operator driver with deterministic safety checks.

The driver owns only the words of one operator turn. Its view never carries
gold, ledger, tool results, file contents, sentinel bytes, or fixture data; it
is never written to disk. ``DriverViolation.detail`` may contain driver text
and is therefore never persisted.

The checks below are pure and use :func:`term_present`. Single-word terms use
word boundaries; multi-word terms are substring-matched by ``term_present``.
That intentional distinction is part of the contract (F22).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
import math
from typing import Literal, Protocol

from .generated import OperatorView, _invoke_with_timeout
from .text_match import term_present


class DriverProvider(Protocol):
    """Callable provider that authors one complete operator turn."""

    def __call__(self, view: "DriverView") -> str:
        """Return the operator's authored message."""


@dataclass(frozen=True, slots=True)
class DriverBeat:
    """A mandatory event beat the authored message must carry."""

    beat_id: str
    required_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DriverView(OperatorView):
    """The narrow, redacted view supplied to a free-authoring provider.

    ``selected_reply`` remains a string for view-family compatibility; the
    engine passes ``''`` when no reply was selected or selection was
    suppressed. ``prior_agent_messages`` is capped by the engine to its last
    two messages. The view is never persisted.
    """

    prior_agent_messages: tuple[str, ...]
    known_facts: tuple[tuple[str, str], ...]
    facts_already_stated: tuple[str, ...]
    beat: DriverBeat | None
    forbidden_terms: tuple[str, ...]
    rejection_notice: str | None

    def to_mapping(self) -> dict[str, object]:
        """Return the provider mapping, adding only the six driver fields."""

        # Explicit dispatch avoids the zero-argument ``super()``/slots class
        # replacement trap in dataclasses on supported Python versions.
        mapping = OperatorView.to_mapping(self)
        mapping.update(
            {
                "prior_agent_messages": list(self.prior_agent_messages),
                "known_facts": [list(fact) for fact in self.known_facts],
                "facts_already_stated": list(self.facts_already_stated),
                "beat": (
                    {"id": self.beat.beat_id, "required_terms": list(self.beat.required_terms)}
                    if self.beat is not None
                    else None
                ),
                "forbidden_terms": list(self.forbidden_terms),
                "rejection_notice": self.rejection_notice,
            }
        )
        return mapping


def leading_violation(
    text: str,
    *,
    forbidden_terms: Sequence[str],
    exempt_texts: Sequence[str],
) -> str | None:
    """Return non-exempt forbidden vocabulary present in authored ``text``.

    A forbidden term is exempt when it is present in any supplied exempt text.
    Exemptions are checked with the same whole-word/multi-word discipline as
    the authored message.
    """

    lowered = text.casefold()
    non_exempt: list[str] = []
    for term in forbidden_terms:
        if not term_present(term, lowered):
            continue
        if any(term_present(term, exempt.casefold()) for exempt in exempt_texts):
            continue
        non_exempt.append(term)
    return ", ".join(non_exempt) or None


def _normalise_operator_message(text: str) -> str:
    return " ".join(text.casefold().split()).rstrip(".!?").strip()


def repeat_violation(text: str, prior_operator_messages: Sequence[str]) -> str | None:
    """Return the one-indexed prior message number repeated by ``text``."""

    normalised = _normalise_operator_message(text)
    for index, prior in enumerate(prior_operator_messages, start=1):
        if normalised == _normalise_operator_message(prior):
            return f"repeats operator message {index}"
    return None


def beat_violation(text: str, beat: DriverBeat | None) -> str | None:
    """Return missing mandatory beat terms, if this turn has a beat."""

    if beat is None:
        return None
    lowered = text.casefold()
    missing = [term for term in beat.required_terms if not term_present(term, lowered)]
    return "missing required beat terms: " + ", ".join(missing) if missing else None


@dataclass(frozen=True, slots=True)
class DriverViolation:
    """A pure post-check failure; details must not enter persisted evidence."""

    kind: Literal["leading", "obstacle", "repeat", "beat"]
    detail: str


@dataclass(frozen=True, slots=True)
class DriverRender:
    """One driver result, including the rejection ladder evidence."""

    text: str
    used_fallback: bool
    reason: str | None
    violations: tuple[DriverViolation, ...]
    attempts: int


@dataclass(frozen=True, slots=True)
class DriverOperator:
    """Author driver turns with one rejection re-ask and safe fallback."""

    provider: DriverProvider | Callable[[DriverView], str]
    model_id: str
    temperature: float
    max_chars: int = 2000
    provider_timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not callable(self.provider):
            raise TypeError("driver provider must be callable")
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("driver model_id must be a non-empty string")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(self.temperature)
            or not 0 <= self.temperature <= 2
        ):
            raise ValueError("driver temperature must be between 0 and 2")
        if isinstance(self.max_chars, bool) or not isinstance(self.max_chars, int) or self.max_chars < 1:
            raise ValueError("driver max_chars must be a positive integer")
        if (
            isinstance(self.provider_timeout_seconds, bool)
            or not isinstance(self.provider_timeout_seconds, (int, float))
            or not math.isfinite(self.provider_timeout_seconds)
            or self.provider_timeout_seconds <= 0
        ):
            raise ValueError("driver provider_timeout_seconds must be positive")

    def author(
        self,
        view: DriverView,
        *,
        fallback: str,
        check: Callable[[str], DriverViolation | None],
    ) -> DriverRender:
        """Author one turn, retrying one rejected message and then falling back."""

        rendered, failure = _invoke_with_timeout(self.provider, view, self.provider_timeout_seconds)
        if failure is not None:
            return DriverRender(fallback, True, failure, (), 1)
        assert rendered is not None
        if len(rendered) > self.max_chars:
            return DriverRender(fallback, True, "provider_output_too_long", (), 1)

        first = check(rendered)
        if first is None:
            return DriverRender(rendered.strip(), False, None, (), 1)

        retry_view = replace(view, rejection_notice=f"{first.kind}: {first.detail}")
        retried, retry_failure = _invoke_with_timeout(self.provider, retry_view, self.provider_timeout_seconds)
        if retry_failure is not None:
            return DriverRender(fallback, True, retry_failure, (first,), 2)
        assert retried is not None
        if len(retried) > self.max_chars:
            return DriverRender(fallback, True, "provider_output_too_long", (first,), 2)

        second = check(retried)
        if second is not None:
            return DriverRender(fallback, True, f"driver_{second.kind}_rejected", (first, second), 2)
        return DriverRender(retried.strip(), False, None, (first,), 2)


__all__ = [
    "DriverBeat",
    "DriverOperator",
    "DriverProvider",
    "DriverRender",
    "DriverViolation",
    "DriverView",
    "beat_violation",
    "leading_violation",
    "repeat_violation",
]

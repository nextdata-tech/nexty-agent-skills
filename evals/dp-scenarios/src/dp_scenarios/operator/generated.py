"""Guarded LLM-generated operator surfaces.

This module deliberately does not own scenario state or phase transitions.  A
deterministic :class:`OperatorEngine` first selects the expected operator reply;
the provider may only render that selection in natural language.  The view
contains no gold data, ledger, tool result, or touched-file bytes.  Its agent
message is untrusted context and must be sentinel-redacted by the engine
before it reaches an external provider.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import threading
from typing import Protocol

from .persona import PersonaCard


class OperatorProvider(Protocol):
    """Callable provider used to render one already-selected operator reply."""

    def __call__(self, view: "OperatorView") -> str:
        """Return a natural-language rendering of the selected reply."""


@dataclass(frozen=True, slots=True)
class OperatorView:
    """The intentionally narrow state visible to a generated operator."""

    turn: int
    phase: int
    persona_id: str
    persona_label: str
    persona_vocabulary: tuple[str, ...]
    persona_behaviors: tuple[str, ...]
    agent_message: str
    selected_reply: str
    prior_operator_messages: tuple[str, ...]
    remaining_turns: int

    @classmethod
    def from_persona(
        cls,
        *,
        turn: int,
        phase: int,
        persona: PersonaCard,
        agent_message: str,
        selected_reply: str,
        prior_operator_messages: Sequence[str],
        remaining_turns: int,
    ) -> "OperatorView":
        """Build a view from only public persona and conversation surface data."""

        return cls(
            turn=turn,
            phase=phase,
            persona_id=persona.id,
            persona_label=persona.label,
            persona_vocabulary=tuple(persona.vocabulary),
            persona_behaviors=tuple(sorted(str(key) for key, value in persona.behaviors.items() if value)),
            agent_message=agent_message,
            selected_reply=selected_reply,
            prior_operator_messages=tuple(prior_operator_messages),
            remaining_turns=remaining_turns,
        )

    def to_mapping(self) -> dict[str, object]:
        """Return the complete provider input with no hidden harness fields."""

        return {
            "turn": self.turn,
            "phase": self.phase,
            "persona": {
                "id": self.persona_id,
                "label": self.persona_label,
                "vocabulary": list(self.persona_vocabulary),
                "behaviors": list(self.persona_behaviors),
            },
            "agent_message": self.agent_message,
            "selected_reply": self.selected_reply,
            "prior_operator_messages": list(self.prior_operator_messages),
            "remaining_turns": self.remaining_turns,
        }


def _invoke_with_timeout(
    provider: Callable[[OperatorView], object],
    view: OperatorView,
    timeout: float,
) -> tuple[str | None, str | None]:
    """Invoke one provider call without allowing it to wedge the engine.

    The second item is a deterministic failure reason.  Provider calls run in
    a daemon thread because a timed-out provider cannot be cancelled safely;
    importantly, this helper never retries the call.
    """

    result: dict[str, object] = {}

    def invoke() -> None:
        try:
            result["value"] = provider(view)
        except Exception as exc:  # provider failures must not wedge the scenario
            result["error"] = exc

    worker = threading.Thread(target=invoke, name="dp-scenario-operator", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return None, "provider_timeout"
    error = result.get("error")
    if isinstance(error, Exception):
        # ``DriverProviderError`` is the contract type a provider raises *after*
        # scrubbing its own message, so its text is safe to record and is the
        # only thing that explains the failure. Reducing every provider failure
        # to a bare type name cost a 22-minute live run its diagnosis: all six
        # authorable turns recorded ``provider_error:DriverProviderError`` while
        # the API had actually replied "Unsupported parameter: 'max_tokens' ...
        # Use 'max_completion_tokens' instead" every time. Any other exception
        # type keeps the type name only, because nothing promises its message
        # has been scrubbed.
        detail = ""
        if type(error).__name__ == "DriverProviderError":
            message = " ".join(str(error).split())[:200]
            if message:
                detail = f":{message}"
        return None, f"provider_error:{type(error).__name__}{detail}"
    rendered = result.get("value")
    if not isinstance(rendered, str) or not rendered.strip():
        return None, "provider_empty"
    return rendered, None


@dataclass(frozen=True, slots=True)
class OperatorRender:
    """One provider result, including whether the deterministic fallback won."""

    text: str
    used_fallback: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class GeneratedOperator:
    """Render selected replies through a provider with fail-safe guardrails."""

    provider: OperatorProvider | Callable[[OperatorView], str]
    max_chars: int = 2000
    provider_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not callable(self.provider):
            raise TypeError("generated operator provider must be callable")
        if isinstance(self.max_chars, bool) or not isinstance(self.max_chars, int) or self.max_chars < 1:
            raise ValueError("generated operator max_chars must be a positive integer")
        if self.provider_timeout_seconds <= 0:
            raise ValueError("generated operator provider_timeout_seconds must be positive")

    def render(
        self,
        view: OperatorView,
        *,
        fallback: str,
        validate: Callable[[str], None],
    ) -> OperatorRender:
        """Render one selected reply, falling back on every provider failure."""

        rendered, failure = _invoke_with_timeout(self.provider, view, self.provider_timeout_seconds)
        if failure is not None:
            return OperatorRender(fallback, True, failure)
        assert rendered is not None
        if len(rendered) > self.max_chars:
            return OperatorRender(fallback, True, "provider_output_too_long")
        try:
            validate(rendered)
        except Exception as exc:
            return OperatorRender(fallback, True, f"provider_output_rejected:{type(exc).__name__}")
        return OperatorRender(rendered, False)


__all__ = ["GeneratedOperator", "OperatorProvider", "OperatorRender", "OperatorView"]

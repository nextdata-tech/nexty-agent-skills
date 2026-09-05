"""Strict data-backed persona cards.

Cards are validated before a run starts and unknown keys fail closed.  The
engine remains the sole owner of deterministic state and, on the scripted
path, selects only the fixed reply bank material.

A persona is the *voice and tactic* axis of the operator: how this particular
stakeholder behaves, never what they know.  Facts belong on the scenario axis,
in the answer sheet, where they can be checked against the gold the run is
graded on.  ``confidently-wrong`` is the standing counter-example -- its bank
holds factual claims ("The API is down") -- and it is why ``stance_when_unknown``
exists as a tactic rather than another canned sentence.

Under a driver, ``behaviors``, ``label`` and ``vocabulary`` *are* engine inputs:
they are composed into the authoring prompt.  This docstring previously said
they were validated grading metadata only, which stopped being true when the
driver landed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml


class PersonaError(ValueError):
    """Raised when a persona card is absent, malformed, or not closed."""


PERSONA_KEYS = frozenset(
    {
        "version",
        "id",
        "label",
        "patience_turns",
        "vocabulary",
        "behaviors",
        "reply_bank",
        "fallback",
        "stance_when_unknown",
    }
)
# Optional because the scripted path never reads it and every pre-driver card
# predates it.  Required keys are the rest of PERSONA_KEYS.
OPTIONAL_PERSONA_KEYS = frozenset({"stance_when_unknown"})

#: How this persona behaves when asked for a decision or preference the
#: scenario never encoded.  This is a tactic, not a sentence: the driver
#: renders it in the persona's own voice.  Every value must hand the floor
#: back to the agent with a direction -- an operator that merely says "no" is
#: what wedged a live run for eight turns.
STANCE_WHEN_UNKNOWN = frozenset(
    {
        "defer_upward",      # will not decide; pushes it back citing someone else
        "ask_back",          # turns the question around
        "push_for_speed",    # tells the agent to pick whatever is fastest
        "approve_anything",  # accepts whatever the agent proposes
        "assert_default",    # states a confident opinion, right or not
    }
)
DEFAULT_STANCE_WHEN_UNKNOWN = "ask_back"
BEHAVIOR_KEYS = frozenset(
    {
        "browser_level_vocabulary",
        "business_vocabulary",
        "loose_technical_vocabulary",
        "ignores_jargon",
        "repeats_the_ask",
        "refuses_tradeoffs",
        "instant_approval",
        "approves_without_reading",
        "defers_decisions",
        "never_frustrated",
        "interrogative",
        "demands_definitions",
        "challenges_intermediate_numbers",
        "asks_for_row_examples",
        "decides_everything",
        "decides_twice_differently",
        "doubles_down_once",
        "concedes_after_correction",
        "misapplied_engineering_vocabulary",
        "goes_quiet_at_jargon",
        "reopens_questions",
        "refuses_risk_bearing_decisions",
        "deadline_driven",
        "kpi_names_only",
        "relays_third_party_questions",
        "rejects_caveats",
        "refuses_decisions",
        "escalation_bait",
        "no_pressure_behaviour",
    }
)
REPLY_CATEGORIES = frozenset(
    {"source_question", "approval_request", "decision_request", "status_query", "other"}
)


def _mapping(value: object, location: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PersonaError(f"{location} must be a mapping")
    return dict(value)


def _unknown(value: Mapping[str, object], allowed: set[str] | frozenset[str], location: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise PersonaError(f"{location} contains unknown key(s): {', '.join(unknown)}")


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PersonaError(f"{location} must be a non-empty string")
    return value


def _string_tuple(value: object, location: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise PersonaError(f"{location} must be a list of strings")
    result = tuple(_string(item, f"{location}[{index}]") for index, item in enumerate(value))
    if not result:
        raise PersonaError(f"{location} must not be empty")
    return result


@dataclass(frozen=True, slots=True)
class PersonaCard:
    """Validated immutable card containing only fixed reply material."""

    version: int
    persona_id: str
    label: str
    patience_turns: int
    vocabulary: tuple[str, ...]
    behaviors: Mapping[str, object]
    reply_bank: Mapping[str, tuple[str, ...]]
    fallback: str
    stance_when_unknown: str = DEFAULT_STANCE_WHEN_UNKNOWN

    @property
    def id(self) -> str:
        """Return the fixture identity used by scenario manifests."""

        return self.persona_id

    @property
    def no_leading_fallback(self) -> str:
        """Return the fixed fallback that never volunteers a diagnosis."""

        return self.fallback

    def replies_for(self, category: str) -> tuple[str, ...]:
        """Return the fixed reply bank for one matcher category."""

        return self.reply_bank.get(category, (self.fallback,))

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "PersonaCard":
        """Construct a card through the strict module validator."""

        return persona_from_mapping(value)

    def to_mapping(self) -> dict[str, object]:
        """Return a canonical, JSON-ready representation for hashing."""

        return {
            "version": self.version,
            "id": self.persona_id,
            "label": self.label,
            "patience_turns": self.patience_turns,
            "vocabulary": list(self.vocabulary),
            "behaviors": dict(self.behaviors),
            "reply_bank": {key: list(value) for key, value in self.reply_bank.items()},
            "fallback": self.fallback,
            "stance_when_unknown": self.stance_when_unknown,
        }


def persona_from_mapping(value: Mapping[str, object]) -> PersonaCard:
    """Validate and construct a persona card from a mapping."""

    raw = _mapping(value, "persona")
    _unknown(raw, PERSONA_KEYS, "persona")
    missing = sorted((PERSONA_KEYS - OPTIONAL_PERSONA_KEYS) - set(raw))
    if missing:
        raise PersonaError(f"persona is missing key(s): {', '.join(missing)}")
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise PersonaError("persona.version must be integer 1")
    patience = raw["patience_turns"]
    if isinstance(patience, bool) or not isinstance(patience, int) or patience < 0:
        raise PersonaError("persona.patience_turns must be a non-negative integer")

    behavior_raw = _mapping(raw["behaviors"], "persona.behaviors")
    _unknown(behavior_raw, BEHAVIOR_KEYS, "persona.behaviors")
    behaviors = MappingProxyType(dict(behavior_raw))
    reply_raw = _mapping(raw["reply_bank"], "persona.reply_bank")
    _unknown(reply_raw, REPLY_CATEGORIES, "persona.reply_bank")
    replies: dict[str, tuple[str, ...]] = {}
    for category in sorted(REPLY_CATEGORIES):
        if category not in reply_raw:
            raise PersonaError(f"persona.reply_bank is missing category {category!r}")
        replies[category] = _string_tuple(reply_raw[category], f"persona.reply_bank.{category}")
    fallback = _string(raw["fallback"], "persona.fallback")
    stance = raw.get("stance_when_unknown", DEFAULT_STANCE_WHEN_UNKNOWN)
    if stance not in STANCE_WHEN_UNKNOWN:
        raise PersonaError(
            "persona.stance_when_unknown must be one of: " + ", ".join(sorted(STANCE_WHEN_UNKNOWN))
        )
    return PersonaCard(
        version=version,
        persona_id=_string(raw["id"], "persona.id"),
        label=_string(raw["label"], "persona.label"),
        patience_turns=patience,
        vocabulary=_string_tuple(raw["vocabulary"], "persona.vocabulary"),
        behaviors=behaviors,
        reply_bank=MappingProxyType(replies),
        fallback=fallback,
        stance_when_unknown=stance,
    )


def load_persona(path: str | Path) -> PersonaCard:
    """Load and validate one YAML persona card."""

    card_path = Path(path)
    try:
        value = yaml.safe_load(card_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PersonaError(f"could not read persona card {card_path}: {exc}") from exc
    return persona_from_mapping(value)


load_persona_card = load_persona


__all__ = [
    "BEHAVIOR_KEYS",
    "DEFAULT_STANCE_WHEN_UNKNOWN",
    "OPTIONAL_PERSONA_KEYS",
    "PERSONA_KEYS",
    "STANCE_WHEN_UNKNOWN",
    "REPLY_CATEGORIES",
    "PersonaCard",
    "PersonaError",
    "load_persona",
    "load_persona_card",
    "persona_from_mapping",
]

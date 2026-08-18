"""Deterministic classification and fixed-reply selection.

The matcher is an inspectable ordered rule bank, not a model. Declared
decisions are checked before the generic no-leading obstacle guard, so a
scenario's planted judgement cannot be shadowed by incidental infrastructure
vocabulary. The exemption is per question: an obstacle term is exempt only
when that same message matches every term of a declared decision; declaring a
compound decision does not globally remove its words from unrelated questions.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Pattern

from .answer_sheet import AnswerSheet
from .persona import PersonaCard


class MatcherError(ValueError):
    """Raised when a reply bank cannot satisfy the no-leading invariant."""


class Category(str, Enum):
    """Closed categories recorded for each agent turn."""

    SOURCE_QUESTION = "source_question"
    APPROVAL_REQUEST = "approval_request"
    DECISION_REQUEST = "decision_request"
    STATUS_QUERY = "status_query"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class MatchResult:
    """One deterministic classification and its fixed response."""

    category: Category
    rule_id: str
    reply: str
    decision_id: str | None = None
    answer_key: str | None = None
    matched: bool = True
    obstacle_question: bool = False

    @property
    def matched_rule_id(self) -> str:
        """Return the stable rule identifier used by evidence rows."""

        return self.rule_id


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_id: str
    category: Category
    pattern: Pattern[str]


DEFAULT_OBSTACLE_TERMS = (
    "proxy",
    "cors",
    "timeout",
    "api is down",
    "401",
    "403",
    "404",
    "credential",
    "auth",
    "token",
    "rate limit",
    "permission",
    "missing header",
    "secret",
)

_RULES = (
    _Rule(
        "source.question",
        Category.SOURCE_QUESTION,
        re.compile(
            r"\b(source|data|field|column|endpoint|resource|record|row|input|table|where\s+did)\b",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        "approval.request",
        Category.APPROVAL_REQUEST,
        re.compile(r"\b(approve|approval|sign\s*off|looks\s+good|proceed|publish|ship)\b", re.IGNORECASE),
    ),
    _Rule(
        "decision.request",
        Category.DECISION_REQUEST,
        re.compile(r"\b(choose|which|should\s+we|prefer|option|decision|decide|yes\s*/\s*no)\b|\?", re.IGNORECASE),
    ),
    _Rule(
        "status.query",
        Category.STATUS_QUERY,
        re.compile(r"\b(status|done|finished|finish|complete|where\s+are\s+we|what(?:'s|\s+is)\s+next)\b", re.IGNORECASE),
    ),
)


def _contains_term(message: str, terms: tuple[str, ...]) -> bool:
    lowered = message.casefold()
    for term in terms:
        if not term:
            continue
        candidate = term.casefold()
        if any(character.isspace() for character in candidate):
            if candidate in lowered:
                return True
        elif re.search(r"(?<!\w)" + re.escape(candidate) + r"(?!\w)", lowered):
            return True
    return False


def _contains_declared_term(value: str | bytes, terms: tuple[str, ...]) -> bool:
    """Check reachable text without making the global question vocabulary a leak rule."""

    if isinstance(value, bytes):
        lowered = value.lower()
        return any(term and term.casefold().encode("utf-8").lower() in lowered for term in terms)
    return _contains_term(value, terms)


def _reachable_reply_material(persona: PersonaCard, answer_sheet: AnswerSheet) -> tuple[str, ...]:
    values: list[str] = [answer_sheet.opening_message, *answer_sheet.turns, persona.fallback]
    values.extend(reply for category in sorted(persona.reply_bank) for reply in persona.reply_bank[category])
    values.extend(answer_sheet.source_answers.values())
    values.extend(answer.answer for answer in answer_sheet.decision_answers.values())
    values.extend(answer_sheet.status_answers.values())
    return tuple(values)


def validate_reachable_material(
    persona: PersonaCard,
    answer_sheet: AnswerSheet,
    *,
    extra_material: Iterable[str | bytes] = (),
    obstacle_terms: tuple[str, ...] | list[str] = (),
) -> None:
    """Reject any agent-visible string that names a scenario-declared obstacle."""

    declared = tuple(dict.fromkeys((*answer_sheet.obstacle_terms, *obstacle_terms)))
    for value in (*_reachable_reply_material(persona, answer_sheet), *tuple(extra_material)):
        if _contains_declared_term(value, declared):
            raise MatcherError("a fixed operator reply contains a planted obstacle term")


class MatcherBank:
    """Classify messages and select only predeclared reply strings."""

    def __init__(
        self,
        persona: PersonaCard,
        answer_sheet: AnswerSheet,
        *,
        obstacle_terms: tuple[str, ...] | list[str] = (),
        extra_material: Iterable[str | bytes] = (),
    ) -> None:
        self.persona = persona
        self.answer_sheet = answer_sheet
        declared = tuple(dict.fromkeys((*answer_sheet.obstacle_terms, *obstacle_terms)))
        self.obstacle_terms = declared
        question_terms = tuple(dict.fromkeys((*DEFAULT_OBSTACLE_TERMS, *declared)))
        # A matching decision returned above is the only per-question exemption.
        self.question_obstacle_terms = question_terms
        validate_reachable_material(
            persona,
            answer_sheet,
            extra_material=extra_material,
            obstacle_terms=obstacle_terms,
        )

    def _validate_replies(self) -> None:
        """Compatibility hook retained for callers that explicitly revalidate a bank."""

        validate_reachable_material(self.persona, self.answer_sheet, obstacle_terms=self.obstacle_terms)

    def validate_outgoing_message(self, message: str) -> None:
        """Validate composed text immediately before transport sends it.

        The empty-message check is an author-error guard: operator-driven
        paths already provide non-empty scripted text or matcher replies. It
        is not the screenshot/wrong-file replacement filter, which suppresses
        only an event card's text when its attachment replaces the message.
        """

        if not isinstance(message, str):
            raise TypeError("outgoing operator message must be a string")
        if not message.strip():
            raise MatcherError("the composed operator message must not be empty")
        if _contains_term(message, self.obstacle_terms):
            raise MatcherError("the composed operator message contains a planted obstacle term")

    def classify(self, message: str) -> MatchResult:
        """Return a stable category and rule id without selecting a reply."""

        if not isinstance(message, str):
            raise TypeError("agent message must be a string")
        is_question = "?" in message or bool(re.match(r"\s*(who|what|where|when|why|how|can|could|should|is|are|do|does)\b", message, re.IGNORECASE))
        decision = self.answer_sheet.answer_for_decision(message)
        if decision is not None:
            return MatchResult(
                Category.DECISION_REQUEST,
                f"decision.answer.{decision.decision_id}",
                decision.answer,
                decision_id=decision.decision_id,
            )
        if is_question and _contains_term(message, self.question_obstacle_terms):
            return MatchResult(
                Category.OTHER,
                "fallback.no-leading",
                self.persona.no_leading_fallback,
                matched=False,
                obstacle_question=True,
            )
        for rule in _RULES:
            if rule.pattern.search(message):
                return MatchResult(rule.category, rule.rule_id, "", matched=True)
        return MatchResult(Category.OTHER, "fallback.no-leading", self.persona.no_leading_fallback, matched=False)

    def reply_for(self, message: str) -> MatchResult:
        """Classify one message and choose its fixed reply."""

        classified = self.classify(message)
        if classified.category is Category.OTHER:
            return classified
        if classified.category is Category.DECISION_REQUEST and classified.decision_id is not None:
            return classified
        if classified.category is Category.SOURCE_QUESTION:
            source = self.answer_sheet.answer_for_source(message)
            if source is not None:
                key, answer = source
                return MatchResult(
                    Category.SOURCE_QUESTION,
                    f"source.answer.{key}",
                    answer,
                    answer_key=key,
                )
            return MatchResult(
                Category.SOURCE_QUESTION,
                "persona.source_question",
                self.persona.replies_for(Category.SOURCE_QUESTION.value)[0],
                matched=False,
            )
        if classified.category is Category.STATUS_QUERY:
            status = self.answer_sheet.answer_for_status(message)
            if status is not None:
                key, answer = status
                return MatchResult(Category.STATUS_QUERY, f"status.answer.{key}", answer, answer_key=key)
        bank = self.persona.replies_for(classified.category.value)
        return MatchResult(classified.category, f"persona.{classified.category.value}", bank[0])


def classify_and_reply(
    message: str,
    persona: PersonaCard,
    answer_sheet: AnswerSheet,
    *,
    obstacle_terms: tuple[str, ...] | list[str] = (),
) -> MatchResult:
    """Convenience wrapper for one deterministic match."""

    return MatcherBank(persona, answer_sheet, obstacle_terms=obstacle_terms).reply_for(message)


__all__ = [
    "Category",
    "DEFAULT_OBSTACLE_TERMS",
    "MatchResult",
    "MatcherBank",
    "MatcherError",
    "classify_and_reply",
]

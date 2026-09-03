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
from dataclasses import dataclass, replace
from enum import Enum
from typing import Pattern

from .answer_sheet import AnswerSheet, script_turn_text
from .persona import PersonaCard
from .text_match import contains_any_term


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
    ground_truth: bool = False
    approval_requested: bool = False
    """Whether the agent solicited approval, orthogonally to ``category``.

    Agents present a spec and ask a factual question in the same breath --
    "Please approve the blueprint. Also, what does updatedAt mean on a deal?"
    Making approval a first-match *category* stole exactly those messages from
    the source/decision/ground-truth lookup, so the operator answered a stock
    approval line instead of the fact it knows, precisely when the fact
    mattered most. The solicitation is therefore recorded as a flag on
    whatever category actually resolves the reply.
    """

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

# The unambiguous solicitation verbs. This is read as an orthogonal flag on
# every result (see MatchResult.approval_requested), not as a category that
# outranks the factual lookups. "looks good" is deliberately absent: it is
# ordinary conversational filler ("the data looks good so far") and reading it
# as a request for sign-off is a false positive far more often than not.
APPROVAL_REQUEST_PATTERN = re.compile(r"\b(approve[sd]?|approval|sign\s*off)\b", re.IGNORECASE)

_RULES = (
    # _RULES is first-match-wins and the factual rules come first on purpose.
    # Whether the agent also asked for approval is carried alongside the
    # category, so a message that both presents a spec and asks a real
    # question is still answered from the source bank, the decision bank, or
    # the ground-truth brief.
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
        APPROVAL_REQUEST_PATTERN,
    ),
    # Weaker, more ambiguous approval vocabulary, kept under its own rule id so
    # a transcript reader can tell which of the two fired.
    _Rule(
        "approval.proceed",
        Category.APPROVAL_REQUEST,
        re.compile(r"\b(proceed|publish|ship)\b", re.IGNORECASE),
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
    return contains_any_term(message, terms)


def _contains_declared_term(value: str | bytes, terms: tuple[str, ...]) -> bool:
    """Check reachable text without making the global question vocabulary a leak rule."""

    if isinstance(value, bytes):
        lowered = value.lower()
        return any(term and term.casefold().encode("utf-8").lower() in lowered for term in terms)
    return _contains_term(value, terms)


def _reachable_reply_material(persona: PersonaCard, answer_sheet: AnswerSheet) -> tuple[str, ...]:
    # A turn may be declared as a mapping carrying the substitution switch, so
    # take its text rather than the declaration: the obstacle scan must still
    # see every string that can actually reach the agent.
    values: list[str] = [
        answer_sheet.opening_message,
        *(script_turn_text(turn) for turn in answer_sheet.turns),
        persona.fallback,
    ]
    values.extend(reply for category in sorted(persona.reply_bank) for reply in persona.reply_bank[category])
    values.extend(answer_sheet.source_answers.values())
    values.extend(answer.answer for answer in answer_sheet.decision_answers.values())
    values.extend(answer_sheet.status_answers.values())
    values.extend(fact.fact for fact in answer_sheet.ground_truth.values())
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

    def validate_generated_surface(self, message: str) -> None:
        """Apply the stricter no-obstacle guard to model-rendered operator text."""

        self.validate_outgoing_message(message)
        if _contains_term(message, self.question_obstacle_terms):
            raise MatcherError("the generated operator surface contains an obstacle term")

    @staticmethod
    def _with_approval_flag(result: MatchResult, message: str) -> MatchResult:
        """Attach the orthogonal solicitation flag to an already-chosen result."""

        if result.approval_requested or not APPROVAL_REQUEST_PATTERN.search(message):
            return result
        return replace(result, approval_requested=True)

    def classify(self, message: str) -> MatchResult:
        """Return a stable category and rule id without selecting a reply."""

        if not isinstance(message, str):
            raise TypeError("agent message must be a string")
        return self._with_approval_flag(self._classify(message), message)

    def _classify(self, message: str) -> MatchResult:
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

        return self._with_approval_flag(self._reply_for(message), message)

    def _reply_for(self, message: str) -> MatchResult:
        classified = self.classify(message)
        if classified.category is Category.OTHER:
            return classified
        if classified.category is Category.DECISION_REQUEST and classified.decision_id is not None:
            return classified
        if classified.category is Category.SOURCE_QUESTION:
            # The brief is consulted before the source answers, not only after
            # them. A ground-truth fact fires only when its *whole* declared
            # term set is present, so a matching fact is strictly more specific
            # than a source answer, which fires on a single topic key name.
            # Consulting the sheet first let one generic key ("data") shadow
            # every specific fact an author added precisely because the source
            # answer was the wrong answer to that question. Scenarios that
            # declare no brief are unaffected: an empty mapping never matches.
            found = self.answer_sheet.answer_for_ground_truth(message)
            if found is not None:
                key, fact = found
                return MatchResult(
                    Category.SOURCE_QUESTION,
                    f"ground_truth.{key}",
                    fact,
                    answer_key=key,
                    ground_truth=True,
                )
            source = self.answer_sheet.answer_for_source(message)
            if source is not None:
                key, answer = source
                return MatchResult(
                    Category.SOURCE_QUESTION,
                    f"source.answer.{key}",
                    answer,
                    answer_key=key,
                )
            return self._unmatched(classified, message)
        if classified.category is Category.STATUS_QUERY:
            status = self.answer_sheet.answer_for_status(message)
            if status is not None:
                key, answer = status
                return MatchResult(Category.STATUS_QUERY, f"status.answer.{key}", answer, answer_key=key)
            return self._unmatched(classified, message)
        if classified.category is Category.DECISION_REQUEST:
            return self._unmatched(classified, message)
        # APPROVAL_REQUEST has no declared-fact lookup: whether to approve is
        # a persona behavioral choice, not a fact a ground-truth brief holds.
        bank = self.persona.replies_for(classified.category.value)
        return MatchResult(classified.category, f"persona.{classified.category.value}", bank[0])

    def _unmatched(self, classified: MatchResult, message: str) -> MatchResult:
        """Resolve a factual category with no declared answer-sheet match.

        No ``ground_truth`` brief declared (the common, legacy case) keeps
        the exact prior behavior byte-for-byte: the persona's own stock line
        for that category, reported unmatched. A declared brief is consulted
        first and, when it covers the question, answered from it — a real
        fact, never fabricated. Only when neither the answer sheet nor the
        brief covers the question does the operator fall back to its fixed,
        never-leading "I don't know, you tell me" line: this is the one path
        that must never produce a confidently wrong or confidently empty
        scripted answer.
        """

        if not self.answer_sheet.ground_truth:
            bank = self.persona.replies_for(classified.category.value)
            return MatchResult(
                classified.category,
                f"persona.{classified.category.value}",
                bank[0],
                matched=False,
            )
        found = self.answer_sheet.answer_for_ground_truth(message)
        if found is not None:
            key, fact = found
            return MatchResult(
                classified.category,
                f"ground_truth.{key}",
                fact,
                answer_key=key,
                ground_truth=True,
            )
        return MatchResult(
            classified.category,
            f"unmatched.{classified.category.value}",
            self.persona.no_leading_fallback,
            matched=False,
        )


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
    "APPROVAL_REQUEST_PATTERN",
    "Category",
    "DEFAULT_OBSTACLE_TERMS",
    "MatchResult",
    "MatcherBank",
    "MatcherError",
    "classify_and_reply",
]

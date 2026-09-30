"""Validated, non-volunteered operator answers.

The opening message contains only a business outcome.  Source, status, and
decision details are stored as fixed answer-bank entries and are returned only
after a deterministic matcher selects the corresponding question.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from .text_match import term_present


class AnswerSheetError(ValueError):
    """Raised when an answer sheet is incomplete or violates intake rules."""


ANSWER_SHEET_KEYS = frozenset(
    {
        "version",
        "scenario_id",
        "opening_message",
        "turns",
        "source_answers",
        "decision_answers",
        "status_answers",
        "opening_forbidden_terms",
        "open_decision_markers",
        "obstacle_terms",
    }
)

# ``ground_truth`` is deliberately optional: most scenario packages have no
# brief and must keep validating and matching exactly as before.  Only a
# package that declares one opts into brief-backed answers for otherwise
# unmatched questions (see MatcherBank._unmatched).
OPTIONAL_ANSWER_SHEET_KEYS = frozenset(
    {
        "driver_forbidden_terms",
        "ground_truth",
        "gap_stance",
        "reapproval",
        "source_answer_terms",
    }
)

#: What it *means* in this drill that the operator cannot answer something.
#: The scenario axis of the operator's behaviour: the persona supplies the
#: voice, the scenario supplies the stance toward the gap.
#:
#: ``source_is_short`` -- the source genuinely cannot supply what is being
#: asked, so "I do not have that" is the substance under test and the operator
#: must not paper over it.  ``operator_is_uninformed`` -- the data is adequate
#: and the gap is only this stakeholder's own ignorance, so the operator should
#: push the agent to use its judgement and proceed.
GAP_STANCES = frozenset({"source_is_short", "operator_is_uninformed"})
DEFAULT_GAP_STANCE = "operator_is_uninformed"


def _mapping(value: object, location: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AnswerSheetError(f"{location} must be a mapping")
    return dict(value)


def _unknown(value: Mapping[str, object], allowed: set[str] | frozenset[str], location: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise AnswerSheetError(f"{location} contains unknown key(s): {', '.join(unknown)}")


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnswerSheetError(f"{location} must be a non-empty string")
    return value


def script_turn_text(turn: object) -> str:
    """Return the operator text a declared script turn carries.

    A turn is either a plain string or a mapping that also declares the
    switches ``ScriptTurn`` understands: ``substitute_reply``, which marks an
    ask a matcher reply must never replace, and ``approval``, which declares
    that transmitting this turn *is* the operator approving the spec.  Without
    the mapping form both switches exist in the engine but are unreachable
    from scenario data.
    """

    if isinstance(turn, str):
        return turn
    if isinstance(turn, Mapping):
        text = turn.get("text", turn.get("message"))
        if isinstance(text, str):
            return text
    raise AnswerSheetError("a script turn must be a string or a mapping declaring text")


def _script_turns(value: object, location: str) -> tuple[str | Mapping[str, object], ...]:
    """Validate declared operator turns, accepting the ScriptTurn mapping form."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AnswerSheetError(f"{location} must be a list of turns")
    result: list[str | Mapping[str, object]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            if not item.strip():
                raise AnswerSheetError(f"{location}[{index}] must be a non-empty string")
            result.append(item)
            continue
        if not isinstance(item, Mapping):
            raise AnswerSheetError(f"{location}[{index}] must be a string or a mapping")
        allowed = {"text", "message", "substitute_reply", "use_reply", "approval"}
        unknown = sorted(str(name) for name in set(item) - allowed)
        if unknown:
            raise AnswerSheetError(f"{location}[{index}] contains unknown key(s): {', '.join(unknown)}")
        # Mirror ScriptTurn.from_value's rules exactly. A declaration this
        # validator accepts but ScriptTurn later rejects would fail deep in a
        # run rather than at load, which is the opposite of fail-closed.
        if "text" in item and "message" in item:
            raise AnswerSheetError(f"{location}[{index}] declares both text and message")
        if "substitute_reply" in item and "use_reply" in item:
            raise AnswerSheetError(f"{location}[{index}] declares both substitute_reply and use_reply")
        text = item.get("text", item.get("message"))
        if not isinstance(text, str) or not text.strip():
            raise AnswerSheetError(f"{location}[{index}].text must be a non-empty string")
        switch = item.get("substitute_reply", item.get("use_reply", True))
        if not isinstance(switch, bool):
            raise AnswerSheetError(f"{location}[{index}].substitute_reply must be a boolean")
        approval = item.get("approval", False)
        if not isinstance(approval, bool):
            raise AnswerSheetError(f"{location}[{index}].approval must be a boolean")
        result.append(dict(item))
    if not result:
        raise AnswerSheetError(f"{location} must not be empty")
    return tuple(result)


def _strings(value: object, location: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AnswerSheetError(f"{location} must be a list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or (not allow_empty and not item.strip()):
            raise AnswerSheetError(f"{location}[{index}] must be a non-empty string")
        result.append(item)
    if not result and not allow_empty:
        raise AnswerSheetError(f"{location} must not be empty")
    return tuple(result)


def _one_sentence(value: str) -> bool:
    return sum(character in ".!?" for character in value) == 1


def _decision_term_present(term: str, lowered: str) -> bool:
    """Match a declared term, including the existing simple plural form."""

    candidate = term.casefold()
    return candidate in lowered or (
        len(term) > 3
        and term.isalpha()
        and candidate.endswith("s")
        and not candidate.endswith(("ss", "us", "is"))
        and term_present(term[:-1], lowered)
    )


@dataclass(frozen=True, slots=True)
class DecisionAnswer:
    """One fixed or staged answer keyed by a declared business decision id."""

    decision_id: str
    terms: tuple[str, ...]
    answer: str
    synonyms: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}))
    available_after_event: str | None = None
    stages: tuple[str, ...] = ()
    retired_after_event: str | None = None
    available_after_overlay: str | None = None
    retired_after_overlay: str | None = None
    clarify_first: bool = False

    @property
    def is_staged(self) -> bool:
        """Whether this decision advances through multiple solicited answers."""

        return bool(self.stages)

    def response_for_solicitation(self, solicitation_number: int) -> tuple[str, int | None, bool | None]:
        """Return a response and 1-based stage metadata for a solicitation.

        Legacy single-answer decisions intentionally have no stage metadata.
        Staged decisions clamp to their final answer, so a repeated ask after
        the final ruling remains stable.
        """

        if not self.stages:
            return self.answer, None, None
        index = min(max(solicitation_number, 1), len(self.stages)) - 1
        return self.stages[index], index + 1, index == len(self.stages) - 1

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical answer entry."""

        entry: dict[str, object] = {"terms": list(self.terms)}
        if self.stages:
            entry["stages"] = list(self.stages)
        else:
            entry["answer"] = self.answer
        if self.synonyms:
            entry["synonyms"] = {term: list(values) for term, values in self.synonyms.items()}
        if self.available_after_event is not None:
            entry["available_after_event"] = self.available_after_event
        if self.retired_after_event is not None:
            entry["retired_after_event"] = self.retired_after_event
        if self.available_after_overlay is not None:
            entry["available_after_overlay"] = self.available_after_overlay
        if self.retired_after_overlay is not None:
            entry["retired_after_overlay"] = self.retired_after_overlay
        if self.clarify_first:
            entry["clarify_first"] = True
        return entry


@dataclass(frozen=True, slots=True)
class ReapprovalAnswer:
    """A bounded, declared approval for a reviewed plan revision."""

    answer: str
    max_uses: int

    def to_mapping(self) -> dict[str, object]:
        return {"answer": self.answer, "max_uses": self.max_uses}


@dataclass(frozen=True, slots=True)
class GroundTruthFact:
    """One fact the operator actually knows and may state when asked.

    Ground-truth entries are not scripted replies: they exist so an
    unanticipated question still has a correct answer available instead of a
    fabricated or a confidently irrelevant one.  Every declared term must
    appear in the question before a fact is used, the same discipline as a
    declared business decision, so an author is pushed toward specific
    multi-term matches rather than the single generic word that caused a
    confident false match in the field.
    """

    fact_id: str
    terms: tuple[str, ...]
    fact: str

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical ground-truth entry."""

        return {"terms": list(self.terms), "fact": self.fact}


@dataclass(frozen=True, slots=True)
class AnswerSheet:
    """Immutable answer material and the two-layer intake contract."""

    version: int
    scenario_id: str
    opening_message: str
    turns: tuple[str | Mapping[str, object], ...]
    source_answers: Mapping[str, str]
    decision_answers: Mapping[str, DecisionAnswer]
    status_answers: Mapping[str, str]
    opening_forbidden_terms: tuple[str, ...]
    open_decision_markers: tuple[str, ...]
    obstacle_terms: tuple[str, ...]
    driver_forbidden_terms: tuple[str, ...] = ()
    """Separate graded-property vocabulary a driver must never volunteer; absent means undrivable."""
    ground_truth: Mapping[str, GroundTruthFact] = field(default_factory=lambda: MappingProxyType({}))
    gap_stance: str = DEFAULT_GAP_STANCE
    """What an unanswerable question means here; see :data:`GAP_STANCES`."""
    reapproval: ReapprovalAnswer | None = None
    """Optional bounded approval for a revised plan after an authorized review fix."""
    source_answer_terms: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    """Optional semantic aliases for source-answer keys in compound asks."""

    @property
    def turn_one(self) -> str:
        """Return the only permitted first operator message."""

        return self.opening_message

    def answer_for_source(self, question: str) -> tuple[str, str] | None:
        """Return a fixed source answer when its declared key is mentioned.

        The key is matched on a whole-word boundary, the same discipline the
        ground-truth brief and the obstacle scan use. Plain substring
        containment let the one-word key ``data`` fire inside ``database``,
        ``metadata`` and ``data product`` -- in a real live run that answered
        three separate questions with the same schema fact, because a key
        name is a topic label, not a declared term set.
        """

        lowered = question.casefold()
        for key in sorted(self.source_answers):
            answer = self.source_answers[key]
            if term_present(key, lowered) or any(
                term_present(term, lowered)
                for term in self.source_answer_terms.get(key, ())
            ):
                return key, answer
        return None

    def source_answers_for(
        self, question: str, *, include_keys: bool = True
    ) -> tuple[tuple[str, str], ...]:
        """Return declared source answers mentioned by a compound ask.

        ``include_keys=False`` restricts compound secondary selection to the
        answer sheet's explicit semantic aliases. This avoids treating a
        source-key word in a review recap as a second question.
        """

        lowered = question.casefold()
        return tuple(
            (key, self.source_answers[key])
            for key in sorted(self.source_answers)
            if (include_keys and term_present(key, lowered))
            or any(
                term_present(term, lowered)
                for term in self.source_answer_terms.get(key, ())
            )
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "AnswerSheet":
        """Construct a sheet through the strict module validator."""

        return answer_sheet_from_mapping(value)

    def answer_for_decision(
        self,
        question: str,
        *,
        excluded: frozenset[str] = frozenset(),
        available_event_ids: Sequence[str] = (),
        active_overlay_ids: Sequence[str] = (),
    ) -> DecisionAnswer | None:
        """Return the declared decision answer whose terms match the question.

        ``excluded`` skips decisions the caller has already answered, so the
        next declared decision (if any) can match the same text.
        A simple plural term also matches its singular whole word: a declared
        "conversions" decision remains answerable when the agent asks about
        a "conversion" record. Each required term can also declare synonyms;
        one of those alternatives satisfies that term without changing the
        other required terms. Multiword terms keep their literal contract.

        An answer with ``available_after_event`` is considered only after that
        event id appears in ``available_event_ids``. If multiple answers for
        the same ask are unlocked, the one unlocked by the most recently
        delivered event takes precedence; unstaged answers retain their
        existing decision-id ordering.
        """

        lowered = question.casefold()
        event_order = {event_id: index for index, event_id in enumerate(available_event_ids)}
        active_overlays = set(active_overlay_ids)
        eligible = [
            decision
            for decision in self.decision_answers.values()
            if decision.available_after_event is None
            or decision.available_after_event in event_order
            if decision.retired_after_event is None
            or decision.retired_after_event not in event_order
            if decision.available_after_overlay is None
            or decision.available_after_overlay in active_overlays
            if decision.retired_after_overlay is None
            or decision.retired_after_overlay not in active_overlays
        ]
        # Keep the established lexical order for all legacy answers. Staged
        # answers sort ahead of older answers only after their gate event was
        # delivered, with the latest delivered gate winning on a revision.
        eligible.sort(
            key=lambda decision: (
                -event_order.get(decision.available_after_event, -1),
                decision.decision_id,
            )
        )
        for decision in eligible:
            if decision.decision_id in excluded:
                continue
            if all(
                any(
                    _decision_term_present(candidate, lowered)
                    for candidate in (term, *decision.synonyms.get(term, ()))
                )
                for term in decision.terms
            ):
                return decision
        return None

    @property
    def decision_overlay_ids(self) -> frozenset[str]:
        """Declared overlay ids that a chain controller may activate."""

        return frozenset(
            overlay_id
            for decision in self.decision_answers.values()
            for overlay_id in (decision.available_after_overlay, decision.retired_after_overlay)
            if overlay_id is not None
        )

    def answer_for_status(self, question: str) -> tuple[str, str] | None:
        """Return a fixed status answer when its declared key is mentioned."""

        lowered = question.casefold()
        for key in sorted(self.status_answers):
            answer = self.status_answers[key]
            if key.casefold() in lowered:
                return key, answer
        return None

    def answer_for_ground_truth(self, question: str) -> tuple[str, str] | None:
        """Return a declared fact whose every term appears in the question.

        Returns ``None`` — never a guess — when no fact's full term set is
        present, including when no ``ground_truth`` brief was declared at
        all (an empty mapping has nothing to iterate). Each declared term is
        matched on a whole-word boundary (multi-word terms use substring
        containment), the same discipline the matcher applies to obstacle
        terms, so a generic word cannot fire on a longer word that merely
        contains it (``product`` must not match ``production``, ``column``
        must not match ``columns``) and produce a confidently irrelevant
        answer.
        """

        lowered = question.casefold()
        for fact_id in sorted(self.ground_truth):
            fact = self.ground_truth[fact_id]
            if all(term_present(term, lowered) for term in fact.terms):
                return fact_id, fact.fact
        return None

    def contains_open_decision_marker(self, artifact: str) -> bool:
        """Report whether an artifact still carries a declared open marker."""

        return any(marker in artifact for marker in self.open_decision_markers)

    def to_mapping(self) -> dict[str, object]:
        """Return a canonical, JSON-ready representation for script hashing."""

        mapping: dict[str, object] = {
            "version": self.version,
            "scenario_id": self.scenario_id,
            "opening_message": self.opening_message,
            "turns": [dict(turn) if isinstance(turn, Mapping) else turn for turn in self.turns],
            "source_answers": dict(self.source_answers),
            "decision_answers": {
                key: value.to_mapping() for key, value in self.decision_answers.items()
            },
            "status_answers": dict(self.status_answers),
            "opening_forbidden_terms": list(self.opening_forbidden_terms),
            "open_decision_markers": list(self.open_decision_markers),
            "obstacle_terms": list(self.obstacle_terms),
            "ground_truth": {key: value.to_mapping() for key, value in self.ground_truth.items()},
        }
        # Keep legacy sheets round-trippable: an absent optional field is
        # represented by its absence, while every driven sheet carries the
        # non-empty vocabulary into the script hash.
        if self.driver_forbidden_terms:
            mapping["driver_forbidden_terms"] = list(self.driver_forbidden_terms)
        if self.gap_stance != DEFAULT_GAP_STANCE:
            mapping["gap_stance"] = self.gap_stance
        if self.reapproval is not None:
            mapping["reapproval"] = self.reapproval.to_mapping()
        if self.source_answer_terms:
            mapping["source_answer_terms"] = {
                key: list(terms) for key, terms in self.source_answer_terms.items()
            }
        return mapping


def _answer_mapping(value: object, location: str) -> dict[str, str]:
    raw = _mapping(value, location)
    result: dict[str, str] = {}
    for key, answer in raw.items():
        result[_string(key, f"{location} key")] = _string(answer, f"{location}.{key}")
    return result


def _decision_mapping(value: object) -> dict[str, DecisionAnswer]:
    raw = _mapping(value, "answer_sheet.decision_answers")
    result: dict[str, DecisionAnswer] = {}
    for decision_id, entry in raw.items():
        identifier = _string(decision_id, "answer_sheet.decision_answers key")
        # The legacy string form has no optional fields. Initialize every
        # per-entry default before branching so a prior mapping entry cannot
        # leak its clarify_first value into this one.
        clarify_first = False
        available_after_event = None
        retired_after_event = None
        available_after_overlay = None
        retired_after_overlay = None
        stages: tuple[str, ...] = ()
        if isinstance(entry, str):
            terms = (identifier.replace("_", " "),)
            answer = entry
            synonyms: dict[str, tuple[str, ...]] = {}
        else:
            data = _mapping(entry, f"answer_sheet.decision_answers.{identifier}")
            _unknown(
                data,
                {
                    "terms",
                    "answer",
                    "stages",
                    "synonyms",
                    "available_after_event",
                    "retired_after_event",
                    "available_after_overlay",
                    "retired_after_overlay",
                    "clarify_first",
                },
                f"answer_sheet.decision_answers.{identifier}",
            )
            has_answer = "answer" in data
            has_stages = "stages" in data
            if not {"terms"}.issubset(data) or has_answer == has_stages:
                raise AnswerSheetError(
                    f"answer_sheet.decision_answers.{identifier} requires terms and exactly one of answer or stages"
                )
            terms = _strings(data["terms"], f"answer_sheet.decision_answers.{identifier}.terms")
            if has_stages:
                stages = _strings(data["stages"], f"answer_sheet.decision_answers.{identifier}.stages")
                if len(stages) < 2:
                    raise AnswerSheetError(
                        f"answer_sheet.decision_answers.{identifier}.stages must contain at least two answers"
                    )
                answer = stages[0]
            else:
                answer = _string(data["answer"], f"answer_sheet.decision_answers.{identifier}.answer")
            synonyms = {}
            if "synonyms" in data:
                raw_synonyms = _mapping(
                    data["synonyms"], f"answer_sheet.decision_answers.{identifier}.synonyms"
                )
                for term, values in raw_synonyms.items():
                    if term not in terms:
                        raise AnswerSheetError(
                            f"answer_sheet.decision_answers.{identifier}.synonyms must name a declared term"
                        )
                    synonyms[term] = _strings(
                        values, f"answer_sheet.decision_answers.{identifier}.synonyms.{term}"
                    )
            available_after_event = (
                _string(
                    data["available_after_event"],
                    f"answer_sheet.decision_answers.{identifier}.available_after_event",
                )
                if "available_after_event" in data
                else None
            )
            retired_after_event = (
                _string(
                    data["retired_after_event"],
                    f"answer_sheet.decision_answers.{identifier}.retired_after_event",
                )
                if "retired_after_event" in data
                else None
            )
            if available_after_event is not None and available_after_event == retired_after_event:
                raise AnswerSheetError(
                    f"answer_sheet.decision_answers.{identifier} cannot be available and retired after the same event"
                )
            available_after_overlay = (
                _string(
                    data["available_after_overlay"],
                    f"answer_sheet.decision_answers.{identifier}.available_after_overlay",
                )
                if "available_after_overlay" in data
                else None
            )
            clarify_first = data.get("clarify_first", False)
            if not isinstance(clarify_first, bool):
                raise AnswerSheetError(
                    f"answer_sheet.decision_answers.{identifier}.clarify_first must be a boolean"
                )
            retired_after_overlay = (
                _string(
                    data["retired_after_overlay"],
                    f"answer_sheet.decision_answers.{identifier}.retired_after_overlay",
                )
                if "retired_after_overlay" in data
                else None
            )
            if (
                available_after_overlay is not None
                and available_after_overlay == retired_after_overlay
            ):
                raise AnswerSheetError(
                    f"answer_sheet.decision_answers.{identifier} cannot be available and retired after the same overlay"
                )
        result[identifier] = DecisionAnswer(
            identifier,
            terms,
            _string(answer, f"decision {identifier}.answer"),
            MappingProxyType(synonyms),
            available_after_event,
            stages,
            retired_after_event,
            available_after_overlay,
            retired_after_overlay,
            clarify_first,
        )
    return result


def _ground_truth_mapping(value: object) -> dict[str, GroundTruthFact]:
    raw = _mapping(value, "answer_sheet.ground_truth")
    result: dict[str, GroundTruthFact] = {}
    for fact_id, entry in raw.items():
        identifier = _string(fact_id, "answer_sheet.ground_truth key")
        data = _mapping(entry, f"answer_sheet.ground_truth.{identifier}")
        _unknown(data, {"terms", "fact"}, f"answer_sheet.ground_truth.{identifier}")
        if set(data) != {"terms", "fact"}:
            raise AnswerSheetError(
                f"answer_sheet.ground_truth.{identifier} requires terms and fact"
            )
        terms = _strings(data["terms"], f"answer_sheet.ground_truth.{identifier}.terms")
        fact = _string(data["fact"], f"answer_sheet.ground_truth.{identifier}.fact")
        result[identifier] = GroundTruthFact(identifier, terms, fact)
    return result


def _reapproval_mapping(value: object) -> ReapprovalAnswer:
    raw = _mapping(value, "answer_sheet.reapproval")
    _unknown(raw, {"answer", "max_uses"}, "answer_sheet.reapproval")
    if set(raw) != {"answer", "max_uses"}:
        raise AnswerSheetError(
            "answer_sheet.reapproval requires exactly answer and max_uses"
        )
    max_uses = raw["max_uses"]
    if isinstance(max_uses, bool) or not isinstance(max_uses, int) or max_uses < 1:
        raise AnswerSheetError("answer_sheet.reapproval.max_uses must be a positive integer")
    return ReapprovalAnswer(
        _string(raw["answer"], "answer_sheet.reapproval.answer"), max_uses
    )


def answer_sheet_from_mapping(value: Mapping[str, object]) -> AnswerSheet:
    """Validate and construct an answer sheet from a mapping."""

    raw = _mapping(value, "answer_sheet")
    _unknown(raw, ANSWER_SHEET_KEYS | OPTIONAL_ANSWER_SHEET_KEYS, "answer_sheet")
    missing = sorted(ANSWER_SHEET_KEYS - set(raw))
    if missing:
        raise AnswerSheetError(f"answer_sheet is missing key(s): {', '.join(missing)}")
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise AnswerSheetError("answer_sheet.version must be integer 1")
    opening = _string(raw["opening_message"], "answer_sheet.opening_message")
    if not _one_sentence(opening):
        raise AnswerSheetError("answer_sheet.opening_message must be at most one business sentence")
    forbidden = _strings(raw["opening_forbidden_terms"], "answer_sheet.opening_forbidden_terms")
    lowered_opening = opening.casefold()
    leaked = [term for term in forbidden if term.casefold() in lowered_opening]
    if leaked:
        raise AnswerSheetError(
            "answer_sheet.opening_message contains forbidden term(s): " + ", ".join(leaked)
        )
    turns = _script_turns(raw["turns"], "answer_sheet.turns")
    if script_turn_text(turns[0]) != opening:
        raise AnswerSheetError("answer_sheet.turns[0] must equal opening_message")
    # ground_truth is optional; when absent, no fact is ever consulted and the
    # legacy unmatched-question behavior is preserved exactly.  When present,
    # even an empty mapping is validated the same strict way as every other
    # section, so a malformed brief is always a load error, never a silent skip.
    ground_truth = _ground_truth_mapping(raw["ground_truth"]) if "ground_truth" in raw else {}
    driver_forbidden_terms = (
        _strings(raw["driver_forbidden_terms"], "answer_sheet.driver_forbidden_terms")
        if "driver_forbidden_terms" in raw
        else ()
    )
    gap_stance = raw.get("gap_stance", DEFAULT_GAP_STANCE)
    if gap_stance not in GAP_STANCES:
        raise AnswerSheetError(
            "answer_sheet.gap_stance must be one of: " + ", ".join(sorted(GAP_STANCES))
        )
    reapproval = (
        _reapproval_mapping(raw["reapproval"]) if "reapproval" in raw else None
    )
    source_answers = _answer_mapping(raw["source_answers"], "answer_sheet.source_answers")
    source_answer_terms: dict[str, tuple[str, ...]] = {}
    if "source_answer_terms" in raw:
        raw_source_terms = _mapping(raw["source_answer_terms"], "answer_sheet.source_answer_terms")
        unknown_source_keys = sorted(set(raw_source_terms) - set(source_answers))
        if unknown_source_keys:
            raise AnswerSheetError(
                "answer_sheet.source_answer_terms names undeclared source answer(s): "
                + ", ".join(map(str, unknown_source_keys))
            )
        source_answer_terms = {
            _string(key, "answer_sheet.source_answer_terms key"): _strings(
                terms, f"answer_sheet.source_answer_terms.{key}"
            )
            for key, terms in raw_source_terms.items()
        }
    return AnswerSheet(
        version=version,
        scenario_id=_string(raw["scenario_id"], "answer_sheet.scenario_id"),
        opening_message=opening,
        turns=turns,
        source_answers=MappingProxyType(source_answers),
        decision_answers=MappingProxyType(_decision_mapping(raw["decision_answers"])),
        status_answers=MappingProxyType(_answer_mapping(raw["status_answers"], "answer_sheet.status_answers")),
        opening_forbidden_terms=forbidden,
        open_decision_markers=_strings(raw["open_decision_markers"], "answer_sheet.open_decision_markers"),
        obstacle_terms=_strings(raw["obstacle_terms"], "answer_sheet.obstacle_terms", allow_empty=True),
        driver_forbidden_terms=driver_forbidden_terms,
        ground_truth=MappingProxyType(ground_truth),
        gap_stance=gap_stance,
        reapproval=reapproval,
        source_answer_terms=MappingProxyType(source_answer_terms),
    )


def load_answer_sheet(path: str | Path) -> AnswerSheet:
    """Load and validate one YAML answer sheet."""

    sheet_path = Path(path)
    try:
        value = yaml.safe_load(sheet_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise AnswerSheetError(f"could not read answer sheet {sheet_path}: {exc}") from exc
    return answer_sheet_from_mapping(value)


__all__ = [
    "ANSWER_SHEET_KEYS",
    "DEFAULT_GAP_STANCE",
    "GAP_STANCES",
    "OPTIONAL_ANSWER_SHEET_KEYS",
    "AnswerSheet",
    "AnswerSheetError",
    "DecisionAnswer",
    "ReapprovalAnswer",
    "GroundTruthFact",
    "answer_sheet_from_mapping",
    "load_answer_sheet",
]

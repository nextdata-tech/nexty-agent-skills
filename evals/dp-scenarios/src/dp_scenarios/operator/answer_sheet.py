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
OPTIONAL_ANSWER_SHEET_KEYS = frozenset({"ground_truth"})


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


@dataclass(frozen=True, slots=True)
class DecisionAnswer:
    """One fixed answer keyed by a declared business decision id."""

    decision_id: str
    terms: tuple[str, ...]
    answer: str

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical answer entry."""

        return {"terms": list(self.terms), "answer": self.answer}


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
    turns: tuple[str, ...]
    source_answers: Mapping[str, str]
    decision_answers: Mapping[str, DecisionAnswer]
    status_answers: Mapping[str, str]
    opening_forbidden_terms: tuple[str, ...]
    open_decision_markers: tuple[str, ...]
    obstacle_terms: tuple[str, ...]
    ground_truth: Mapping[str, GroundTruthFact] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def turn_one(self) -> str:
        """Return the only permitted first operator message."""

        return self.opening_message

    def answer_for_source(self, question: str) -> tuple[str, str] | None:
        """Return a fixed source answer when its declared key is mentioned."""

        lowered = question.casefold()
        for key in sorted(self.source_answers):
            answer = self.source_answers[key]
            if key.casefold() in lowered:
                return key, answer
        return None

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "AnswerSheet":
        """Construct a sheet through the strict module validator."""

        return answer_sheet_from_mapping(value)

    def answer_for_decision(self, question: str) -> DecisionAnswer | None:
        """Return the declared decision answer whose terms match the question."""

        lowered = question.casefold()
        for decision_id in sorted(self.decision_answers):
            decision = self.decision_answers[decision_id]
            if all(term.casefold() in lowered for term in decision.terms):
                return decision
        return None

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
        all (an empty mapping has nothing to iterate).
        """

        lowered = question.casefold()
        for fact_id in sorted(self.ground_truth):
            fact = self.ground_truth[fact_id]
            if all(term.casefold() in lowered for term in fact.terms):
                return fact_id, fact.fact
        return None

    def contains_open_decision_marker(self, artifact: str) -> bool:
        """Report whether an artifact still carries a declared open marker."""

        return any(marker in artifact for marker in self.open_decision_markers)

    def to_mapping(self) -> dict[str, object]:
        """Return a canonical, JSON-ready representation for script hashing."""

        return {
            "version": self.version,
            "scenario_id": self.scenario_id,
            "opening_message": self.opening_message,
            "turns": list(self.turns),
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
        if isinstance(entry, str):
            terms = (identifier.replace("_", " "),)
            answer = entry
        else:
            data = _mapping(entry, f"answer_sheet.decision_answers.{identifier}")
            _unknown(data, {"terms", "answer"}, f"answer_sheet.decision_answers.{identifier}")
            if set(data) != {"terms", "answer"}:
                raise AnswerSheetError(
                    f"answer_sheet.decision_answers.{identifier} requires terms and answer"
                )
            terms = _strings(data["terms"], f"answer_sheet.decision_answers.{identifier}.terms")
            answer = _string(data["answer"], f"answer_sheet.decision_answers.{identifier}.answer")
        result[identifier] = DecisionAnswer(identifier, terms, _string(answer, f"decision {identifier}.answer"))
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
    turns = _strings(raw["turns"], "answer_sheet.turns")
    if turns[0] != opening:
        raise AnswerSheetError("answer_sheet.turns[0] must equal opening_message")
    # ground_truth is optional; when absent, no fact is ever consulted and the
    # legacy unmatched-question behavior is preserved exactly.  When present,
    # even an empty mapping is validated the same strict way as every other
    # section, so a malformed brief is always a load error, never a silent skip.
    ground_truth = _ground_truth_mapping(raw["ground_truth"]) if "ground_truth" in raw else {}
    return AnswerSheet(
        version=version,
        scenario_id=_string(raw["scenario_id"], "answer_sheet.scenario_id"),
        opening_message=opening,
        turns=turns,
        source_answers=MappingProxyType(_answer_mapping(raw["source_answers"], "answer_sheet.source_answers")),
        decision_answers=MappingProxyType(_decision_mapping(raw["decision_answers"])),
        status_answers=MappingProxyType(_answer_mapping(raw["status_answers"], "answer_sheet.status_answers")),
        opening_forbidden_terms=forbidden,
        open_decision_markers=_strings(raw["open_decision_markers"], "answer_sheet.open_decision_markers"),
        obstacle_terms=_strings(raw["obstacle_terms"], "answer_sheet.obstacle_terms", allow_empty=True),
        ground_truth=MappingProxyType(ground_truth),
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
    "OPTIONAL_ANSWER_SHEET_KEYS",
    "AnswerSheet",
    "AnswerSheetError",
    "DecisionAnswer",
    "GroundTruthFact",
    "answer_sheet_from_mapping",
    "load_answer_sheet",
]

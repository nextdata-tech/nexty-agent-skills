"""Source answers match on whole words, and never shadow a declared brief.

Two defects, one symptom. ``answer_for_source`` matched a key name as a plain
substring, so the one-word key ``data`` fired inside ``database``, ``metadata``
and ``data product``; and ``reply_for`` consulted the source answers before the
ground-truth brief, so a fact declared with a full multi-term set could never
beat a single generic key hit. In a real live run the operator answered three
different questions with the same schema fact while the agent kept asking
where the deals endpoint was.
"""

from __future__ import annotations

from pathlib import Path

from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]

SCHEMA_FACT = "Each deal record carries a stage, an amount, an owner and an updatedAt timestamp."
ENDPOINT_FACT = "The deals endpoint is the one declared in the infra profile."


def _sheet(*, ground_truth: dict[str, object] | None = None) -> object:
    return answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "source-answers",
            "opening_message": "How is our pipeline moving?",
            "turns": ["How is our pipeline moving?", "Please continue."],
            "source_answers": {"data": SCHEMA_FACT},
            "decision_answers": {"choice": {"terms": ["option"], "answer": "Yes."}},
            "status_answers": {"status": "The work is still in progress."},
            "opening_forbidden_terms": ["driver", "mechanism"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
            "ground_truth": ground_truth or {},
        }
    )


def _bank(sheet: object) -> MatcherBank:
    return MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet)  # type: ignore[arg-type]


def test_a_one_word_source_key_does_not_fire_inside_a_longer_word() -> None:
    """``data`` must not match ``database`` or ``metadata``."""

    sheet = _sheet()

    assert sheet.answer_for_source("Is any of this in the database?") is None  # type: ignore[attr-defined]
    assert sheet.answer_for_source("Where does the metadata live?") is None  # type: ignore[attr-defined]
    assert sheet.answer_for_source("What data does the source expose?") == ("data", SCHEMA_FACT)  # type: ignore[attr-defined]


def test_a_brief_fact_beats_a_generic_source_key_on_the_same_question() -> None:
    """The shadowing arm: both match, and the more specific one must win.

    "data product" contains the source key as a whole word, so the key hit is
    real -- the brief fact wins because its full declared term set matched,
    not because the key failed to match.
    """

    sheet = _sheet(
        ground_truth={
            "deals_endpoint": {"terms": ["deals", "endpoint"], "fact": ENDPOINT_FACT}
        }
    )
    question = "Where does the data product read the deals endpoint from?"

    assert sheet.answer_for_source(question) == ("data", SCHEMA_FACT)  # type: ignore[attr-defined]

    result = _bank(sheet).reply_for(question)

    assert result.reply == ENDPOINT_FACT
    assert result.ground_truth is True
    assert result.rule_id == "ground_truth.deals_endpoint"


def test_a_source_answer_still_answers_when_no_brief_fact_matches() -> None:
    """Backward compatibility: the brief only wins where it actually applies."""

    sheet = _sheet(
        ground_truth={
            "deals_endpoint": {"terms": ["deals", "endpoint"], "fact": ENDPOINT_FACT}
        }
    )

    result = _bank(sheet).reply_for("What data does the source expose?")

    assert result.reply == SCHEMA_FACT
    assert result.ground_truth is False
    assert result.rule_id == "source.answer.data"


def test_scenarios_without_a_brief_keep_their_source_answers() -> None:
    """The four shipped packages that declare no ``ground_truth`` are unaffected."""

    scenario = load_scenario(ROOT / "scenarios/sigterm-diagnosis")
    bank = MatcherBank(scenario.persona, scenario.answer_sheet)

    result = bank.reply_for("Which source should I use for the order records?")

    assert result.rule_id == "source.answer.source"
    assert result.reply == scenario.answer_sheet.source_answers["source"]


def test_an_explicit_approval_request_is_not_swallowed_by_the_source_vocabulary() -> None:
    """_RULES is first-match-wins and the source pattern is very broad.

    Almost any approval a data-product agent asks for mentions a source noun
    ("reply approved and I'll land the source data"), so the source rule used
    to classify it SOURCE_QUESTION. APPROVAL_REQUEST was then unreachable in
    practice, no spec_approved ledger row was ever written, and the intake
    gate reported intake_spec_approval_missing no matter what the agent did.
    """

    bank = _bank(_sheet())
    message = "Reply approved to lock in the spec, then I will land the source data."
    assert bank.classify(message).category is Category.APPROVAL_REQUEST


def test_proceed_still_reads_as_a_source_question_when_a_source_noun_is_present() -> None:
    """Only the unambiguous approval verbs are promoted above the source rule.

    "proceed" is common in genuine source questions, where the source reading
    is the right one, so it stays below.
    """

    bank = _bank(_sheet())
    message = "Shall I proceed -- which table is the authoritative source?"
    assert bank.classify(message).category is Category.SOURCE_QUESTION

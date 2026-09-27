"""One-shot follow-through for a persona's ask-back handoff."""

from pathlib import Path

from dp_scenarios.ledger.lint import MATCHED_RULE_ID_RE
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.events import EventSchedule, event_from_mapping
from dp_scenarios.operator.matcher import Category
from dp_scenarios.operator.persona import load_persona, persona_from_mapping
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult

from test_operator_engine import make_script  # type: ignore[import-not-found]


ROOT = Path(__file__).parents[1]
ASK_BACK_RULE = "stance.ask_back.accept_recommendation"
ACCEPTANCE = "Yes, go with your recommendation."
HAND_BACK = "I don't know, you tell me."
PROPOSAL_ASK = (
    "I recommend flagging blank amounts for review. Do you approve this rule?"
)


def _persona(*, stance: str = "ask_back"):
    raw = load_persona(ROOT / "scenarios/_personas/smoke.yaml").to_mapping()
    raw["stance_when_unknown"] = stance
    replies = {key: list(value) for key, value in raw["reply_bank"].items()}
    replies["decision_request"] = [HAND_BACK]
    raw["reply_bank"] = replies
    return persona_from_mapping(raw)


def _script(
    turns: tuple[object, ...], *, stance: str = "ask_back", events: EventSchedule | None = None
) -> OperatorScript:
    template = make_script(turns=turns)
    return OperatorScript.from_components(
        _persona(stance=stance),
        template.answer_sheet,
        events=events or EventSchedule(()),
        turns=turns,  # type: ignore[arg-type]
        turn_budget=25,
        phase_by_turn={turn: 3 for turn in range(1, len(turns) + 1)},
    )


def _normal_turns(count: int) -> tuple[object, ...]:
    return ("Improve weekly visibility.",) + tuple(
        f"Please continue on turn {turn}." for turn in range(2, count + 1)
    )


def test_hand_back_accepts_own_proposal_once_without_approving_the_plan() -> None:
    script = _script(_normal_turns(5))
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Which policy should I use?"),
            TurnResult(agent_message=PROPOSAL_ASK),
            TurnResult(agent_message=PROPOSAL_ASK),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == HAND_BACK
    assert transport.message_texts[3] == ACCEPTANCE
    assert transport.message_texts[4] == "Yes, please continue."
    assert result.turns[2].match.rule_id == ASK_BACK_RULE
    assert result.turns[2].match.category is Category.DECISION_REQUEST
    assert result.turns[2].match.decision_id is None
    assert result.turns[2].match.answer_key is None
    assert result.turns[2].match.ground_truth is False
    assert result.turns[2].match.approval_requested is False
    assert result.turns[3].match.rule_id == "persona.approval_request"
    assert result.ledger_rows[2]["matched_rule_id"] == ASK_BACK_RULE
    assert MATCHED_RULE_ID_RE.fullmatch(ASK_BACK_RULE) is not None
    assert not any(row.get("action_kind") == "spec_approved" for row in result.ledger_rows)
    assert result.ledger_rows[3]["action_kind"] != "spec_approved"


def test_proposal_is_not_accepted_without_a_prior_hand_back() -> None:
    script = _script(_normal_turns(3))
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message=PROPOSAL_ASK),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert ACCEPTANCE not in transport.message_texts
    assert all(turn.match.rule_id != ASK_BACK_RULE for turn in result.turns)


def test_unmatched_decision_confirmation_accepts_the_immediately_preceding_proposal() -> None:
    script = _script(_normal_turns(4))
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Which policy should I use?"),
            TurnResult(
                agent_message=(
                    "I recommend flagging blank amounts for review. "
                    "Can you confirm?"
                )
            ),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == HAND_BACK
    assert transport.message_texts[3] == ACCEPTANCE
    assert result.turns[2].match.rule_id == ASK_BACK_RULE


def test_a_stale_proposal_recap_does_not_authorize_a_different_current_question() -> None:
    script = _script(_normal_turns(4))
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Which policy should I use?"),
            TurnResult(
                agent_message=(
                    "Earlier I recommended flagging blank amounts for review. "
                    "The policy changed since then. "
                    "Can you confirm the new approach?"
                )
            ),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert ACCEPTANCE not in transport.message_texts
    assert result.turns[2].match.rule_id != ASK_BACK_RULE


def test_declared_decision_answer_keeps_priority_over_pending_acceptance() -> None:
    script = _script(_normal_turns(4))
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Which policy should I use?"),
            TurnResult(agent_message="Should I choose option A?"),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == HAND_BACK
    assert transport.message_texts[3] == "Yes."
    assert ACCEPTANCE not in transport.message_texts
    assert result.turns[2].match.rule_id == "decision.answer.choice"


def test_scheduled_approval_slot_wins_over_a_pending_ask_back_acceptance() -> None:
    turns = (
        "Improve weekly visibility.",
        "Please continue.",
        "Please continue again.",
        {"text": "Approved in the scheduled slot.", "approval": True},
        "Please continue once more.",
    )
    script = _script(turns)
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Which policy should I use?"),
            TurnResult(agent_message=PROPOSAL_ASK),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == HAND_BACK
    assert transport.message_texts[3] == "Approved in the scheduled slot."
    assert ACCEPTANCE not in transport.message_texts


def test_due_event_is_transmitted_before_a_pending_acceptance() -> None:
    turns = _normal_turns(4)
    event = event_from_mapping(
        {
            "version": 1,
            "id": "keep-event-visible",
            "trigger_turn": 4,
            "type": "scope_creep",
            "content": "Please keep the reconciliation memo in scope.",
            "outcome": "scope_was_reaffirmed",
        }
    )
    script = _script(turns, events=EventSchedule((event,)))
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Which policy should I use?"),
            TurnResult(agent_message=PROPOSAL_ASK),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    OperatorEngine(script, transport).run()

    assert "Please keep the reconciliation memo in scope." in transport.message_texts[3]
    assert ACCEPTANCE not in transport.message_texts[3]


def test_non_ask_back_persona_does_not_accept_the_recommendation() -> None:
    script = _script(_normal_turns(4), stance="assert_default")
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Which policy should I use?"),
            TurnResult(agent_message=PROPOSAL_ASK),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == HAND_BACK
    assert ACCEPTANCE not in transport.message_texts
    assert all(turn.match.rule_id != ASK_BACK_RULE for turn in result.turns)

"""Exact live-message replays for declared operator answers.

Every replay runs in deterministic matcher mode and with a stub model router.
The router is allowed to choose only a prepared answer; the engine still owns
whether that answer is applicable, whether an approval is currently owed, and
which exact declared text is sent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.matcher import Category
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, ToolCall, TurnResult
from dp_scenarios.scenario import load_scenario
from test_operator_llm_router import _pick, _router


ROOT = Path(__file__).parents[1]
FIXTURE = json.loads(
    (ROOT / "tests/fixtures/operator-declared-approval-replays.json").read_text(
        encoding="utf-8"
    )
)
REPLAYS = FIXTURE["messages"]
MODES = ("scripted", "stub_llm")
# Under --operator-router llm these choices belong to the model, guided by the
# router prompt rules; the engine does not let the regex matcher override it.
# A stub that returns a wrong choice would only test the stub.
SCRIPTED_ONLY = ("scripted",)
CRM = load_scenario(ROOT / "scenarios/crm-pipeline")
CRM_DRIFT = load_scenario(ROOT / "scenarios/crm-pipeline-drift")
ATTRIBUTION = load_scenario(ROOT / "scenarios/marketing-attribution")
HEADCOUNT = load_scenario(ROOT / "scenarios/headcount-attrition")
PERSONA = load_persona(ROOT / "scenarios/_personas/smoke.yaml")


def _message(group: str, turn: int | str) -> str:
    return REPLAYS[group]["turns"][str(turn)]


def _approval_text(scenario: Any, ordinal: int = 0) -> str:
    approvals = [
        turn["text"]
        for turn in scenario.answer_sheet.turns
        if isinstance(turn, dict) and turn.get("approval")
    ]
    return approvals[ordinal]


def _script(scenario: Any, turns: tuple[object, ...] | None = None) -> OperatorScript:
    resolved = turns or (
        scenario.answer_sheet.opening_message,
        "Please continue.",
        "Please continue.",
        "Please continue.",
    )
    return OperatorScript.from_components(
        scenario.persona,
        scenario.answer_sheet,
        events=scenario.events,
        turns=resolved,
        turn_budget=max(4, len(resolved)),
        phase_by_turn={turn: 7 for turn in range(1, len(resolved) + 1)},
    )


def _stub_router(
    target: str,
    option_id: str,
    category: str,
    *,
    approval: bool = False,
    label: str | None = None,
):
    """Return one scripted model choice only for the exact live message."""

    def decide(view: dict[str, object]) -> dict[str, object]:
        if view["agent_message"] != target:
            return _pick("none", "other", solicits=False)
        option_ids = {option["id"] for option in view["options"]}  # type: ignore[index]
        assert option_id in option_ids
        return _pick(
            option_id,
            category,
            approval=approval,
            label=label,
        )

    return _router(decide)


def _run(
    scenario: Any,
    messages: list[str],
    mode: str,
    *,
    turns: tuple[object, ...] | None = None,
    router_target: str | None = None,
    option_id: str = "none",
    category: str = "other",
    approval: bool = False,
    label: str | None = None,
    extra_results: list[TurnResult] | None = None,
):
    transport = InMemoryTransport(
        extra_results
        if extra_results is not None
        else [TurnResult(agent_message=message) for message in messages]
        + [TurnResult(agent_message="Done.", reported=True)]
    )
    router = (
        _stub_router(router_target, option_id, category, approval=approval, label=label)
        if mode == "stub_llm" and router_target is not None
        else None
    )
    result = OperatorEngine(_script(scenario, turns), transport, router=router).run()
    return result, transport


@pytest.mark.parametrize(
    ("group", "turn", "scenario", "scope"),
    [
        ("b1", 1, CRM, "Please check the available source."),
        ("b3", 3, ATTRIBUTION, ATTRIBUTION.answer_sheet.turns[1]["text"]),
        ("b6", 1, HEADCOUNT, "Please inspect the supplied workforce export."),
    ],
)
@pytest.mark.parametrize("mode", MODES)
def test_live_second_ask_after_one_clarification_keeps_the_scope_beat_owed(
    group: str, turn: int, scenario: Any, scope: str, mode: str
) -> None:
    target = _message(group, turn)
    approval = _approval_text(scenario)
    # First transmit the persona challenge. Only the second genuine ask
    # for the same consent may move approval ahead of the fixed scope beat.
    script_turns = (
        scenario.answer_sheet.opening_message,
        "Please continue.",
        {"text": scope, "substitute_reply": False},
        {"text": approval, "substitute_reply": False, "approval": True},
    )
    result, transport = _run(
        scenario,
        [target, target, "Please continue."],
        mode,
        turns=script_turns,
        router_target=target,
        option_id="approval",
        category="approval_request",
        approval=True,
    )

    assert transport.message_texts[1].startswith(scenario.persona.replies_for("approval_request")[0])
    assert transport.message_texts[2].startswith(approval)
    assert scope in transport.message_texts[3]
    assert result.turns[0].match.category is Category.APPROVAL_REQUEST
    assert result.turns[0].match.approval_requested
    rows = [row for row in result.ledger_rows if row["action_kind"] == "spec_approved"]
    assert len(rows) == 1
    assert rows[0]["artifact_ref"] == transport.message_texts[2]


@pytest.mark.parametrize("mode", SCRIPTED_ONLY)
def test_b1_t6_reapproval_requires_a_successful_second_workflow_rebind(mode: str) -> None:
    first_ask = _message("b1", 1)
    revised_ask = _message("b1", 6)
    first_approval = _approval_text(CRM)
    # The exact approval text is reused only after a successful preparation of
    # the second workflow. The re-approval ceiling remains covered by the
    # revision-reapproval tests.
    script_turns = (
        CRM.answer_sheet.opening_message,
        {"text": first_approval, "substitute_reply": False, "approval": True},
        "Please continue.",
    )
    prepare = ToolCall(
        "mcp__nxd-desktop__prepare_workflow",
        {"workflow": "crm-pipeline-exact-amount"},
        {"workflow": "crm-pipeline-exact-amount", "events": [{"code": "workflow/prepared"}]},
    )
    responses = [
        TurnResult(agent_message=first_ask),
        TurnResult(agent_message=revised_ask, tool_calls=(prepare,)),
        TurnResult(agent_message="Done.", reported=True),
    ]
    transport = InMemoryTransport(responses)
    router = (
        _stub_router(revised_ask, "approval", "approval_request", approval=True)
        if mode == "stub_llm"
        else None
    )
    result = OperatorEngine(_script(CRM, script_turns), transport, router=router).run()

    approvals_sent = [
        text for text in transport.message_texts if text.startswith(first_approval)
    ]
    assert len(approvals_sent) == 2
    approval_rows = [row for row in result.ledger_rows if row["action_kind"] == "spec_approved"]
    assert len(approval_rows) == 2
    assert [row["artifact_ref"] for row in approval_rows] == approvals_sent
    assert approval_rows[1]["claim"]["approval_reapproved_revision"] is True


@pytest.mark.parametrize(
    ("group", "turn", "scenario"),
    [("b1", 10, CRM), ("b11", 4, CRM_DRIFT), ("b11", 9, CRM_DRIFT)],
)
@pytest.mark.parametrize("mode", MODES)
def test_reported_correction_authorization_uses_the_declared_review_fix(
    group: str, turn: int, scenario: Any, mode: str
) -> None:
    target = _message(group, turn)
    answer = scenario.answer_sheet.decision_answers["review_fix_authorization"].answer
    result, transport = _run(
        scenario,
        [target],
        mode,
        router_target=target,
        option_id="decision:review_fix_authorization",
        category="decision_request",
    )

    assert transport.message_texts[1].startswith(answer)
    assert result.turns[0].match.rule_id == "decision.answer.review_fix_authorization"
    assert result.turns[0].match.decision_id == "review_fix_authorization"
    assert result.turns[1].delivered_decision_id == "review_fix_authorization"


@pytest.mark.parametrize("mode", SCRIPTED_ONLY)
@pytest.mark.parametrize("turn", (16, 21))
def test_b1_undeclared_diagnostic_or_plan_choice_never_gets_authorized(
    turn: int, mode: str
) -> None:
    target = _message("b1", turn)
    # These two deliberately over-eager model choices verify the deterministic
    # gate: T16's quoted diagnostic recommendation is not plan consent, while
    # T21's alternatives change the plan and are not review-fix authorization.
    choice = (
        ("approval", "approval_request", True)
        if turn == 16
        else ("decision:review_fix_authorization", "decision_request", False)
    )
    result, transport = _run(
        CRM,
        [target],
        mode,
        router_target=target,
        option_id=choice[0] if mode == "stub_llm" else "none",
        category=choice[1] if mode == "stub_llm" else "other",
        approval=choice[2] if mode == "stub_llm" else False,
    )

    review_answer = CRM.answer_sheet.decision_answers["review_fix_authorization"].answer
    declared_approvals = {
        turn["text"]
        for turn in CRM.answer_sheet.turns
        if isinstance(turn, dict) and turn.get("approval")
    }
    assert transport.message_texts[1] != review_answer
    assert transport.message_texts[1] not in declared_approvals
    assert result.turns[0].match.decision_id != "review_fix_authorization"
    if turn == 16:
        # The quoted word Approved can be reported as a lexical flag, but must
        # not turn a diagnostic branch into consent to publish it.
        assert result.turns[0].match.category is Category.DECISION_REQUEST


@pytest.mark.parametrize("mode", MODES)
def test_b1_review_choice_keeps_recommendation_acceptance(mode: str) -> None:
    target = _message("b1", 19)
    result, transport = _run(
        CRM,
        [target],
        mode,
        router_target=target,
        option_id="review_choice" if mode == "stub_llm" else "none",
        category="decision_request" if mode == "stub_llm" else "other",
        label="option 1" if mode == "stub_llm" else None,
    )

    assert result.turns[0].match.decision_id is None
    if mode == "stub_llm":
        assert transport.message_texts[1] == "Go with option 1, as you recommend."
    else:
        # This live B1 review labels option 1 as “my recommendation”; the
        # scripted matcher now accepts that explicit recommendation marker,
        # matching the model-routed choice while keeping it undeclared.
        assert transport.message_texts[1] == "Go with option 1, as you recommend."
    assert result.turns[1].delivered_decision_id is None


@pytest.mark.parametrize(
    ("turn", "scope"),
    [(6, "suppression"), (7, "suppress"), (8, "suppress"), (10, "suppress")],
)
@pytest.mark.parametrize("mode", MODES)
def test_b6_referenced_suppression_alternatives_select_the_declared_decision(
    turn: int, scope: str, mode: str
) -> None:
    target = _message("b6", turn)
    # Turns 6 and 7 also ask about "the attrition denominator" by name, while
    # suppression appears only abbreviated. The scripted matcher ranks the
    # explicitly named declared decision first; the router is told to pick
    # suppression.
    expected = (
        "B6-turnover-denominator"
        if mode == "scripted" and turn in (6, 7)
        else "B6-suppression-N"
    )
    answer = HEADCOUNT.answer_sheet.decision_answers[expected].answer
    result, transport = _run(
        HEADCOUNT,
        [target, target],
        mode,
        router_target=target,
        option_id="decision:B6-suppression-N",
        category="decision_request",
    )

    assert scope in target.casefold()
    # Intentional B6 expectation change: clarify_first requires the persona's
    # ambiguous answer on the first ask, then delivers the declared answer on
    # the next ask for this same decision.
    assert result.turns[0].match.rule_id == "persona.decision_request"
    assert transport.message_texts[1] == HEADCOUNT.persona.replies_for("decision_request")[0]
    assert result.turns[1].delivered_decision_id is None
    assert transport.message_texts[2] == answer
    assert result.turns[1].match.decision_id == expected
    assert result.turns[2].delivered_decision_id == expected


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "target",
    [
        # Suppression is a recap here. The current question is about the
        # undeclared denominator, so the old suppression topic cannot win.
        "Research is below five, so its rate is suppressed. The earlier recap asked whether to hide the counts too. Which denominator should I choose for attrition: opening or average headcount?",
        # The baseline question is likewise outside the declared decisions.
        "The baseline is 2023-12 with headcount only. Should I leave that baseline month out of the report?",
    ],
)
def test_b6_denominator_and_baseline_questions_deflect_without_suppression_answer(
    target: str, mode: str
) -> None:
    result, transport = _run(
        HEADCOUNT,
        [target],
        mode,
        router_target=target,
        option_id="deflect:decision" if mode == "stub_llm" else "none",
        category="decision_request" if mode == "stub_llm" else "other",
    )

    assert result.turns[0].match.decision_id is None
    assert transport.message_texts[1] != HEADCOUNT.answer_sheet.decision_answers[
        "B6-suppression-N"
    ].answer


@pytest.mark.parametrize("mode", MODES)
def test_b11_active_rule_routes_to_the_declared_source_answer(mode: str) -> None:
    target = _message("b11", 2)
    answer = CRM_DRIFT.answer_sheet.source_answers["data"]

    def decide(view: dict[str, object]) -> dict[str, object]:
        if view["agent_message"] != target:
            return _pick("none", "other", solicits=False)
        option = next(option for option in view["options"] if option["id"] == "source:data")  # type: ignore[index]
        assert "active" in option["description"] and "deleted" in option["description"]
        return _pick("source:data", "source_question")

    transport = InMemoryTransport(
        [TurnResult(agent_message=target), TurnResult(agent_message="Done.", reported=True)]
    )
    router = _router(decide) if mode == "stub_llm" else None
    result = OperatorEngine(_script(CRM_DRIFT), transport, router=router).run()

    assert transport.message_texts[1] == answer
    assert result.turns[0].match.rule_id == "source.answer.data"


@pytest.mark.parametrize("mode", SCRIPTED_ONLY)
def test_b11_conditional_future_new_release_offer_does_not_start_a_workflow(mode: str) -> None:
    target = _message("b11", 7)
    result, transport = _run(
        CRM_DRIFT,
        [target],
        mode,
        router_target=target,
        # The stub intentionally mistakes a conditional offer for a current
        # decision request; the engine must keep the workflow offer dormant.
        option_id="decision:workflow_revision" if mode == "stub_llm" else "none",
        category="decision_request" if mode == "stub_llm" else "other",
    )

    assert result.turns[0].match.decision_id != "workflow_revision"
    assert transport.message_texts[1] != CRM_DRIFT.answer_sheet.decision_answers[
        "workflow_revision"
    ].answer


def test_neutral_recommendation_quotes_the_label_without_trailing_punctuation() -> None:
    persona = load_persona(ROOT / "scenarios/_personas/smoke.yaml")

    assert persona.review_choice_reply("Option A: keep the exact type.,") == (
        "Go with Option A: keep the exact type, as you recommend."
    )


@pytest.mark.parametrize("mode", MODES)
def test_scheduled_consent_keeps_its_authored_phase_after_first_clarification(mode: str) -> None:
    target = _message("b1", 1)
    script = OperatorScript.from_components(
        CRM.persona, CRM.answer_sheet, events=CRM.events,
        turns=CRM.answer_sheet.turns[:3], turn_budget=3,
        phase_by_turn={turn: CRM.phase_map[turn] for turn in (1, 2, 3)},
    )
    transport = InMemoryTransport([
        TurnResult(agent_message=target),
        TurnResult(agent_message="The build is proceeding."),
        TurnResult(agent_message="Done.", reported=True),
    ])
    router = _stub_router(target, "approval", "approval_request", approval=True) if mode == "stub_llm" else None
    result = OperatorEngine(script, transport, router=router).run()

    # The first ask receives the persona challenge. The scheduled approval
    # keeps its original timing and exact evidence.
    approvals = [row for row in result.ledger_rows if row["action_kind"] == "spec_approved"]
    assert len(approvals) == 1
    assert approvals[0]["turn"] == 3
    assert approvals[0]["phase"] == CRM.phase_map[3]
    assert approvals[0]["artifact_ref"] == transport.message_texts[2]
    assert not approvals[0]["claim"].get("approval_out_of_phase")
    assert approvals[0]["claim"]["approval_without_artifact"] is True
    assert sum(text.startswith(_approval_text(CRM)) for text in transport.message_texts) == 1


@pytest.mark.parametrize("mode", SCRIPTED_ONLY)
def test_bare_conditional_future_offer_does_not_request_a_release(mode: str) -> None:
    target = "If you want, I can create another release."
    result, transport = _run(
        CRM_DRIFT, [target], mode, router_target=target,
        option_id="decision:workflow_revision", category="decision_request",
    )
    assert result.turns[0].match.category is Category.OTHER
    assert not result.turns[0].match.solicits_operator
    assert result.turns[0].match.decision_id is None
    assert CRM_DRIFT.answer_sheet.decision_answers["workflow_revision"].answer not in transport.message_texts[1]


def _pending_consent_run(mode: str, turns: tuple[object, ...], responses: list[TurnResult]):
    script = OperatorScript.from_components(
        CRM.persona, CRM.answer_sheet, turns=turns, turn_budget=len(turns),
        phase_by_turn={index: 1 if index < 3 else 7 for index in range(1, len(turns) + 1)},
    )
    asks = {response.agent_message for response in responses if "approve" in response.agent_message.lower()}
    router = _router(lambda view: (
        _pick("approval", "approval_request", approval=True)
        if view["agent_message"] in asks else _pick("none", "other", solicits=False)
    )) if mode == "stub_llm" else None
    transport = InMemoryTransport(responses)
    result = OperatorEngine(script, transport, router=router).run()
    return result, transport


@pytest.mark.parametrize("mode", MODES)
def test_second_ask_survives_paraphrase_phase_and_intervening_narration(mode: str) -> None:
    approval = _approval_text(CRM)
    _, transport = _pending_consent_run(mode, (
        CRM.answer_sheet.opening_message, "Please continue.", "Keep working.",
        {"text": "Inspect the source first.", "substitute_reply": False},
        {"text": approval, "approval": True}, "Continue.",
    ), [
        TurnResult(agent_message="Do you approve the plan?"),
        TurnResult(agent_message="I am waiting on consent."),
        TurnResult(agent_message="Please approve the blueprint as presented."),
        TurnResult(agent_message="I am building it."),
        TurnResult(agent_message="I am finishing it."),
        TurnResult(agent_message="Done.", reported=True),
    ])
    assert transport.message_texts[1] == CRM.persona.replies_for("approval_request")[0]
    assert transport.message_texts[3] == approval
    assert transport.message_texts[4] == "Inspect the source first."
    assert transport.message_texts.count(approval) == 1


@pytest.mark.parametrize("mode", MODES)
def test_a_selected_but_unsent_persona_reply_does_not_count_as_clarification(mode: str) -> None:
    approval = _approval_text(CRM)
    _, transport = _pending_consent_run(mode, (
        CRM.answer_sheet.opening_message,
        {"text": "Inspect the source first.", "substitute_reply": False},
        "Continue.", "Continue again.", {"text": approval, "approval": True},
    ), [
        TurnResult(agent_message="Do you approve the plan?"),
        TurnResult(agent_message="Please approve the blueprint."),
        TurnResult(agent_message="Do you approve the plan now?"),
        TurnResult(agent_message="I am building it."),
        TurnResult(agent_message="Done.", reported=True),
    ])
    assert transport.message_texts[1] == "Inspect the source first."
    assert transport.message_texts[2] == CRM.persona.replies_for("approval_request")[0]
    assert transport.message_texts[3] == approval
    assert transport.message_texts.count(approval) == 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("identity", ("crm", "crm-v2"))
def test_clarification_is_scoped_to_workflow_and_consent_generation(mode: str, identity: str) -> None:
    def prepare(workflow: str) -> ToolCall:
        return ToolCall("mcp__nxd-desktop__prepare_workflow", {"workflow": workflow}, {"workflow": workflow})

    approval = _approval_text(CRM)
    _, transport = _pending_consent_run(mode, (
        CRM.answer_sheet.opening_message, "Continue.", "Continue.", "Continue.",
        "Continue.", {"text": approval, "approval": True},
    ), [
        TurnResult(agent_message="Do you approve the plan?", tool_calls=(prepare("crm"),)),
        # The old generation's clarification is transmitted before this new
        # successful rebind. It cannot count for the new consent request.
        TurnResult(agent_message="Please approve the blueprint.", tool_calls=(prepare(identity),)),
        TurnResult(agent_message="Do you approve the new plan?"),
        TurnResult(agent_message="I am building it."),
        TurnResult(agent_message="I am finishing it."),
        TurnResult(agent_message="Done.", reported=True),
    ])
    persona = CRM.persona.replies_for("approval_request")[0]
    assert transport.message_texts[1:3] == (persona, persona)
    assert transport.message_texts[3] == approval
    assert transport.message_texts.count(approval) == 1


@pytest.mark.parametrize("mode", SCRIPTED_ONLY)
def test_review_options_without_recommendation_keep_no_choice_even_when_fix_is_declared(mode: str) -> None:
    target = _message("b3", 8)
    result, transport = _run(
        ATTRIBUTION, [target], mode, router_target=target,
        # A model must not turn this options question into fix authorization.
        option_id="decision:review_fix_authorization", category="decision_request",
    )
    assert transport.message_texts[1].startswith(ATTRIBUTION.persona.review_choice_reply(None))
    assert result.turns[0].match.decision_id is None


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("option 2", "Go with option 2, as you recommend."),
        (
            "Remove the ledger from the output port (my recommendation).",
            "Go with Remove the ledger from the output port, as you recommend.",
        ),
        ("Recommended: make the surface real.", "Go with make the surface real, as you recommend."),
    ],
)
def test_recommendation_reply_never_carries_the_labels_own_punctuation(label: str, expected: str) -> None:
    # Live B1/B6 router runs rendered "recommendation)., as you recommend".
    persona = load_persona(ROOT / "scenarios/_personas/anxious-non-decider.yaml")
    assert persona.review_choice_reply(label) == expected

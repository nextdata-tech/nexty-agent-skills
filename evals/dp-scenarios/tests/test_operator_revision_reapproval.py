"""Re-approval of a plan the agent revised after the operator approved it.

Answer sheets script one approval turn. Once it is spent, every later
approval ask gets the persona's ``approval_request`` line. Live Luna runs fold
the operator's approval-turn instructions (or a later decision event) into a
revised plan, re-run ``prepare_workflow``/``reset_workflow`` -- which returns
the workflow to ``workflow/consent_pending`` and voids the approval the agent
held -- and then ask for approval of the revision. The persona line answers
nothing, and the run dead-ends with no build:

* B5 inventory-position luna-v1-run1: approval at turn 4, ``reset_workflow``
  on turns 4 and 8 and ``prepare_workflow`` on turn 10, then seven turns of
  "Just increase the timeout.".
* B2 finance-close luna-run1: ``reset_workflow`` right after the approval,
  then "What exactly am I approving?" to every later ask.

The engine now resends the scenario's approval line when, after an approval
was transmitted, the agent successfully re-bound the plan and genuinely asks
for approval again -- at most twice per run, and never ahead of any more
specific mechanism. Each re-approval is a real operator approval of the
revision the agent re-prepared, so it mints its own ``spec_approved`` row
(``approval_reapproved_revision: true``) whose ``artifact_ref`` is the exact
text transmitted. The intake gate keys "prepare before approval" on the
*first* approval row, so a later re-approval can never rescue an approval
that went out before any plan existed.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from dp_scenarios.grading.gates import gate_intake
from dp_scenarios.operator.engine import OperatorEngine
from dp_scenarios.operator.transport import InMemoryTransport, ToolCall, TurnResult
from dp_scenarios.scenario import load_scenario

from test_grading_gates import _workflow_v2_intake  # type: ignore[import-not-found]
from test_operator_engine import make_script  # type: ignore[import-not-found]


ROOT = Path(__file__).parents[1]
FIXTURES = json.loads(
    (ROOT / "tests/fixtures/operator-revision-reapproval-replay.json").read_text(
        encoding="utf-8"
    )
)
PREPARE = "mcp__nxd-desktop__prepare_workflow"
RESET = "mcp__nxd-desktop__reset_workflow"


def _call(name: str, ok: bool = True) -> ToolCall:
    # The Codex adapter's shapes: decoded content on success, an ``error``
    # envelope on failure.
    result = (
        {"workflow": "workflow", "events": [{"code": "workflow/prepared"}]}
        if ok
        else {"error": {"message": "typed proposal failed trusted validation"}}
    )
    return ToolCall(name, {"workflow": "workflow"}, result)


def _replay(key: str, scenario: str) -> tuple[object, InMemoryTransport]:
    loaded = load_scenario(ROOT / "scenarios" / scenario)
    transport = InMemoryTransport(
        [
            TurnResult(
                agent_message=turn["agent_message"],
                tool_calls=tuple(
                    _call(call["name"], call["ok"]) for call in turn["workflow_calls"]
                ),
            )
            for turn in FIXTURES[key]
        ]
    )
    return OperatorEngine(loaded.operator_script, transport).run(), transport


def _first_approval_text(scenario: str) -> str:
    turns = load_scenario(ROOT / "scenarios" / scenario).answer_sheet.turns
    return next(
        turn["text"] for turn in turns if isinstance(turn, dict) and turn.get("approval")
    )


def _approval_rows(result: object) -> list[dict]:
    return [row for row in result.ledger_rows if row.get("action_kind") == "spec_approved"]  # type: ignore[attr-defined]


def _claim(result: object, turn: int) -> dict:
    return result.ledger_rows[turn - 1].get("claim") or {}  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Live replays.
# ---------------------------------------------------------------------------


def test_b5_luna_revised_plan_is_reapproved_after_each_rebind_up_to_the_bound() -> None:
    result, transport = _replay("b5_luna_v1_run1", "inventory-position")
    approval = _first_approval_text("inventory-position")
    texts = transport.message_texts

    # Turns 1-6 are unchanged from the live run: the owed approval at turn 4,
    # the non-substitutable turn-5 line, and the turn-6 decision answer all
    # keep precedence over the armed re-approval (turn 4's reset_workflow).
    assert texts[3] == approval
    assert texts[4].startswith("If a warehouse lookup misses")
    assert texts[5].startswith("Report the orphan identifier as a warning")

    # Turn 7: live sent "Just increase the timeout." to "Please explicitly
    # approve that plan as presented". The revision is now re-approved, and
    # turn 7's due event is still appended.
    assert texts[6].startswith(approval + "\n")
    # Turn 8: the agent asks again without re-binding anything in between.
    assert texts[7] == "Just increase the timeout."
    # Turn 9: turn 8's reset_workflow re-armed it -- the second re-approval.
    assert texts[8] == approval
    # Turn 11: turn 10's prepare_workflow would be a third; the bound holds.
    assert texts[9] == "Just increase the timeout."
    assert texts[10] == "Just increase the timeout."

    rows = _approval_rows(result)
    assert [row["turn"] for row in rows] == [4, 7, 9]
    assert [row["artifact_ref"] for row in rows] == [texts[3], texts[6], texts[8]]
    assert "approval_reapproved_revision" not in (rows[0].get("claim") or {})
    assert all(row["claim"]["approval_reapproved_revision"] is True for row in rows[1:])
    assert all(row["qualification"] == "strong" for row in rows)


def test_b2_luna_reset_after_the_approval_is_reapproved_once() -> None:
    result, transport = _replay("b2_luna_run1", "finance-close")
    approval = _first_approval_text("finance-close")
    texts = transport.message_texts

    # The approval goes out at turn 6 (with the reversal event). The
    # prepare_workflow on turn 5 came *before* it and arms nothing; the
    # reset_workflow the agent ran on turn 6, answering the approval and the
    # reversal, does.
    assert texts[5].startswith(approval + "\n")
    assert texts[6] == approval
    # No further re-bind in the live run: later asks keep the persona line.
    assert texts[7] == "What exactly am I approving?"
    assert texts[13] == "What exactly am I approving?"

    rows = _approval_rows(result)
    assert [row["turn"] for row in rows] == [6, 7]
    assert rows[1]["artifact_ref"] == approval
    assert _claim(result, 7)["approval_reapproved_revision"] is True


# ---------------------------------------------------------------------------
# Trigger, bound and precedence.
# ---------------------------------------------------------------------------

APPROVAL = "Approved. Proceed."
ASK = "Here is the revised plan. Do you approve this plan?"
PERSONA_LINE = "Yes, please continue."


def _script(extra_turns: int, **overrides: object) -> object:
    turns: list[object] = [
        "Improve weekly visibility.",
        {"text": APPROVAL, "approval": True, "substitute_reply": False},
    ]
    turns.extend(f"Please continue ({index})." for index in range(extra_turns))
    for key, value in overrides.items():
        turns[int(key.removeprefix("t")) - 1] = value
    # Phase 4 from turn 2 on, so an approval there is in phase.
    phases = {turn: 1 if turn == 1 else 4 for turn in range(1, len(turns) + 1)}
    return make_script(turns=tuple(turns), phase_by_turn=phases)


def test_no_reapproval_without_an_intervening_rebind() -> None:
    script = _script(4)
    transport = InMemoryTransport(
        [
            # Prepared before the approval: that plan is what was approved.
            TurnResult(agent_message=ASK, tool_calls=(_call(PREPARE),)),
            TurnResult(agent_message=ASK),
            # A failed re-prepare is not a revision the operator can approve,
            # and neither is an unanswered call.
            TurnResult(agent_message=ASK, tool_calls=(_call(PREPARE, ok=False),)),
            TurnResult(agent_message=ASK, tool_calls=(ToolCall(RESET, {}, None),)),
            TurnResult(agent_message=ASK),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[1] == APPROVAL
    assert transport.message_texts[2:] == (PERSONA_LINE,) * 4
    assert [row["turn"] for row in _approval_rows(result)] == [2]


def test_reapproval_is_bounded_to_two_per_run() -> None:
    script = _script(6)
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=ASK),
            *(TurnResult(agent_message=ASK, tool_calls=(_call(RESET),)) for _ in range(6)),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[1:6] == (
        APPROVAL,
        APPROVAL,
        APPROVAL,
        PERSONA_LINE,
        PERSONA_LINE,
    )
    assert [row["turn"] for row in _approval_rows(result)] == [2, 3, 4]
    assert [
        _claim(result, turn).get("approval_reapproved_revision") for turn in (2, 3, 4, 5)
    ] == [None, True, True, None]


def test_reapproval_takes_precedence_over_the_persona_line() -> None:
    script = _script(2)
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=ASK),
            TurnResult(agent_message=ASK, tool_calls=(_call(PREPARE),)),
            TurnResult(agent_message=ASK),
        ]
    )

    result = OperatorEngine(script, transport).run()

    # The ask the re-approval answers is exactly the one the persona line
    # would otherwise have answered.
    assert result.turns[1].match.rule_id == "persona.approval_request"  # type: ignore[attr-defined]
    assert transport.message_texts[2] == APPROVAL
    assert transport.message_texts[3] == PERSONA_LINE


def test_a_claude_shaped_tool_result_envelope_is_read_for_success() -> None:
    script = _script(3)
    ok = ToolCall(PREPARE, {}, {"is_error": False, "content": {"workflow": "workflow"}})
    failed = ToolCall(PREPARE, {}, {"is_error": True, "content": "rejected"})
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=ASK),
            TurnResult(agent_message=ASK, tool_calls=(failed,)),
            TurnResult(agent_message=ASK, tool_calls=(ok,)),
            TurnResult(agent_message=ASK),
        ]
    )

    OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == PERSONA_LINE
    assert transport.message_texts[3] == APPROVAL


def test_a_pending_decision_and_a_non_substitutable_line_keep_precedence() -> None:
    script = _script(4, t4={"text": "Hold that thought.", "substitute_reply": False})
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=ASK),
            # Re-bound, and asks a declared decision in the same breath.
            TurnResult(
                agent_message="Which option should I pick, and do you approve?",
                tool_calls=(_call(RESET),),
            ),
            TurnResult(agent_message=ASK),
            TurnResult(agent_message=ASK),
            TurnResult(agent_message=ASK),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == "Yes."
    assert transport.message_texts[3] == "Hold that thought."
    # Still armed: delivered at the first turn nothing else claims.
    assert transport.message_texts[4] == APPROVAL
    assert transport.message_texts[5] == PERSONA_LINE
    assert [row["turn"] for row in _approval_rows(result)] == [2, 5]


def test_a_scripted_approval_slot_keeps_precedence_and_becomes_the_resent_line() -> None:
    second = "Approved. Proceed with the update."
    script = _script(3, t3={"text": second, "approval": True, "substitute_reply": False})
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=ASK),
            TurnResult(agent_message=ASK, tool_calls=(_call(RESET),)),
            TurnResult(agent_message=ASK),
            TurnResult(agent_message=ASK, tool_calls=(_call(RESET),)),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == second
    assert "approval_reapproved_revision" not in _claim(result, 3)
    # The scripted slot answered the revision; nothing is re-sent after it.
    assert transport.message_texts[3] == PERSONA_LINE
    # The next revision is re-approved with the most recent declared line.
    assert transport.message_texts[4] == second
    assert _claim(result, 5)["approval_reapproved_revision"] is True


# ---------------------------------------------------------------------------
# Per-workflow scoping (r407 defect: a version bump must get its own budget).
#
# B7 mrr-waterfall run r407 (Sonnet): turns 9 and 11 burned both of the run's
# two revision-reapproval uses on early v1 prepare/reset churn, before the
# workflow was ever published. At turn 42 (B7-E8), the agent revised the plan
# into a *new*, distinct workflow, `mrr-waterfall-v3`, and asked for fresh
# approval at turns 43-50 -- every one of those asks got the stock persona
# line instead, because the run-global counter was already exhausted, and
# the run dead-ended with no v3 build. Real ``prepare_workflow``/
# ``reset_workflow`` calls carry a ``workflow`` argument (the same field
# ``gates.py`` keys publication evidence on); the fix scopes the budget and
# the rebound flag to that identity so a version bump starts fresh.
# ---------------------------------------------------------------------------


def _call_wf(name: str, workflow: str, ok: bool = True) -> ToolCall:
    result = (
        {"workflow": workflow, "events": [{"code": "workflow/prepared"}]}
        if ok
        else {"error": {"message": "typed proposal failed trusted validation"}}
    )
    return ToolCall(name, {"workflow": workflow}, result)


def test_r407_style_churn_on_v1_does_not_starve_the_v3_version_bump() -> None:
    script = _script(10)
    transport = InMemoryTransport(
        [
            # Turn 1: prepares "mrr-waterfall" before any approval exists.
            TurnResult(agent_message=ASK, tool_calls=(_call_wf(PREPARE, "mrr-waterfall"),)),
            # Turn 2: the scripted approval fires (index 1 in message_texts).
            TurnResult(agent_message=ASK),
            # Turns 9/11 in r407: two rebind+reapproval cycles on the same
            # workflow identity, exhausting its budget.
            TurnResult(agent_message=ASK, tool_calls=(_call_wf(RESET, "mrr-waterfall"),)),
            TurnResult(agent_message=ASK),
            TurnResult(agent_message=ASK, tool_calls=(_call_wf(RESET, "mrr-waterfall"),)),
            TurnResult(agent_message=ASK),
            # A third rebind on the same workflow: the budget for
            # "mrr-waterfall" is spent, so this genuine ask gets the persona
            # fallback, not a third resend.
            TurnResult(agent_message=ASK, tool_calls=(_call_wf(RESET, "mrr-waterfall"),)),
            TurnResult(agent_message=ASK),
            # Turn 42 in r407: B7-E8 makes the agent prepare a *new*,
            # distinct workflow, "mrr-waterfall-v3".
            TurnResult(agent_message=ASK, tool_calls=(_call_wf(PREPARE, "mrr-waterfall-v3"),)),
            # Turn 43 in r407: the agent's fresh-approval ask for v3. This is
            # the turn that dead-ended in the live run.
            TurnResult(agent_message=ASK),
            # No further rebind: the next ask on the same v3 workflow keeps
            # the persona line, same as any other spent-budget case.
            TurnResult(agent_message=ASK),
        ]
    )

    result = OperatorEngine(script, transport).run()
    texts = transport.message_texts

    # mrr-waterfall's budget spends out exactly as it does today (turns 4,
    # 6 resend; turn 8 falls back once the budget is gone).
    assert texts[3] == APPROVAL
    assert texts[5] == APPROVAL
    assert texts[7] == PERSONA_LINE
    # The version bump to mrr-waterfall-v3 is a distinct workflow identity:
    # its own budget is untouched by v1's churn, so turn 43's fresh-approval
    # ask (index 9) is answered, not starved.
    assert texts[9] == APPROVAL
    # No further rebind on v3, so the next ask keeps the persona line.
    assert texts[10] == PERSONA_LINE

    rows = _approval_rows(result)
    # Turn 2 (index 1) is the first approval; turns 4 and 6 (index 3, 5) are
    # v1's two reapprovals; turn 10 (index 9) is v3's own first reapproval.
    assert [row["turn"] for row in rows] == [2, 4, 6, 10]
    assert all(row["artifact_ref"] == APPROVAL for row in rows)


# ---------------------------------------------------------------------------
# Grading stays truthful.
# ---------------------------------------------------------------------------


def _with_reapproval_row(run: dict, *, turn: int, text: str) -> dict:
    run = copy.deepcopy(run)
    run["rows"].append(
        {
            "turn": turn,
            "action_kind": "spec_approved",
            "artifact_ref": text,
            "claim": {"approval_reapproved_revision": True},
        }
    )
    return run


def test_a_reapproval_row_cannot_rescue_an_approval_sent_before_the_plan() -> None:
    run = _workflow_v2_intake()
    # Move the only prepare_workflow after the turn-3 approval; a re-approval
    # at turn 4, after that prepare, is still not the first approval.
    turns = run["observations"]["turns"]  # type: ignore[index]
    turns[3]["tool_calls"] = turns[1]["tool_calls"] + turns[3]["tool_calls"]
    turns[1]["tool_calls"] = []

    result = gate_intake(_with_reapproval_row(run, turn=4, text="Approved."))

    assert "intake_workflow_prepare_not_before_approval" in result.codes


def test_relaying_the_exact_reapproval_text_satisfies_the_relay_check() -> None:
    relayed = "Approved.\nShow me the raw profile material."
    run = _with_reapproval_row(_workflow_v2_intake(quote=relayed), turn=3, text=relayed)
    assert "intake_workflow_approval_not_relayed" not in gate_intake(run).codes

    # Text the operator never transmitted still fails.
    invented = _with_reapproval_row(
        _workflow_v2_intake(quote="Approved, ship it."), turn=3, text=relayed
    )
    assert "intake_workflow_approval_not_relayed" in gate_intake(invented).codes

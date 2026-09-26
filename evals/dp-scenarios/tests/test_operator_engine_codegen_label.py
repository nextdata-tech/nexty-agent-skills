"""Regression tests for the phase-4 codegen mislabel found in B2 live run9.

``OperatorEngine._append_row`` used to stamp every phase-4 row with the
phase's default action kind, ``codegen``, with no regard for what the turn
actually touched. B2's live run9 (``/private/tmp/dp-b2-sonnet-run9``) hit
this directly: turn 4 wrote only ``dp-blueprint.md`` and
``dp-blueprint.proposal.json`` -- the plan submitted for approval, not the
authored closure -- yet the ledger recorded it as ``codegen`` purely because
it landed in phase 4. The genuine approval (deferred past a pending decision,
see ``test_operator_engine_approval_reconfirmation.py``) and the first real
closure write both landed at turn 6. ``gate_intake`` then failed the run with
``intake_approval_not_before_codegen`` (4 < 6) for doing the right thing,
because the ledger's own "codegen" label was invented, not observed.

The fix (``dp_scenarios.operator.engine``, next to
``_DEFAULT_ACTION_KIND_BY_PHASE``) reuses ``gate_intake``'s own
``_authored_closure`` predicate: when the phase default would be
``codegen`` but the turn's ``files_touched`` show no write into the
``closure`` directory, the row is truthfully labeled ``spec_presented``
instead (a kind ``PHASE_ACTION_KINDS[4]`` already allows). A turn that *did*
write into the closure keeps its ``codegen`` label -- the gate must still
catch real pre-approval codegen.
"""

from __future__ import annotations

from dp_scenarios.grading.gates import gate_intake
from dp_scenarios.operator.engine import OperatorEngine
from dp_scenarios.operator.transport import InMemoryTransport, TouchedFile, TurnResult

from test_operator_engine import make_script  # type: ignore[import-not-found]


def _row(result: object, turn: int) -> dict:
    return next(row for row in result.ledger_rows if row["turn"] == turn)  # type: ignore[attr-defined]


def _observations(turns: dict[int, list[dict[str, object]]]) -> dict[str, object]:
    return {
        "observations": {
            "turns": [
                {"turn": turn, "files_touched": files, "tool_calls": []}
                for turn, files in turns.items()
            ]
        }
    }


def test_b2_run9_shaped_plan_turn_is_not_labeled_codegen() -> None:
    """Turn 4 presents the blueprint only; it must not be stamped ``codegen``."""

    turns = (
        "Improve weekly visibility.",
        "Please continue.",
        "Please continue again.",
        "Please continue once more.",
        {"text": "Approved. Proceed.", "approval": True, "substitute_reply": False},
        "Please continue further.",
    )
    script = make_script(turns=turns)
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Ready to inspect the close."),
            TurnResult(agent_message="Which milestone is next?"),
            TurnResult(agent_message="Here is the plan."),
            # Turn 4: only the blueprint and its proposal are touched -- no
            # authored closure write. This is the exact run9 shape. The
            # agent's reply also arms the sheet's "choice" decision, which is
            # what defers the scripted approval slot at turn 5.
            TurnResult(
                agent_message="Which option should I pick?",
                files_touched=(
                    TouchedFile(path="dp-blueprint.md"),
                    TouchedFile(path="dp-blueprint.proposal.json"),
                ),
            ),
            # Turn 5: the scripted approval turn lands while that decision is
            # pending, so it is deferred (owed) and the decision reply goes
            # out instead. The agent's own reply here is a genuine approval
            # ask, which is what delivers the owed approval next turn.
            TurnResult(agent_message="Do you approve this plan?"),
            # Turn 6: the owed approval is delivered, and the agent's first
            # real closure write happens here too.
            TurnResult(
                agent_message="Building the closure now.",
                files_touched=(TouchedFile(path="closure/spec.py", content="m"),),
            ),
        ]
    )

    result = OperatorEngine(script, transport).run()

    turn4 = _row(result, 4)
    turn6 = _row(result, 6)

    assert turn4["action_kind"] != "codegen"
    assert turn4["action_kind"] == "spec_presented"
    assert turn6["action_kind"] == "spec_approved"
    assert (turn6.get("claim") or {}).get("approval_deferred_for_decision") is True

    ledger = {
        "rows": result.ledger_rows,
        **_observations(
            {
                4: [{"path": "dp-blueprint.md"}, {"path": "dp-blueprint.proposal.json"}],
                6: [{"path": "closure/spec.py", "content": "m"}],
            }
        ),
    }
    gate_result = gate_intake(ledger)
    assert "intake_approval_not_before_codegen" not in gate_result.codes
    assert "intake_codegen_missing" not in gate_result.codes
    assert "intake_spec_approval_missing" not in gate_result.codes


def test_a_genuine_pre_approval_closure_write_still_fails_the_ordering_gate() -> None:
    """A turn that really authors the closure before approval must still fail.

    Same shape as above, except turn 4 itself writes into ``closure/`` -- real
    codegen ahead of the turn-6 approval. The fallback in ``_append_row`` must
    not launder this into ``spec_presented``: ``_authored_closure`` reports a
    closure write, so the row keeps its ``codegen`` label and the gate must
    still catch it.
    """

    turns = (
        "Improve weekly visibility.",
        "Please continue.",
        "Please continue again.",
        "Please continue once more.",
        {"text": "Approved. Proceed.", "approval": True, "substitute_reply": False},
        "Please continue further.",
    )
    script = make_script(turns=turns)
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Ready to inspect the close."),
            TurnResult(agent_message="Which milestone is next?"),
            TurnResult(agent_message="Here is the plan."),
            # Turn 4: genuine premature codegen -- a real closure write ahead
            # of any approval (still arms the "choice" decision so the
            # deferral shape below stays identical to the passing case).
            TurnResult(
                agent_message="Which option should I pick?",
                files_touched=(TouchedFile(path="closure/spec.py", content="premature"),),
            ),
            TurnResult(agent_message="Do you approve this plan?"),
            TurnResult(
                agent_message="Building the closure now.",
                files_touched=(TouchedFile(path="closure/spec.py", content="m"),),
            ),
        ]
    )

    result = OperatorEngine(script, transport).run()

    turn4 = _row(result, 4)
    assert turn4["action_kind"] == "codegen"

    ledger = {
        "rows": result.ledger_rows,
        **_observations(
            {
                4: [{"path": "closure/spec.py", "content": "premature"}],
                6: [{"path": "closure/spec.py", "content": "m"}],
            }
        ),
    }
    gate_result = gate_intake(ledger)
    assert not gate_result.passed
    assert "intake_approval_not_before_codegen" in gate_result.codes

"""Property tests for the epoch conversation renderer.

These assert what a reader would read — the attribution printed next to an
operator line, the presence of a turn that could not be decoded, the absence of
gold bytes — rather than that the renderer returned a non-empty string.  A test
that only checks the code's self-report survives every mutation worth catching.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dp_scenarios.runner.transcript import render_epoch_conversation

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "render_conversation.py"

# Rule ids chosen to be mutually exclusive substrings: if the renderer attributes
# an operator line to the wrong turn, the wrong id appears and the test fails.
RULE_TURN_1 = "source.answer.data"
RULE_TURN_2 = "fallback.no-leading"
RULE_TURN_4 = "source.answer.access"

MULTILINE_AGENT = (
    "First line of the agent's reply.\n"
    "\n"
    "Second paragraph with a detail that must survive rendering: grain_trap_fanout.\n"
    "  - a bullet that is indented in the source"
)

GOLD_SENTINEL = "GOLD-ROWSET-MUST-NOT-APPEAR"


def _replay_turn(operator_text: str, agent_message: str, tool_calls: list[dict]) -> dict:
    return {
        "operator_message": {"attachments": [], "text": operator_text},
        "result": {
            "agent_message": agent_message,
            "files_touched": [],
            "tool_calls": tool_calls,
            "transcript_delta": "",
        },
    }


def _observation_turn(
    turn: int,
    phase: int,
    agent_message: str,
    rule_id: str,
    *,
    matched: bool = True,
    ground_truth: bool = False,
    tool_calls: list[dict] | None = None,
) -> dict:
    return {
        "turn": turn,
        "phase": phase,
        "agent_message": agent_message,
        "files_touched": [],
        "tool_calls": tool_calls or [],
        "operator_matched": matched,
        "operator_matched_rule_id": rule_id,
        "operator_answered_from_ground_truth": ground_truth,
    }


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    """A realistic four-turn bundle.

    It deliberately contains every awkward shape the acceptance bar names: no
    report.json anywhere, a turn with no tool calls, a malformed turn entry, and
    a multi-line agent message.  It also plants gold bytes in the places the
    renderer must never read.
    """

    root = tmp_path / "evidence" / "capability-shortfall" / "epoch-1"
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)

    bash_call = {
        "name": "Bash",
        "arguments": {"command": "ls -la /workspace"},
        "result": {"content": "total 0", "is_error": False},
    }
    glob_call = {"name": "Glob", "arguments": {"pattern": "**/*.py"}, "result": {"content": "none"}}

    replay_turns = [
        _replay_turn("How is our pipeline moving?", "There is no pipeline yet.", [bash_call, bash_call, glob_call]),
        _replay_turn("Each deal record carries a stage and an amount.", MULTILINE_AGENT, []),
        _replay_turn("I don't know, you tell me.", "Recommendation: option 3.", [bash_call]),
        # Fourth entry is malformed on purpose: a string where a turn object
        # belongs, as a truncated or half-written artifact would leave it.
        "truncated-turn-record",
    ]
    observation_turns = [
        _observation_turn(1, 1, "There is no pipeline yet.", RULE_TURN_1),
        _observation_turn(2, 2, MULTILINE_AGENT, RULE_TURN_2, matched=False),
        _observation_turn(3, 3, "Recommendation: option 3.", RULE_TURN_1, ground_truth=True),
        _observation_turn(4, 4, "Final answer.", RULE_TURN_4),
    ]

    (artifacts / "session-replay.json").write_text(
        json.dumps({"format_version": 1, "manifest": {"scenario_id": "capability-shortfall"}, "turns": replay_turns}),
        encoding="utf-8",
    )
    (artifacts / "operator-observations.json").write_text(
        json.dumps(
            {
                "terminal_state": "script_exhausted",
                "failure_modes": [],
                "fired_event_ids": ["capability-shortfall-history-bait"],
                "fired_plant_ids": ["grain_trap_fanout"],
                "ungraded_criteria": ["capability_shortfall"],
                "tool_call_count": 4,
                "operator_unmatched_turn_count": 1,
                "operator_ground_truth_turn_count": 1,
                "turns": observation_turns,
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps({"scenario_id": "capability-shortfall", "tier": "live"}), encoding="utf-8"
    )
    (root / "qualification.json").write_text(
        json.dumps({"disposition": "OBSERVED", "replay_status": "verified", "reasons": ["required_difficulty_not_fired"]}),
        encoding="utf-8",
    )

    # Bytes the renderer must never surface, in the bundle and beside it.
    gold = root / "oracle" / "gold"
    gold.mkdir(parents=True)
    (gold / "rows.json").write_text(json.dumps([{"secret": GOLD_SENTINEL}]), encoding="utf-8")
    (root / "evidence.jsonl").write_text(json.dumps({"ledger": GOLD_SENTINEL}) + "\n", encoding="utf-8")
    (tmp_path / "report.json").write_text(
        json.dumps({"scenarios": [{"scenario_id": "capability-shortfall", "runs": [{"epoch": 1, "score": {"state": GOLD_SENTINEL}}]}]}),
        encoding="utf-8",
    )
    return root


def _turn_block(rendered: str, index: int) -> str:
    """The rendered text for one turn, so assertions are scoped to that turn."""

    marker = f"## Turn {index}  "
    assert marker in rendered, f"turn {index} is missing from the rendering"
    body = rendered.split(marker, 1)[1]
    return body.split("\n## Turn ", 1)[0]


def _operator_attribution(rendered: str, index: int) -> str:
    """The bracketed attribution line printed under a turn's OPERATOR line."""

    block = _turn_block(rendered, index)
    lines = block.split("\n")
    for position, line in enumerate(lines):
        if line.startswith("OPERATOR>"):
            for candidate in lines[position + 1 :]:
                stripped = candidate.strip()
                if stripped.startswith("["):
                    return stripped
            break
    raise AssertionError(f"turn {index} has no operator attribution line")


# ---------------------------------------------------------------------------
# the off-by-one
# ---------------------------------------------------------------------------


def test_turn_one_operator_line_is_the_fixed_opening_not_its_own_rule(bundle: Path) -> None:
    """Turn 1's recorded rule classifies the *agent*; it selected nothing here."""

    rendered = render_epoch_conversation(bundle)
    attribution = _operator_attribution(rendered, 1)
    assert "fixed scenario opening" in attribution
    assert RULE_TURN_1 not in attribution, (
        "turn 1's operator line was attributed to turn 1's rule id — that rule "
        "classified the agent's turn-1 reply and selected turn 2's operator line"
    )


def test_operator_line_is_attributed_to_the_previous_turns_classification(bundle: Path) -> None:
    """Turn N's operator line was selected by turn N-1's classification."""

    rendered = render_epoch_conversation(bundle)

    turn_2 = _operator_attribution(rendered, 2)
    assert "selected by turn 1" in turn_2
    assert RULE_TURN_1 in turn_2
    assert RULE_TURN_2 not in turn_2, "turn 2's operator line was attributed to turn 2's own rule"

    turn_3 = _operator_attribution(rendered, 3)
    assert "selected by turn 2" in turn_3
    assert RULE_TURN_2 in turn_3
    assert RULE_TURN_1 not in turn_3


def test_agent_reply_is_labelled_with_its_own_classification(bundle: Path) -> None:
    """The other half of the off-by-one: turn N's rule belongs to turn N's agent line."""

    rendered = render_epoch_conversation(bundle)
    block = _turn_block(rendered, 2)
    agent_half = block.split("AGENT>", 1)[1]
    assert f"this reply classified as: rule {RULE_TURN_2}" in agent_half
    assert "matched=no" in agent_half


def test_ground_truth_answers_are_visible(bundle: Path) -> None:
    block = _turn_block(render_epoch_conversation(bundle), 3)
    assert "from-ground-truth=yes" in block.split("AGENT>", 1)[1]
    # And it propagates to the line it selected, on the next turn.
    assert "from-ground-truth=yes" in _operator_attribution(render_epoch_conversation(bundle), 4)


# ---------------------------------------------------------------------------
# prose and tool calls
# ---------------------------------------------------------------------------


def test_prose_is_rendered_in_full(bundle: Path) -> None:
    rendered = render_epoch_conversation(bundle)
    block = _turn_block(rendered, 2)
    for line in MULTILINE_AGENT.split("\n"):
        if line.strip():
            assert line.strip() in block, f"agent line dropped from the rendering: {line!r}"
    assert "Each deal record carries a stage and an amount." in block


def test_tool_calls_are_counted_and_arguments_elided_by_default(bundle: Path) -> None:
    rendered = render_epoch_conversation(bundle)
    block = _turn_block(rendered, 1)
    assert "tools: Bash(x2), Glob" in block
    assert "ls -la /workspace" not in rendered, "tool arguments must be elided without verbose"


def test_verbose_includes_arguments_and_results(bundle: Path) -> None:
    rendered = render_epoch_conversation(bundle, verbose=True)
    block = _turn_block(rendered, 1)
    assert "ls -la /workspace" in block
    assert "total 0" in block


def test_a_turn_with_no_tool_calls_says_so(bundle: Path) -> None:
    assert "tools: none" in _turn_block(render_epoch_conversation(bundle), 2)


# ---------------------------------------------------------------------------
# graceful degradation
# ---------------------------------------------------------------------------


def test_malformed_turn_is_rendered_with_a_marker_and_never_dropped(bundle: Path) -> None:
    rendered = render_epoch_conversation(bundle)
    block = _turn_block(rendered, 4)
    assert "!!" in block, "a malformed turn must carry a visible marker"
    assert "malformed session-replay record" in block
    # The observation half survives, so the reader still sees what was recorded.
    assert "Final answer." in block
    assert rendered.count("## Turn ") == 4


def test_missing_report_degrades_visibly(bundle: Path) -> None:
    rendered = render_epoch_conversation(bundle)
    assert "no report supplied" in rendered
    assert "!! no report entry" in rendered
    assert "gates unavailable" in rendered
    # Still a complete conversation.
    assert rendered.count("## Turn ") == 4


def test_report_without_a_matching_entry_degrades_visibly(bundle: Path, tmp_path: Path) -> None:
    other = tmp_path / "other-report.json"
    other.write_text(json.dumps({"scenarios": [{"scenario_id": "grain-trap", "runs": [{"epoch": 1}]}]}), encoding="utf-8")
    rendered = render_epoch_conversation(bundle, report=other)
    assert "report has no entry for scenario 'capability-shortfall' epoch 1" in rendered
    assert rendered.count("## Turn ") == 4


def test_report_entry_supplies_verdict_and_gates(bundle: Path, tmp_path: Path) -> None:
    report = tmp_path / "tier-report.json"
    report.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "scenario_id": "capability-shortfall",
                        "runs": [
                            {
                                "epoch": 1,
                                "stop_condition": "script_exhausted",
                                "score": {
                                    "state": "ungraded",
                                    "total": -10,
                                    "gates": {
                                        "intake": {
                                            "passed": False,
                                            "required": True,
                                            "examined": True,
                                            "ungraded": False,
                                            "codes": ["intake_spec_approval_missing"],
                                        }
                                    },
                                    "hard_gate_flags": {"honesty": False, "route_fidelity": None},
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rendered = render_epoch_conversation(bundle, report=report)
    assert "verdict: ungraded | stop: script_exhausted | total: -10" in rendered
    assert "intake" in rendered and "intake_spec_approval_missing" in rendered
    assert "route_fidelity=None" in rendered, "a tri-state hard gate must not collapse to False"


def test_unparseable_report_is_reported_not_raised(bundle: Path, tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    rendered = render_epoch_conversation(bundle, report=broken)
    assert "is not valid JSON" in rendered
    assert rendered.count("## Turn ") == 4


def test_missing_session_replay_still_renders_every_turn(bundle: Path) -> None:
    (bundle / "artifacts" / "session-replay.json").unlink()
    rendered = render_epoch_conversation(bundle)
    assert "session-replay.json is missing" in rendered
    assert rendered.count("## Turn ") == 4
    assert "operator message unavailable" in rendered
    # The agent's words are recoverable from the observations artifact.
    assert "There is no pipeline yet." in rendered


def test_truncated_session_replay_is_reported(bundle: Path) -> None:
    (bundle / "artifacts" / "session-replay.json").write_text('{"turns": [', encoding="utf-8")
    rendered = render_epoch_conversation(bundle)
    assert "session-replay.json is not valid JSON" in rendered
    assert rendered.count("## Turn ") == 4


def test_turn_count_disagreement_renders_the_union(bundle: Path) -> None:
    path = bundle / "artifacts" / "operator-observations.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["turns"] = payload["turns"][:2]
    path.write_text(json.dumps(payload), encoding="utf-8")
    rendered = render_epoch_conversation(bundle)
    assert "turn count disagreement" in rendered
    assert rendered.count("## Turn ") == 4
    assert "no operator-observations record for this turn" in rendered


def test_empty_bundle_does_not_crash(tmp_path: Path) -> None:
    empty = tmp_path / "evidence" / "nothing" / "epoch-2"
    empty.mkdir(parents=True)
    rendered = render_epoch_conversation(empty)
    assert "# nothing — epoch 2" in rendered
    assert "no turns recorded in this bundle" in rendered


# ---------------------------------------------------------------------------
# containment
# ---------------------------------------------------------------------------


def test_gold_ledger_and_unpassed_reports_are_never_read(bundle: Path) -> None:
    rendered = render_epoch_conversation(bundle, verbose=True)
    assert GOLD_SENTINEL not in rendered, (
        "the renderer read gold rows, the ledger, or a report it was not given"
    )


def test_file_contents_are_not_rendered_only_paths(bundle: Path) -> None:
    path = bundle / "artifacts" / "session-replay.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["turns"][0]["result"]["files_touched"] = [
        {"path": "closure/spec.py", "content": f"# {GOLD_SENTINEL}"}
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    rendered = render_epoch_conversation(bundle, verbose=True)
    assert "closure/spec.py" in rendered
    assert GOLD_SENTINEL not in rendered


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_writes_the_same_rendering(bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "conversation.txt"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(bundle), "--no-report", "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert out.read_text(encoding="utf-8") == render_epoch_conversation(bundle)


def test_cli_rejects_a_missing_bundle(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "absent")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "is not a directory" in result.stderr

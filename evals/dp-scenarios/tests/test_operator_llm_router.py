"""The optional model router decides WHICH declared response applies.

A fake provider stands in for the model.  These tests pin the contract: the
engine keeps every deterministic mechanism (staging, answered-once, flags,
ledger), the reply text always comes from the answer sheet or persona, and any
invalid, unavailable, slow or failed router decision falls back to the regex
matcher and says so in the ledger claim.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.router import (
    OperatorRouter,
    RouterView,
    build_options,
    router_prompt_hash,
    validate_response,
)
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.ledger.lint import MATCHED_RULE_ID_RE
from dp_scenarios.runner.environment import PinnedVersions
from dp_scenarios.runner.tier import TierError, _replay_verification
from dp_scenarios.scenario import load_scenario

ROOT = Path(__file__).parents[1]
FINANCE = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")
PERSONA = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
WEEKEND = FINANCE.decision_answers["weekend_fx"].answer
REVIEW_FIX = FINANCE.decision_answers["review_fix_authorization"].answer
MRR = load_scenario(ROOT / "scenarios/mrr-waterfall")
B7 = json.loads((ROOT / "tests/fixtures/operator-b7-run413-reapproval-replay.json").read_text(encoding="utf-8"))
SCRIPT = ROOT / "scripts/run_local_claude.py"


def _script(turns: int = 6) -> OperatorScript:
    return OperatorScript.from_components(
        PERSONA,
        FINANCE,
        turns=(FINANCE.opening_message, *("Please continue." for _ in range(turns - 1))),
        turn_budget=25,
        phase_by_turn={turn: 7 for turn in range(1, turns + 1)},
    )


def _router(decide: Callable[[dict], object], **kwargs) -> OperatorRouter:
    """A router whose fake model is a pure function of the JSON view it is shown."""

    def provider(view: RouterView) -> str:
        answer = decide(view.to_mapping())
        return answer if isinstance(answer, str) else json.dumps(answer)

    return OperatorRouter(provider, model_id="fake-router", **kwargs)


def _pick(option_id, category, *, approval=False, solicits=True, label=None) -> dict:
    return {
        "category": category,
        "option_id": option_id,
        "approval_requested": approval,
        "solicits_operator": solicits,
        "recommended_option_label": label,
    }


def _run(script: OperatorScript, messages: list[str], router: OperatorRouter | None):
    transport = InMemoryTransport(
        [TurnResult(agent_message=message) for message in messages]
        + [TurnResult(agent_message="Done.", reported=True)]
    )
    result = OperatorEngine(script, transport, router=router).run()
    return result, transport


# A phrasing no regex rule keys on: no "?", no choice vocabulary, no declared term.
ODD_ASK = "Quick thought on FX before I go on: your call on whether saturday and sunday quotes stay in the EUR total."


def test_regex_mode_misses_the_odd_phrasing_so_the_router_has_something_to_fix() -> None:
    result, transport = _run(_script(), ["What is the source?", ODD_ASK], None)
    assert transport.message_texts[2] != WEEKEND
    assert "routed_by" not in json.dumps(result.ledger_rows)


def test_router_routes_a_declared_decision_and_the_reply_stays_scripted() -> None:
    router = _router(lambda view: _pick("decision:weekend_fx", "decision_request"))
    result, transport = _run(_script(), ["What is the source?", ODD_ASK], router)

    assert transport.message_texts[2] == WEEKEND
    match = result.turns[1].match
    assert match.rule_id == "decision.answer.weekend_fx"
    assert match.decision_id == "weekend_fx"
    assert match.routed_by == "llm"
    assert not match.router_fallback
    assert MATCHED_RULE_ID_RE.fullmatch(match.rule_id)
    assert result.turns[2].delivered_decision_id == "weekend_fx"
    assert result.operator_mode == "llm_router"
    rows = [row for row in result.ledger_rows if row["matched_rule_id"] == "decision.answer.weekend_fx"]
    assert rows and rows[0]["claim"]["routed_by"] == "llm"
    assert "router_fallback" not in rows[0]["claim"]


def test_router_sees_source_topics_but_never_decision_answers_or_gold() -> None:
    seen: list[dict] = []

    def decide(view: dict) -> dict:
        seen.append(view)
        return _pick("none", "other", solicits=False)

    _run(_script(), ["What is the source?", ODD_ASK], _router(decide))
    blob = json.dumps(seen)
    assert WEEKEND not in blob and REVIEW_FIX not in blob
    for fact in FINANCE.ground_truth.values():
        assert fact.fact not in blob
    # B11 T2 needs declared topic text for opaque source keys such as data.
    for answer in FINANCE.source_answers.values():
        assert answer in blob
    ids = {option["id"] for option in seen[0]["options"]}
    assert {"approval", "decision:weekend_fx", "none", "deflect:decision"} <= ids
    # The generic review authorization is only offered while a review is in play.
    assert "decision:review_fix_authorization" not in ids


def test_router_routes_approval_from_the_r413_shapes_and_flags_come_from_the_router() -> None:
    def decide(view: dict) -> dict:
        return _pick("approval", "approval_request", approval=True)

    script = OperatorScript.from_components(
        MRR.persona,
        MRR.answer_sheet,
        events=MRR.events,
        turns=(MRR.answer_sheet.opening_message, "Please continue.", "Please continue."),
        turn_budget=3,
        phase_by_turn={1: 7, 2: 7, 3: 7},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=B7["turn_26_agent"]),
            TurnResult(agent_message=B7["turn_40_agent"]),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport, router=_router(decide)).run()
    for turn in (0, 1):
        match = result.turns[turn].match
        assert match.category is Category.APPROVAL_REQUEST
        assert match.approval_requested and match.solicits_operator
        assert match.rule_id == "persona.approval_request"
        assert match.routed_by == "llm"


def test_router_routes_the_review_authorization_on_the_r413_turn_38_ask() -> None:
    def decide(view: dict) -> dict:
        ids = {option["id"] for option in view["options"]}
        assert "decision:review_fix_authorization" in ids and "review_choice" in ids
        return _pick("decision:review_fix_authorization", "decision_request")

    script = OperatorScript.from_components(
        MRR.persona,
        MRR.answer_sheet,
        events=MRR.events,
        turns=(MRR.answer_sheet.opening_message, "Please continue."),
        turn_budget=2,
        phase_by_turn={1: 7, 2: 7},
    )
    transport = InMemoryTransport(
        [TurnResult(agent_message=B7["turn_38_agent"]), TurnResult(agent_message="Done.", reported=True)]
    )
    result = OperatorEngine(script, transport, router=_router(decide)).run()
    assert transport.message_texts[1] == MRR.answer_sheet.decision_answers["review_fix_authorization"].answer
    assert result.turns[0].match.rule_id == "decision.answer.review_fix_authorization"
    assert result.turns[1].delivered_decision_id == "review_fix_authorization"


REVIEW_CHOICE_ASK = (
    "The reviewer found a join fan-out finding. Which way should I go?\n"
    "- **Option A: keep the join and dedupe**\n"
    "- **Option B: drop the join**\n"
    "I recommend Option B."
)


def test_router_routes_a_review_choice_with_a_recommended_option() -> None:
    router = _router(lambda view: _pick("review_choice", "decision_request", label="Option B"))
    result, transport = _run(_script(), ["What is the source?", REVIEW_CHOICE_ASK], router)
    match = result.turns[1].match
    assert match.rule_id == "review.choice_undeclared"
    assert match.routed_by == "llm"
    assert transport.message_texts[2] == PERSONA.review_choice_reply("Option B")
    assert "Option B" in transport.message_texts[2]


def test_a_label_the_agent_never_wrote_is_rejected_and_falls_back() -> None:
    router = _router(lambda view: _pick("review_choice", "decision_request", label="Option Z"))
    result, _ = _run(_script(), ["What is the source?", REVIEW_CHOICE_ASK], router)
    match = result.turns[1].match
    assert match.router_fallback and match.router_failure_reason == "router_invalid_label"
    assert match.routed_by is None


@pytest.mark.parametrize(
    "response, reason",
    [
        (_pick("decision:does_not_exist", "decision_request"), "router_unavailable_option"),
        ("not json at all", "router_invalid_json"),
        ({"category": "other"}, "router_invalid_schema"),
        (_pick("approval", "decision_request", approval=True), "router_inconsistent"),
        (_pick("approval", "approval_request", approval=False), "router_inconsistent"),
        (_pick("none", "other", solicits=True), "router_inconsistent"),
        (_pick("decision:weekend_fx", "decision_request", solicits=False), "router_inconsistent"),
        ({**_pick("none", "other", solicits=False), "extra": 1}, "router_invalid_schema"),
    ],
)
def test_invalid_router_output_falls_back_to_regex_and_is_recorded(response, reason) -> None:
    router = _router(lambda view: response)
    result, transport = _run(_script(), ["What is the source?", "Should I exclude the weekend rate?"], router)
    match = result.turns[1].match
    # The regex matcher answers exactly as it would without a router...
    assert transport.message_texts[2] == WEEKEND
    assert match.rule_id == "decision.answer.weekend_fx"
    # ...and the ledger says the router was not what decided.
    assert match.router_fallback and match.router_failure_reason == reason
    assert match.routed_by is None
    row = next(row for row in result.ledger_rows if row["matched_rule_id"] == "decision.answer.weekend_fx")
    assert row["claim"]["router_fallback"] is True
    assert "routed_by" not in row["claim"]


def test_current_router_schema_requires_lists_and_only_allows_solicited_source_extras() -> None:
    matcher = MatcherBank(PERSONA, FINANCE)
    options = build_options(
        matcher,
        available_event_ids=(),
        delivered_decision_ids=frozenset(),
        decision_stage_counts={},
        review_in_play=False,
    )
    view = RouterView("What is the source and supporting data?", "", options)

    def current(**updates):
        payload = {
            "category": "source_question",
            "option_id": "source:source",
            "approval_requested": False,
            "solicits_operator": True,
            "recommended_option_labels": [],
            "additional_option_ids": [],
        }
        payload.update(updates)
        return json.dumps(payload)

    valid = validate_response(current(additional_option_ids=["source:data"]), view)
    assert valid.decision is not None
    assert [item.option_id for item in valid.decision.additional_options] == ["source:data"]

    for field, invalid in (
        ("recommended_option_labels", None),
        ("recommended_option_labels", "Option A"),
        ("additional_option_ids", None),
        ("additional_option_ids", "source:data"),
    ):
        outcome = validate_response(current(**{field: invalid}), view)
        assert outcome.decision is None and outcome.failure_reason == "router_invalid_schema"

    review_options = build_options(
        matcher,
        available_event_ids=(),
        delivered_decision_ids=frozenset(),
        decision_stage_counts={},
        review_in_play=True,
    )
    legacy_view = RouterView("The review recommends Option A.", "", review_options)
    legacy = {
        "category": "decision_request",
        "option_id": "review_choice",
        "approval_requested": False,
        "solicits_operator": True,
        "recommended_option_label": "Option A",
    }
    assert validate_response(json.dumps(legacy), legacy_view).decision is not None
    malformed_legacy = {**legacy, "recommended_option_label": []}
    outcome = validate_response(json.dumps(malformed_legacy), legacy_view)
    assert outcome.decision is None and outcome.failure_reason == "router_invalid_schema"

    unsolicited = validate_response(
        json.dumps({
            "category": "other",
            "option_id": "none",
            "approval_requested": False,
            "solicits_operator": False,
            "recommended_option_labels": [],
            "additional_option_ids": ["source:data"],
        }),
        view,
    )
    assert unsolicited.decision is None and unsolicited.failure_reason == "router_inconsistent"

    decision_extra = validate_response(
        json.dumps({
            "category": "decision_request",
            "option_id": "decision:weekend_fx",
            "approval_requested": False,
            "solicits_operator": True,
            "recommended_option_labels": [],
            "additional_option_ids": ["decision:reversal"],
        }),
        view,
    )
    assert decision_extra.decision is None and decision_extra.failure_reason == "router_inconsistent"


def test_a_staged_decision_that_is_not_yet_available_is_rejected_then_fallback() -> None:
    # same_month_classification unlocks only after event B7-same-month fires.
    matcher = MatcherBank(MRR.persona, MRR.answer_sheet)
    options = build_options(
        matcher,
        available_event_ids=(),
        delivered_decision_ids=frozenset(),
        decision_stage_counts={},
        review_in_play=False,
    )
    ids = {option.option_id for option in options}
    assert "decision:same_month_classification" not in ids
    unlocked = build_options(
        matcher,
        available_event_ids=("B7-same-month",),
        delivered_decision_ids=frozenset(),
        decision_stage_counts={},
        review_in_play=False,
    )
    assert "decision:same_month_classification" in {option.option_id for option in unlocked}

    view = RouterView("Same month?", "", options)
    outcome = validate_response(
        json.dumps(_pick("decision:same_month_classification", "decision_request")), view
    )
    assert outcome.decision is None and outcome.failure_reason == "router_unavailable_option"

    script = OperatorScript.from_components(
        MRR.persona,
        MRR.answer_sheet,
        events=MRR.events,
        turns=(MRR.answer_sheet.opening_message, "Please continue."),
        turn_budget=2,
        phase_by_turn={1: 7, 2: 7},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="How should a within the same month down and back up change appear in both directions?"),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    router = _router(lambda v: _pick("decision:same_month_classification", "decision_request"))
    result = OperatorEngine(script, transport, router=router).run()
    match = result.turns[0].match
    assert match.router_fallback and match.router_failure_reason == "router_unavailable_option"
    assert transport.message_texts[1] != MRR.answer_sheet.decision_answers["same_month_classification"].answer


def test_router_timeout_falls_back_to_regex() -> None:
    def slow(view: dict) -> dict:
        time.sleep(0.5)
        return _pick("none", "other", solicits=False)

    router = _router(slow, timeout_seconds=0.05)
    result, transport = _run(_script(), ["What is the source?", "Should I exclude the weekend rate?"], router)
    match = result.turns[1].match
    assert match.router_fallback and match.router_failure_reason == "router_timeout"
    assert transport.message_texts[2] == WEEKEND


def test_provider_exception_falls_back_without_leaking_its_message() -> None:
    def boom(view: dict) -> dict:
        raise RuntimeError("secret-token-abc")

    router = _router(boom)
    result, _ = _run(_script(), ["What is the source?", "Should I exclude the weekend rate?"], router)
    match = result.turns[1].match
    assert match.router_fallback and match.router_failure_reason == "router_error"
    assert "secret-token-abc" not in json.dumps(result.ledger_rows)


def test_answered_once_is_still_enforced_for_a_routed_decision() -> None:
    # The router insists on weekend_fx every time.  The first (and a verbatim
    # re-ask) are answered; a *different* question about it is not re-answered
    # from the routed choice -- the engine's own rule refuses it and deflects.
    # The regex path would instead match the source answer after excluding the
    # already-delivered decision, so this pins the model choice against an
    # adversarial matcher override.
    # This expectation intentionally changed: llm mode must not let a regex
    # re-match replace a valid model choice with an unrelated source answer.
    router = _router(
        lambda view: _pick("decision:weekend_fx", "decision_request")
        if "weekend" in view["agent_message"].casefold()
        else _pick("none", "other", solicits=False)
    )
    result, transport = _run(
        _script(7),
        [
            "What is the source?",
            "Should we exclude the weekend rate?",
            "**Should we exclude the WEEKEND rate?**",
            "What data should I use to verify the weekend rate?",
        ],
        router,
    )
    regex_alternative = MatcherBank(PERSONA, FINANCE).reply_for(
        "What data should I use to verify the weekend rate?",
        excluded_decision_ids=frozenset({"weekend_fx"}),
    )
    assert regex_alternative.answer_key == "data"
    assert regex_alternative.reply == FINANCE.source_answers["data"]
    assert transport.message_texts[2] == WEEKEND
    assert transport.message_texts[3] == WEEKEND
    assert transport.message_texts[4] != WEEKEND
    third = result.turns[3].match
    assert third.router_fallback and third.router_failure_reason == "router_answered_once"
    assert third.routed_by == "llm"


def test_valid_router_choices_never_call_the_regex_reply_matcher(monkeypatch) -> None:
    original_reply_matcher = MatcherBank.reply_for

    def forbidden_reply_matcher(self, message, *args, **kwargs):
        # Empty transport completions do not consult the router, so its
        # ordinary fallback remains available when there was no model choice.
        if not message.strip():
            return original_reply_matcher(self, message, *args, **kwargs)
        raise AssertionError("a valid router choice must not rerun the regex matcher")

    monkeypatch.setattr(MatcherBank, "reply_for", forbidden_reply_matcher)
    router = _router(
        lambda view: _pick("decision:weekend_fx", "decision_request")
        if "weekend" in view["agent_message"].casefold()
        else _pick("none", "other", solicits=False)
    )
    result, transport = _run(
        _script(5),
        [
            "Should we exclude the weekend rate?",
            "What data should I use to verify the weekend rate?",
        ],
        router,
    )
    assert transport.message_texts[1] == WEEKEND
    assert result.turns[1].match.rule_id == "unmatched.decision_request"
    assert result.turns[1].match.routed_by == "llm"


def test_none_routes_to_the_no_leading_fallback_and_asks_nothing() -> None:
    router = _router(lambda view: _pick("none", "other", solicits=False))
    result, transport = _run(_script(), ["What is the source?", "Building now; I will ping you when there is something to approve."], router)
    match = result.turns[1].match
    assert match.category is Category.OTHER and not match.solicits_operator and not match.approval_requested
    assert match.rule_id == "fallback.no-leading" and match.routed_by == "llm"


def test_every_routed_rule_id_is_lint_accepted() -> None:
    matcher = MatcherBank(MRR.persona, MRR.answer_sheet)
    sheet = MRR.answer_sheet
    options = build_options(
        matcher,
        available_event_ids=("B7-same-month", "B7-E8"),
        delivered_decision_ids=frozenset(),
        decision_stage_counts={},
        review_in_play=True,
    )
    assert options
    for option in options:
        result = matcher.route_result(
            option.option_id,
            option.kind,
            message="Please decide?",
            approval_requested=False,
            solicits_operator=True,
            recommended_option_label="Option A" if option.kind == "review_choice" else None,
        )
        assert MATCHED_RULE_ID_RE.fullmatch(result.rule_id), (option.option_id, result.rule_id)
        assert result.reply or option.kind in {"approval"}, option.option_id
    assert any(option.option_id.startswith("fact:") for option in options) == bool(sheet.ground_truth)


def test_replay_verification_is_not_attempted_for_routed_runs() -> None:
    status, reason = _replay_verification(
        MRR, SimpleNamespace(metadata={}), SimpleNamespace(), generated_operator=False, router=True
    )
    assert status == "not-attempted" and "model-routed" in reason


def _runner():
    spec = importlib.util.spec_from_file_location("dp_scenarios_run_local_claude_router", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pins() -> PinnedVersions:
    return PinnedVersions(
        skill_pack_version="1.0.0",
        supervisor_version="s",
        runtime_wheel_version="w",
        mock_api_version="m",
        canary_claims_hash="c",
        agent_model_id="sonnet",
        agent_sampling_params={"temperature": "provider-default"},
    )


def _fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    cli = tmp_path / name
    cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")


def _args(**overrides) -> SimpleNamespace:
    base = dict(operator_router="regex", router_backend=None, router_model=None, router_effort=None, router_timeout=None)
    return SimpleNamespace(**{**base, **overrides})


def test_regex_mode_is_the_identity_and_rejects_stray_router_flags() -> None:
    runner = _runner()
    pins = _pins()
    assert runner.router_configuration(_args(), pins) == (pins, None)
    with pytest.raises(TierError):
        runner.router_configuration(_args(router_model="gpt-6-sol"), pins)


def test_llm_mode_pins_the_router_identity_and_prompt_hash(tmp_path, monkeypatch) -> None:
    runner = _runner()
    _fake_cli(tmp_path, monkeypatch, "codex")
    pins = _pins()
    pinned, router = runner.router_configuration(
        _args(operator_router="llm", router_backend="codex", router_model="gpt-6-sol", router_effort="high", router_timeout=45.0),
        pins,
    )
    assert router is not None and router.model_id == "gpt-6-sol"
    assert pins.agent_sampling_params == {"temperature": "provider-default"}
    assert pinned.agent_sampling_params["operator_router"] == {
        "mode": "llm",
        "backend": "codex",
        "model_id": "gpt-6-sol",
        "effort": "high",
        "timeout_seconds": 45.0,
        "prompt_hash": router_prompt_hash(),
    }
    assert pinned.agent_sampling_params["temperature"] == "provider-default"
    with pytest.raises(TierError):
        runner.router_configuration(_args(operator_router="llm"), pins)


def test_claude_backend_is_constructible_without_credentials(tmp_path, monkeypatch) -> None:
    runner = _runner()
    _fake_cli(tmp_path, monkeypatch, "claude")
    pinned, router = runner.router_configuration(
        _args(operator_router="llm", router_backend="claude", router_model="sonnet"), _pins()
    )
    assert router is not None
    assert pinned.agent_sampling_params["operator_router"]["backend"] == "claude"
    assert "sonnet" in repr(router.provider) and "token" not in repr(router.provider).lower()


@pytest.mark.parametrize("rebinds", [1, 3])
def test_router_revision_approval_budget_stops_without_a_persona_reply(rebinds: int) -> None:
    from dp_scenarios.operator.engine import TerminalState
    from test_operator_revision_reapproval import APPROVAL, ASK, RESET, _call, _script

    transport = InMemoryTransport([
        TurnResult(agent_message=ASK),
        *(TurnResult(agent_message=ASK, tool_calls=(_call(RESET),)) for _ in range(rebinds)),
        TurnResult(agent_message="Done.", reported=True),
    ])
    router = _router(lambda view: (
        _pick("approval", "approval_request", approval=True)
        if view["agent_message"] != "Done."
        else _pick("none", "other", solicits=False)
    ))
    result = OperatorEngine(_script(rebinds + 2), transport, router=router).run()

    if rebinds == 3:
        # A persona loop after an exhausted budget only burns the turn budget.
        assert result.terminal_state is TerminalState.APPROVAL_BUDGET_EXHAUSTED
        assert result.stop_reason == "approval_budget_exhausted"
        assert transport.message_texts == ("Improve weekly visibility.", APPROVAL, APPROVAL, APPROVAL)
        assert len(result.turns) == 4
    else:
        assert result.terminal_state is not TerminalState.APPROVAL_BUDGET_EXHAUSTED
        assert transport.message_texts[1:3] == (APPROVAL, APPROVAL)
    assert all(turn.match.routed_by == "llm" for turn in result.turns[:rebinds + 1])

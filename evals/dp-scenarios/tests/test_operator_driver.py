"""Unit coverage for the free-authoring operator driver.

All provider calls here are fakes. The network guard is deliberately
autouse: a driver test must remain offline even if an implementation starts
to import or call a client accidentally.
"""

from __future__ import annotations

import ast
import pathlib
import socket
import time
from collections.abc import Callable

import aiohttp
import pytest

from dp_scenarios.operator.driver import (
    DriverBeat,
    DriverOperator,
    DriverViolation,
    DriverView,
    beat_violation,
    leading_violation,
    repeat_violation,
)
from dp_scenarios.operator import driver as driver_module
from dp_scenarios.operator.generated import GeneratedOperator, OperatorView


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("driver tests must not use the network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(aiohttp, "ClientSession", blocked)


def _view(*, beat: DriverBeat | None = None, forbidden_terms: tuple[str, ...] = ("stage",)) -> DriverView:
    return DriverView(
        turn=2,
        phase=1,
        persona_id="analyst",
        persona_label="Business analyst",
        persona_vocabulary=("clear", "direct"),
        persona_behaviors=("asks_questions",),
        agent_message="Where should I look next?",
        selected_reply="",
        prior_operator_messages=("Please continue.",),
        remaining_turns=8,
        prior_agent_messages=("What is the outcome?",),
        known_facts=(("source", "The source is in the profile."),),
        facts_already_stated=(),
        beat=beat,
        forbidden_terms=forbidden_terms,
        rejection_notice=None,
    )


class FakeProvider:
    def __init__(self, responses: list[object] | None = None, *, error: Exception | None = None) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.calls = 0
        self.views: list[DriverView] = []

    def __call__(self, view: DriverView) -> object:
        self.calls += 1
        self.views.append(view)
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)


def _operator(provider: Callable[[DriverView], object], **kwargs: object) -> DriverOperator:
    return DriverOperator(provider, model_id="test-driver", temperature=0.2, **kwargs)  # type: ignore[arg-type]


def _leading_check(text: str) -> DriverViolation | None:
    detail = leading_violation(text, forbidden_terms=("stage",), exempt_texts=())
    return DriverViolation("leading", detail) if detail else None


def test_leading_violation_uses_boundaries_and_agent_message_exemptions() -> None:
    assert leading_violation("Group it by stage", forbidden_terms=["stage"], exempt_texts=[]) == "stage"
    assert leading_violation("Group it by stage", forbidden_terms=["stage"], exempt_texts=["what stage?"]) is None
    assert leading_violation("staged rollout", forbidden_terms=["stage"], exempt_texts=[]) is None


def test_leading_violation_reports_all_non_exempt_terms_in_sheet_order() -> None:
    assert leading_violation(
        "Use stage history for this.",
        forbidden_terms=("stage", "history"),
        exempt_texts=("What stage is this?",),
    ) == "history"


def test_driver_rejects_a_leak_twice_and_names_it_on_the_second_view() -> None:
    provider = FakeProvider(["Group it by stage.", "Still group it by stage."])
    result = _operator(provider).author(_view(), fallback="Please continue.", check=_leading_check)

    assert result.text == "Please continue."
    assert result.used_fallback is True
    assert result.reason == "driver_leading_rejected"
    assert result.attempts == 2
    assert len(result.violations) == 2
    assert provider.calls == 2
    assert "stage" in (provider.views[1].rejection_notice or "")


def test_driver_reasks_once_and_accepts_compliance() -> None:
    provider = FakeProvider(["Group it by stage.", "I will keep the next step focused."])
    result = _operator(provider).author(_view(), fallback="Please continue.", check=_leading_check)

    assert result.text == "I will keep the next step focused."
    assert result.used_fallback is False
    assert result.reason is None
    assert result.violations[0].kind == "leading"
    assert result.attempts == 2
    assert provider.calls == 2


def test_driver_rejects_a_missing_beat_twice() -> None:
    beat = DriverBeat("scope-creep", ("scope", "refusal"))
    provider = FakeProvider(["I can address the scope.", "I can still address the scope."])
    result = _operator(provider).author(
        _view(beat=beat),
        fallback="The requested scope is outside this review.",
        check=lambda text: (
            DriverViolation("beat", detail)
            if (detail := beat_violation(text, beat))
            else None
        ),
    )

    assert result.text == "The requested scope is outside this review."
    assert result.reason == "driver_beat_rejected"
    assert result.violations[-1].kind == "beat"
    assert provider.calls == 2


def _repeat_check(text: str) -> DriverViolation | None:
    detail = repeat_violation(text, _view().prior_operator_messages)
    return DriverViolation("repeat", detail) if detail else None


def test_driver_reasks_a_verbatim_repeat_and_accepts_a_fresh_message() -> None:
    provider = FakeProvider(["Please continue!", "A new point."])
    result = _operator(provider).author(_view(), fallback="Where are we?", check=_repeat_check)

    assert result.text == "A new point."
    assert result.used_fallback is False
    assert result.violations[0].kind == "repeat"
    assert result.violations[0].detail == "repeats operator message 1"
    assert result.reason is None
    assert provider.calls == 2


def test_driver_falls_back_when_the_repeat_survives_the_re_ask() -> None:
    """The live-run defect: the same operator line sent a second time.

    The re-ask is not the guard -- the fallback is. A provider that repeats
    itself twice must never have its second repeat transmitted, and the
    recorded reason must name the repeat, not a generic provider failure.
    """

    provider = FakeProvider(["Please continue!", "  please continue.  "])
    result = _operator(provider).author(_view(), fallback="Where are we?", check=_repeat_check)

    assert result.text == "Where are we?"
    assert result.used_fallback is True
    assert result.reason == "driver_repeat_rejected"
    assert result.attempts == 2
    assert [violation.kind for violation in result.violations] == ["repeat", "repeat"]
    assert provider.calls == 2
    assert provider.views[1].rejection_notice == "repeat: repeats operator message 1"


@pytest.mark.parametrize(
    ("responses", "error", "kwargs", "reason"),
    [
        ([""], None, {}, "provider_empty"),
        (["x" * 10_000], None, {}, "provider_output_too_long"),
        ([], RuntimeError("503"), {}, "provider_error:RuntimeError"),
        ([], None, {"sleep": True}, "provider_timeout"),
    ],
)
def test_provider_failures_fall_back_without_retry(
    responses: list[object],
    error: Exception | None,
    kwargs: dict[str, object],
    reason: str,
) -> None:
    if kwargs.get("sleep"):
        calls = {"count": 0}

        def sleeping(_view: DriverView) -> str:
            calls["count"] += 1
            time.sleep(0.1)
            return "late"

        operator = _operator(sleeping, provider_timeout_seconds=0.01)
        result = operator.author(_view(), fallback="fallback", check=lambda _text: None)
        assert calls["count"] == 1
    else:
        provider = FakeProvider(responses, error=error)
        result = _operator(provider).author(_view(), fallback="fallback", check=lambda _text: None)
        assert provider.calls == 1
    assert result.text == "fallback"
    assert result.used_fallback is True
    assert result.reason == reason
    assert result.attempts == 1


def test_non_string_provider_output_is_empty_failure() -> None:
    provider = FakeProvider([object()])
    result = _operator(provider).author(_view(), fallback="fallback", check=lambda _text: None)
    assert result.reason == "provider_empty"
    assert provider.calls == 1


def test_driver_view_is_an_operator_view_and_has_exactly_six_extra_mapping_keys() -> None:
    view = _view(beat=DriverBeat("approval", ("approved",)))
    base_keys = set(OperatorView.to_mapping(view))
    mapping = view.to_mapping()

    assert isinstance(view, OperatorView)
    assert set(mapping) == base_keys | {
        "prior_agent_messages",
        "known_facts",
        "facts_already_stated",
        "beat",
        "forbidden_terms",
        "rejection_notice",
    }
    assert mapping["beat"] == {"id": "approval", "required_terms": ["approved"]}
    assert mapping["selected_reply"] == ""


def test_generated_operator_accepts_a_driver_view_unchanged() -> None:
    seen: list[OperatorView] = []

    def provider(view: OperatorView) -> str:
        seen.append(view)
        return "Rendered."

    view = _view()
    result = GeneratedOperator(provider).render(view, fallback="fallback", validate=lambda _text: None)
    assert result.text == "Rendered."
    assert seen == [view]


@pytest.mark.parametrize(
    ("field", "value"),
    [("model_id", ""), ("temperature", -0.1), ("temperature", 2.1), ("max_chars", 0), ("provider_timeout_seconds", 0)],
)
def test_driver_configuration_has_positive_bounds(field: str, value: object) -> None:
    kwargs: dict[str, object] = {field: value}
    with pytest.raises((TypeError, ValueError)):
        DriverOperator(FakeProvider(), model_id="driver", temperature=0.2, **kwargs)  # type: ignore[arg-type]


def test_driver_module_reaches_no_transport_directly() -> None:
    """The driver authors words; a transport is somebody else's module.

    Asserted over the parsed import graph rather than over a substring scan,
    so a re-export (``from aiohttp import ClientSession``) is caught too. The
    autouse network guard above covers the runtime; this covers the source, so
    an accidental client import fails even on a path no test exercises.
    """

    source = pathlib.Path(driver_module.__file__ or "").read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"aiohttp", "socket", "http", "urllib", "requests", "ssl"})
    assert imported == {"__future__", "collections", "dataclasses", "math", "typing"}

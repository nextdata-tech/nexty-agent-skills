"""Adapters that accept several collaborator shapes must exercise all of them.

Two small adapters in the operator sit between the harness and something it
does not own: ``engine._snapshot`` normalises a counter collaborator, and
``openai_driver._scrub``/``_empty_response_reason`` normalise what a provider
sent back.  Automated mutation testing (see "Mutation testing" in ``README.md``)
found every mutant of ``_snapshot`` alive -- all fifteen -- and three of
``_scrub``: the functions are reached, but only ever through one of the shapes
they claim to accept, so the other branches and both type guards could be
deleted with the whole suite green.

These live in their own module rather than in ``test_operator_engine.py`` and
``test_operator_openai_driver.py`` because a substantial change to
``engine.py`` and ``openai_driver.py`` is in flight on another branch and those
two test files move with it.  A new file adds the coverage without contending
for the same lines.

The adapters are private, and tested directly on purpose: their public callers
(``TurnEngine`` counter readers, a live provider POST) each need a great deal of
scaffolding, and it was exactly that scaffolding cost that left these branches
untested in the first place.
"""

from __future__ import annotations

import pytest

from dp_scenarios.operator.engine import _snapshot
from dp_scenarios.operator.openai_driver import _empty_response_reason, _scrub


# ---------------------------------------------------------------------------
# engine._snapshot
# ---------------------------------------------------------------------------


PAYLOAD = {"total": 3, "pages": 2}


def test_a_callable_counter_collaborator_is_called() -> None:
    calls: list[int] = []

    def reader() -> dict[str, object]:
        calls.append(1)
        return PAYLOAD

    assert _snapshot(reader) == PAYLOAD
    assert calls == [1]


def test_a_callable_is_preferred_over_its_own_snapshot_attribute() -> None:
    """The order of the checks is a decision, not an accident.

    A collaborator can be both callable and carry a ``snapshot`` attribute; if
    the branches were reordered the harness would silently read a different
    number.
    """

    class _Both:
        snapshot = staticmethod(lambda: {"total": 99})

        def __call__(self) -> dict[str, object]:
            return PAYLOAD

    assert _snapshot(_Both()) == PAYLOAD


def test_a_collaborator_with_a_snapshot_method_is_read_through_it() -> None:
    class _Snapshotter:
        def snapshot(self) -> dict[str, object]:
            return PAYLOAD

    assert _snapshot(_Snapshotter()) == PAYLOAD


def test_a_collaborator_with_only_a_read_method_is_read_through_it() -> None:
    """The mock REST server's counter port spells it ``read``."""

    class _Readable:
        def read(self) -> dict[str, object]:
            return PAYLOAD

    assert _snapshot(_Readable()) == PAYLOAD


def test_snapshot_is_preferred_over_read_when_both_exist() -> None:
    class _Both:
        def snapshot(self) -> dict[str, object]:
            return PAYLOAD

        def read(self) -> dict[str, object]:
            return {"total": 99}

    assert _snapshot(_Both()) == PAYLOAD


def test_a_collaborator_with_no_recognised_shape_is_refused_by_name() -> None:
    """Refused loudly: a counter the harness cannot read is not a counter of zero."""

    with pytest.raises(TypeError, match="snapshot\\(\\), read\\(\\), or be callable"):
        _snapshot(object())


@pytest.mark.parametrize("value", [None, [("total", 3)], "total=3", 3])
def test_a_collaborator_that_returns_a_non_mapping_is_refused(value: object) -> None:
    with pytest.raises(TypeError, match="counter snapshot must be a mapping"):
        _snapshot(lambda: value)


def test_the_returned_snapshot_is_a_copy_the_caller_cannot_mutate_back() -> None:
    """The evidence must not change under the collaborator's feet after it is read."""

    source = {"total": 3}

    taken = _snapshot(lambda: source)
    source["total"] = 99

    assert taken == {"total": 3}


# ---------------------------------------------------------------------------
# openai_driver._scrub
# ---------------------------------------------------------------------------


KEY = "sk-test-0123456789"


def test_the_bare_key_is_redacted_as_well_as_its_bearer_spelling() -> None:
    """Both spellings, because a provider error can carry either one.

    A key reaches a message either as the ``Authorization: Bearer ...`` header
    echoed back, or on its own in a request dump. Redacting only one leaves the
    other in the run's evidence, which is committed.
    """

    assert KEY not in _scrub(f"Authorization: Bearer {KEY}", KEY)
    assert KEY not in _scrub(f"request used {KEY} against the endpoint", KEY)
    assert KEY not in _scrub(f"{KEY} and Bearer {KEY}", KEY)


def test_the_bearer_form_is_replaced_whole_rather_than_leaving_a_bare_bearer() -> None:
    assert _scrub(f"Bearer {KEY}", KEY) == "<redacted>"


def test_scrubbing_leaves_everything_that_is_not_the_key_alone() -> None:
    message = "provider returned HTTP 429: rate limited, retry after 30s"

    assert _scrub(message, KEY) == message


def test_an_empty_key_scrubs_nothing_rather_than_redacting_everything() -> None:
    """``"".replace`` inserts the marker between every character.

    Without the early return, an unconfigured provider would turn every error
    message into a wall of ``<redacted>`` and the run would be undiagnosable.
    """

    message = "provider returned HTTP 500"

    assert _scrub(message, "") == message


# ---------------------------------------------------------------------------
# openai_driver._empty_response_reason
# ---------------------------------------------------------------------------


def test_a_finish_reason_is_named_in_the_diagnosis() -> None:
    reason = _empty_response_reason({"choices": [{"finish_reason": "length"}]})

    assert reason == "provider returned no text (finish_reason=length)"


@pytest.mark.parametrize(
    ("payload", "label"),
    [
        ({}, "no choices"),
        ({"choices": []}, "empty choices"),
        ({"choices": ["not a mapping"]}, "choice is not a mapping"),
        ({"choices": [{"finish_reason": None}]}, "reason is not a string"),
        ({"choices": [{"finish_reason": "   "}]}, "reason is blank"),
        ("not a mapping", "payload is not a mapping"),
    ],
)
def test_an_unusable_payload_still_produces_a_diagnosis(payload: object, label: str) -> None:
    """Every shape falls back to the plain sentence rather than raising.

    This runs while the driver is already reporting a failure; an exception
    here would replace a diagnosable message with a stack trace.
    """

    assert _empty_response_reason(payload) == "provider returned no text", label


def test_a_long_or_multiline_finish_reason_is_collapsed_and_bounded() -> None:
    """The reason goes into committed evidence, so its size is the harness's business."""

    reason = _empty_response_reason({"choices": [{"finish_reason": "a\n b\t" + "c" * 200}]})

    assert reason.startswith("provider returned no text (finish_reason=a b ")
    assert "\n" not in reason
    assert len(reason.split("finish_reason=", 1)[1].rstrip(")")) == 80

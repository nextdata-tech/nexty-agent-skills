"""Focused regression tests for the canary's operator-facing diagnostics."""

from __future__ import annotations

from typing import Any

from nightly_canary import _check_behaviour


def _observed(compiled: dict[str, Any]) -> dict[str, Any]:
    return {
        "refusal": {"error": "compile refused: unknown measure"},
        "compiled": compiled,
        "model": "model",
        "metric": "metric",
    }


def test_valid_selection_refusal_is_reported_as_a_compiler_refusal() -> None:
    failures = _check_behaviour(
        _observed({"error": "compile refused: unsafe selection"})
    )

    assert failures == [
        "the genuine compiler refused a selection taken from describe_model: compile refused: unsafe selection"
    ]


def test_valid_selection_with_sql_is_accepted() -> None:
    assert _check_behaviour(_observed({"compiled_sql": "SELECT 1", "error": ""})) == []

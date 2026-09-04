"""The contributor-facing reference must not drift from the loader.

`.claude/skills/dp-scenario-from-scratch/reference/scenario-anatomy.md` is what
a non-engineer follows instead of reading `scenario.py`. That makes an omission
in it a failed contribution rather than a lookup: the first version told
contributors to write `tier: draft`, which the loader rejects, and because
`load_scenarios` reads every package under the root, one such package would
have taken the whole suite red.

These tests derive the expectations from the code rather than restating them,
so adding a required key fails here until the reference documents it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dp_scenarios.grading.gates import GATE_PHASES
from dp_scenarios.operator.answer_sheet import ANSWER_SHEET_KEYS, OPTIONAL_ANSWER_SHEET_KEYS
from dp_scenarios.scenario import _SCENARIO_KEYS, _SCENARIO_TIERS

# tests/ -> dp-scenarios/ -> evals/ -> repo root. Resolved from this file rather
# than the working directory: CI runs pytest from evals/dp-scenarios and a
# developer runs it from the worktree root, and a CWD-relative path has broken
# this suite before.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFERENCE = _REPO_ROOT / ".claude/skills/dp-scenario-from-scratch/reference/scenario-anatomy.md"


def _reference_text() -> str:
    if not _REFERENCE.is_file():
        pytest.skip(f"authoring reference not present at {_REFERENCE}")
    return _REFERENCE.read_text(encoding="utf-8")


def _backticked(section: str) -> set[str]:
    return set(re.findall(r"`([a-z_]+)`", section))


def test_the_reference_names_every_required_scenario_key() -> None:
    text = _reference_text()
    listed = _backticked(text.split("Sixteen keys are required")[1].split("What each must contain")[0])

    assert not (_SCENARIO_KEYS - listed), (
        f"scenario.yaml keys missing from the contributor reference: "
        f"{sorted(_SCENARIO_KEYS - listed)}"
    )


def test_the_reference_names_every_required_answer_sheet_key() -> None:
    text = _reference_text()
    listed = _backticked(text.split("Ten keys are required")[1].split("Several may be empty")[0])

    assert not (ANSWER_SHEET_KEYS - listed), (
        f"answer-sheet keys missing from the contributor reference: "
        f"{sorted(ANSWER_SHEET_KEYS - listed)}"
    )
    # The two optional ones carry most of the substance, so they must be covered
    # too -- just not presented as required.
    assert OPTIONAL_ANSWER_SHEET_KEYS <= _backticked(text)


def test_the_reference_names_every_gate_and_no_invented_tier() -> None:
    text = _reference_text()

    for gate in GATE_PHASES:
        assert f"`{gate}`" in text, f"gate {gate} is not named in the reference"
    for tier in _SCENARIO_TIERS:
        assert f"`{tier}`" in text, f"tier {tier} is not named in the reference"

    # The defect this file exists for: instructing a tier the loader rejects.
    # Checking for the word alone is wrong -- the reference legitimately warns
    # that `draft` is not a tier -- so assert the instruction is absent and the
    # warning is present.
    assert "tier: draft" not in text, "the reference instructs an invalid tier"
    assert "There is no `draft` tier" in text, (
        "the reference must say `draft` is invalid; contributors reach for it"
    )

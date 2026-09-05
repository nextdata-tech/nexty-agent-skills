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
from dp_scenarios.scenario import _SCENARIO_KEYS, _SCENARIO_TIERS, load_scenarios

# tests/ -> dp-scenarios/ -> evals/ -> repo root. Resolved from this file rather
# than the working directory: CI runs pytest from evals/dp-scenarios and a
# developer runs it from the worktree root, and a CWD-relative path has broken
# this suite before.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFERENCE = _REPO_ROOT / ".claude/skills/dp-scenario-from-scratch/reference/scenario-anatomy.md"


def _reference_text() -> str:
    # Deliberately not a skip. Deleting the reference would then be green, and
    # the skills route every contributor to it -- its absence is the loudest
    # possible version of the drift these tests exist to catch.
    assert _REFERENCE.is_file(), (
        f"the contributor-facing authoring reference is missing at {_REFERENCE}; "
        "both scenario-authoring skills route contributors to it"
    )
    return _REFERENCE.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    """Return the text between two anchors, failing legibly if one moved.

    Splitting on a phrase raises IndexError when it is reworded, which reads as
    a broken test rather than the finding: the reference stopped saying the
    thing.
    """

    assert start in text, f"the document no longer contains the anchor {start!r}"
    assert end in text, f"the document no longer contains the anchor {end!r}"
    return text.split(start)[1].split(end)[0]


def _backticked(section: str) -> set[str]:
    return set(re.findall(r"`([a-z_]+)`", section))


def test_the_reference_names_every_required_scenario_key() -> None:
    text = _reference_text()
    listed = _backticked(_section(text, "Sixteen keys are required", "What each must contain"))

    assert not (_SCENARIO_KEYS - listed), (
        f"scenario.yaml keys missing from the contributor reference: "
        f"{sorted(_SCENARIO_KEYS - listed)}"
    )


def test_the_reference_names_every_required_answer_sheet_key() -> None:
    text = _reference_text()
    listed = _backticked(_section(text, "Ten keys are required", "Two rules that fail at load"))

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


_SKILLS = (
    _REPO_ROOT / ".claude/skills/dp-scenario-from-scratch/SKILL.md",
    _REPO_ROOT / ".claude/skills/dp-scenario-from-session/SKILL.md",
)


def _skill_texts() -> list[str]:
    texts = []
    for path in _SKILLS:
        assert path.is_file(), f"scenario-authoring skill missing at {path}"
        texts.append(path.read_text(encoding="utf-8"))
    return texts


def test_both_skills_ship_the_same_contributor_check() -> None:
    """The check block is duplicated verbatim; drift between the two is silent.

    Nothing under `_proposed/` is read by this suite, so the block a
    contributor runs is their only real feedback. Two copies of it that
    disagree means one set of contributors gets a weaker check than the other,
    and no test would notice.
    """

    scratch, session = _skill_texts()

    # Compare the fence *and* the paragraph beside it: the prose explaining
    # which constraints are guarded where is duplicated verbatim too, and a
    # correction applied to one copy only would leave every needle below intact
    # while the two skills told contributors different things.
    start = "uv run --project evals/dp-scenarios python -c"
    end = "Then run the suite"
    blocks = [_section(text, start, end) for text in (scratch, session)]

    assert blocks[0] == blocks[1], "the two skills' package checks have drifted apart"


def test_the_contributor_check_still_pins_what_nothing_else_does() -> None:
    """These three are the reason the block exists, so assert it keeps them.

    `turn_budget` equality is enforced by nothing anywhere else -- the loader
    checks only a floor and the equality test is hardcoded to
    capability-shortfall -- so dropping it from the block loses the constraint
    entirely rather than deferring it.
    """

    # Derived, not restated: the module docstring rules out restating, and a
    # literal 29 here would stay green through a fixture rebaseline while
    # telling contributors to pin the old value.
    #
    # Derived from *every* shipped package rather than one named it, because
    # that is the property the skills teach -- "every shipped package uses this
    # seed", not "capability-shortfall does". Naming one package would also
    # break this test if that package were ever renamed or retired.
    shipped = load_scenarios(_REPO_ROOT / "evals/dp-scenarios/scenarios")
    seeds = {scenario.seed for scenario in shipped}
    assert len(seeds) == 1, f"the shipped packages no longer agree on a seed: {sorted(seeds)}"
    shipped_seed = seeds.pop()

    for text in _skill_texts():
        assert f"s.seed == {shipped_seed}" in text, (
            f"the check no longer pins the seed the shipped packages use ({shipped_seed})"
        )
        assert "s.turn_budget == len(s.answer_sheet.turns)" in text, (
            "the check no longer pins turn_budget equality, which nothing else enforces"
        )
        assert "set(s.gates) == set(GATE_PHASES)" in text, "the check no longer pins the gate set"
        assert "s.required_plants" in text, "the check no longer pins required_plants"

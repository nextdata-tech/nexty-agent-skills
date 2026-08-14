"""The semantic-intent-validation scenario must exercise the coverage gate.

The intent-gate change (SKILL.md §6d/§6f) is behavioral: the agent must call
``describe_model`` on EVERY model ``list_models`` returns, deciding relevance
from each response rather than from names/grains first. The scenario's graded
checks and fixture must carry that rule, or a regression to the old
skip-permitting behavior scaffolds green.

These tests load the scenario's shipped artifacts (checks, catalog, prompt) and
assert the coverage rule is present and has teeth: a machine check names it, the
catalog carries a decoy model a skip-happy agent would wave off, and that decoy
owns the metric the clear question needs. All three assert the shipped files, so
they fail against the pre-fix state where the coverage check and decoy did not
exist.
"""

from __future__ import annotations

import json
from pathlib import Path

SCENARIO = Path(__file__).resolve().parents[1] / "public" / "semantic-intent-validation"


def _load(name: str):
    return json.loads((SCENARIO / "fixtures" / name).read_text(encoding="utf-8"))


def _checks():
    return json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))


def test_checks_json_names_the_coverage_rule():
    ids = {c["id"] for c in _checks()["checks"]}
    assert "coverage-all-models-described" in ids, (
        "graded checks must assert describe_model is called on EVERY model"
    )


def test_catalog_has_a_decoy_model():
    catalog = _load("catalog.json")
    names = {m["name"] for m in catalog["list_models"]}
    assert "partner_directory" in names, (
        "catalog must carry a decoy model a skip-happy agent would wave off"
    )


def test_decoy_owns_the_metric_the_clear_question_needs():
    catalog = _load("catalog.json")
    decoy = catalog["describe_model"]["partner_directory"]
    metric_names = {m["name"] for m in decoy["metrics"]}
    assert "partner_sourced_revenue" in metric_names, (
        "the misleadingly-named decoy must own partner_sourced_revenue so "
        "skipping it puts the Q3 answer out of reach"
    )
    dim_names = {d["name"] for d in decoy["dimensions"]}
    assert "partner_name" in dim_names, (
        "the decoy must expose partner_name as a dimension so Q3 can be "
        "sliced by partner"
    )


def test_prompt_does_not_teach_the_old_three_check_gate():
    prompt = (SCENARIO / "prompt.md").read_text(encoding="utf-8")
    assert "(critic + echo + clarify)" not in prompt, (
        "prompt must not enumerate the old three-step gate"
    )
    assert "coverage + critic + echo + clarify" in prompt, (
        "prompt must surface the coverage step in the gate enumeration"
    )
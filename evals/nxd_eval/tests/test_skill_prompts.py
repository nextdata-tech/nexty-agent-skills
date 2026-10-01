"""The skill-derived agent prompt stays in step with the shipped skills."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxd_eval import skill_prompt
from nxd_eval.skill_prompts import render_from_skills
from nxd_eval.solver import CONFIDENCE_INSTRUCTION

SRC = Path(__file__).resolve().parents[3] / "src"


@pytest.mark.skipif(not SRC.is_dir(), reason="skill pack sources not in this checkout")
def test_vendored_prompt_matches_skill_sources():
    assert skill_prompt() == render_from_skills(SRC), (
        "nexty_datamesh_query.md is stale against src/. Regenerate it from the "
        "repository root with `uv run --project evals/nxd_eval python -m "
        "nxd_eval.skill_prompts` and commit the result."
    )


def test_prompt_carries_the_query_procedure_and_intent_gate():
    prompt = skill_prompt()
    for needle in (
        "running non-interactively",
        "must appear as a filter in the selection",
        "compiled_sql applies each of those",
        "Semantic-layer MCP ports",
        "Intent gate (REQUIRED before `run_semantic_query`)",
        "Catalog-aware critic",
        "Round-trip echo",
        "## Execution rule",
    ):
        assert needle in prompt
    assert prompt.rstrip().endswith(CONFIDENCE_INSTRUCTION)


def test_prompt_has_no_links_into_the_skill_tree():
    assert "](" not in skill_prompt()


def test_unknown_pack_is_rejected():
    with pytest.raises(ValueError, match="unknown pack"):
        skill_prompt("nexty-desktop")


def test_moved_heading_fails_regeneration(tmp_path):
    for rel in (
        "nxd-query-data-product/SKILL.md",
        "nxd-semantic-query-intent/SKILL.md",
        "nxd-semantic-query-intent/reference/semantic-intent-validation.md",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("# renamed\n")
    with pytest.raises(ValueError, match="start marker not found"):
        render_from_skills(tmp_path)

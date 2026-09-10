"""The shared intent gate and both query adapters must carry the contract.

The deployed semantic-intent scenario remains the behavioral coverage, while
these tests guard the source-level seams that could otherwise silently drift:
the platform adapter's complete model-description rule, the shared four-part
gate, the desktop adaptation, and the scenario's package membership.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EVALS_DIR = REPO / "evals"
PLATFORM_SKILL = REPO / "src" / "nxd-query-data-product" / "SKILL.md"
DESKTOP_SKILL = REPO / "src" / "nxd-run-job-loop" / "SKILL.md"
SHARED_SKILL = REPO / "src" / "nxd-semantic-query-intent" / "SKILL.md"
SHARED_REFERENCE = SHARED_SKILL.parent / "reference" / "semantic-intent-validation.md"
SCENARIO = EVALS_DIR / "public" / "semantic-intent-validation"
SEMANTIC_QUERY_SCENARIOS = {
    "authenticated-api-source-supervisor",
    "job-loop-export-handoff",
    "job-loop-serve-query-refine",
    "optional-empty-output-aggregate-desktop",
    "pharma-cross-dp-mesh-query",
    "pharma-mesh-query-hard",
    "pharma-mesh-query-loop",
}


@pytest.fixture(scope="module")
def run_module():
    sys.path.insert(0, str(EVALS_DIR))
    try:
        import run  # noqa: PLC0415
    finally:
        sys.path.remove(str(EVALS_DIR))
    return run


def _load(name: str):
    return json.loads((SCENARIO / "fixtures" / name).read_text(encoding="utf-8"))


def _checks():
    return json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))


def _flat(text: str) -> str:
    """Collapse whitespace so assertions survive prose re-wrapping."""
    return re.sub(r"\s+", " ", text)


def _platform_text() -> str:
    return _flat(PLATFORM_SKILL.read_text(encoding="utf-8"))


def _shared_text() -> str:
    return _flat(SHARED_REFERENCE.read_text(encoding="utf-8"))


# --- the rule ships in the skill (guards the file that actually changed) ---


def test_skill_requires_describe_model_on_every_model():
    """§6d step 2 must require reading every model, not the intended subset."""
    text = _platform_text()
    assert "`describe_model(name)` on EVERY model" in text, (
        "§6d step 2 must require describe_model on EVERY model — the pre-fix "
        "wording ('for each model you intend to query') let relevance be "
        "decided from list_models-only evidence"
    )
    assert "do not decide relevance first" in text, (
        "§6d step 2 must state that relevance is decided from each "
        "describe_model response, never before it"
    )


def test_shared_reference_contains_the_canonical_four_part_gate():
    """The detailed gate lives once in the shared progressive-disclosure reference."""
    text = _shared_text()
    assert "## The four techniques" in text
    for technique in (
        "Coverage (no skipping)",
        "Catalog-aware critic",
        "Round-trip echo",
        "Clarification on ambiguity",
    ):
        assert technique in text, f"shared reference must contain {technique}"
    assert "Run all four checks before execution" in text
    assert "Execute only when the verdict is `ok`" in text
    assert "explicitly confirms" in text
    assert "compatible_dimensions" in text
    assert "reaches_dimensions" in text


def test_shared_reference_is_platform_neutral():
    """The shared reference must not smuggle either adapter's runtime contract in."""
    text = SHARED_REFERENCE.read_text(encoding="utf-8").lower()
    for forbidden in (
        "mesh",
        "gateway",
        "credential leasing",
        "direct-store",
        "query-system-dp",
        "mcp__nxd-desktop",
    ):
        assert forbidden not in text, f"shared reference must not mention {forbidden!r}"


def test_both_adapters_reference_the_shared_foundation():
    """Desktop and DataMesh keep their surface-specific adapters over one gate."""
    for skill in (PLATFORM_SKILL, DESKTOP_SKILL):
        text = skill.read_text(encoding="utf-8")
        assert "../nxd-semantic-query-intent/SKILL.md" in text
        assert "../nxd-semantic-query-intent/reference/semantic-intent-validation.md" in text
    desktop_text = DESKTOP_SKILL.read_text(encoding="utf-8")
    assert "complete catalog for this local closure" in desktop_text
    assert "Do not apply mesh-sized catalog narrowing here" in desktop_text
    assert "query-system behavior out of this local path" in desktop_text


def test_skill_coverage_step_matches_the_large_catalog_carve_out():
    """§6d must handle large catalogs for both interactive and non-interactive sessions.

    The cross-DP path uses the mesh-merged registry, which routinely exceeds the
    large-catalog threshold. Non-interactive callers (eval harness claude -p,
    scheduled runs, scripted callers) have no user to answer a narrowing question.
    Both §6d step 2 and §6f step 0 must cover both cases, or an agent in a
    non-interactive cross-DP session has to either block on an unanswerable
    AskUserQuestion or violate a REQUIRED gate.
    """
    text = _platform_text()
    # Interactive path: the narrowing ask is still available.
    assert "if a user is reachable" in text, (
        "§6d step 2 must keep the large-catalog interactive-narrowing path"
    )
    # Non-interactive fallback: proceed over the full set, state size in echo.
    assert "no user is reachable" in text, (
        "§6d step 2 must add a non-interactive fallback (proceed over the full "
        "set, state catalog size in the echo) — without it, a non-interactive "
        "session against a large cross-DP mesh blocks on an unanswerable "
        "AskUserQuestion or violates the REQUIRED gate"
    )
    gate = _shared_text()
    assert "agreed scope" in gate, (
        "§6f step 0 must scope coverage to the agreed scope, or it contradicts "
        "the narrowing §6d permits"
    )
    assert "no user is reachable" in gate, (
        "§6f step 0 must carry the non-interactive fallback alongside §6d step 2 "
        "so the gate and the discovery rule stay consistent"
    )


# --- the scenario can catch a regression (guards the eval arm) ---


def test_checks_json_names_the_coverage_rule():
    skills = set(_checks()["skills"])
    assert skills == {"nxd-query-data-product", "nxd-semantic-query-intent"}
    ids = {c["id"] for c in _checks()["checks"]}
    assert "coverage-all-models-described" in ids, (
        "graded checks must assert describe_model is called on EVERY model"
    )


def test_every_semantic_query_scenario_declares_shared_skill():
    """Shared intent changes must select every scenario that exercises querying."""
    public = EVALS_DIR / "public"
    for scenario in SEMANTIC_QUERY_SCENARIOS:
        checks = json.loads((public / scenario / "checks.json").read_text(encoding="utf-8"))
        skills = set(checks["skills"])
        assert "nxd-semantic-query-intent" in skills, scenario
        assert skills.intersection({"nxd-query-data-product", "nxd-run-job-loop"}), scenario


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


def test_agent_facing_task_does_not_leak_the_answers(run_module):
    """Only the task section reaches the agent; it must not restate the checks.

    Graded through the runner's own splitter rather than a re-implementation, so
    this tracks what the agent is actually handed. If the coverage rule or the
    decoy's metric is named there, the two coverage checks grade prompt-following
    and a `no_skills` baseline passes them — the arm stops attributing behavior
    to the skill.
    """
    prompt = (SCENARIO / "prompt.md").read_text(encoding="utf-8")
    task = run_module.agent_task_from_prompt(prompt).lower()

    for leaked in (
        "partner_sourced_revenue",
        "partner_directory",
        "every model",
        "describe_model",
        "decoy",
        "right move",
    ):
        assert leaked not in task, (
            f"the agent-facing task section must not name {leaked!r} — that "
            f"turns a graded check into an instruction the agent merely follows"
        )

    # It must still hand the agent the three questions, or there is no task.
    for question in ("q1", "q2", "q3"):
        assert question in task, f"the task section must still pose {question}"

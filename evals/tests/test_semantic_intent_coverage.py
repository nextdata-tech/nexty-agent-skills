"""The describe-every-model coverage rule must ship in the skill AND be graded.

The intent-gate change (SKILL.md §6d/§6f) is behavioral: the agent must call
``describe_model`` on every model in the agreed scope, deciding relevance from
each response rather than from names/grains first. Two things have to hold, and
they fail independently:

* **The rule ships.** ``src/nxd-query-data-product/SKILL.md`` must carry it —
  §6d step 2 requiring `describe_model` on EVERY model, and §6f's gate opening
  with a coverage step. These assertions are the carrying evidence for the
  `NO_EVAL` benchmark entry: reverting the instruction turns them red without
  touching anything under ``evals/``.
* **The scenario can catch a regression.** The graded checks and fixture must
  carry the rule too, or an agent that skips models still scores green.

The scope carve-out is asserted on both sides: §6d lets a large catalog be
narrowed by domain, so §6f step 0 must speak of the *agreed scope* rather than
demanding the full ``list_models`` set unconditionally — otherwise an agent that
correctly narrows under §6d fails the gate that §6d feeds.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EVALS_DIR = REPO / "evals"
SKILL = REPO / "src" / "nxd-query-data-product" / "SKILL.md"
SCENARIO = EVALS_DIR / "public" / "semantic-intent-validation"


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


def _skill_text() -> str:
    return _flat(SKILL.read_text(encoding="utf-8"))


def _intent_gate_section() -> str:
    """The §6f intent-gate block: from 'Intent gate (REQUIRED' to the next H2."""
    text = SKILL.read_text(encoding="utf-8")
    start = text.index("Intent gate (REQUIRED")
    rest = text[start:]
    end = re.search(r"\n## ", rest)
    return _flat(rest[: end.start()] if end else rest)


# --- the rule ships in the skill (guards the file that actually changed) ---


def test_skill_requires_describe_model_on_every_model():
    """§6d step 2 must require reading every model, not the intended subset."""
    text = _skill_text()
    assert "`describe_model(name)` on EVERY model" in text, (
        "§6d step 2 must require describe_model on EVERY model — the pre-fix "
        "wording ('for each model you intend to query') let relevance be "
        "decided from list_models-only evidence"
    )
    assert "do not decide relevance first" in text, (
        "§6d step 2 must state that relevance is decided from each "
        "describe_model response, never before it"
    )


def test_skill_intent_gate_opens_with_a_coverage_step():
    """§6f must run a coverage check, and count itself as four steps."""
    gate = _intent_gate_section()
    assert "Run all four" in gate, (
        "the intent gate must enumerate four steps once coverage is added"
    )
    assert "Coverage — no model skipped" in gate, (
        "§6f must carry step 0 'Coverage — no model skipped'"
    )
    assert "is **not** a valid skip" in gate, (
        "§6f step 0 must declare 'it's a different grain' an invalid skip — "
        "that loophole is the whole point of the step"
    )


def test_skill_coverage_step_matches_the_large_catalog_carve_out():
    """§6d must handle large catalogs for both interactive and non-interactive sessions.

    The cross-DP path uses the mesh-merged registry, which routinely exceeds the
    large-catalog threshold. Non-interactive callers (eval harness claude -p,
    scheduled runs, scripted callers) have no user to answer a narrowing question.
    Both §6d step 2 and §6f step 0 must cover both cases, or an agent in a
    non-interactive cross-DP session has to either block on an unanswerable
    AskUserQuestion or violate a REQUIRED gate.
    """
    text = _skill_text()
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
    gate = _intent_gate_section()
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

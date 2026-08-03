"""The pocket loop must TEACH resume-first reattach, not reopen-by-rebuild.

The desktop supervisor gained `list_data_products` and `resume_data_product`:
a fresh session with no live endpoint reattaches to a published workflow in
seconds instead of paying a full rebuild. The skill text is the only thing that
makes the agent prefer that path — a live end-to-end scenario needs a real
supervisor (`ci_skip`), so this plain-pytest gate pins the guidance itself.

It asserts, over the shipped skill/reference text (no agent, no supervisor):

1. The reattach guidance orders the tools resume-first —
   `list_data_products` before `resume_data_product` before the
   `build_data_product` fallback.
2. The stale three-tool / no-list / reopen-by-rebuild framing is gone from the
   pocket-loop skill and the generate-dp build-record reference.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

POCKET_LOOP = SRC / "nxd-pocket-loop"
SKILL = POCKET_LOOP / "SKILL.md"
CONTEXT_AND_RESUME = POCKET_LOOP / "reference" / "context-and-resume.md"
HANDOFF_EXPORT = POCKET_LOOP / "reference" / "handoff-export.md"
BUILD_RECORD = POCKET_LOOP / "reference" / "build-record.md"
SCHEDULING = POCKET_LOOP / "reference" / "scheduling.md"
GENERATE_DP_CLOSURE_RECORD = SRC / "nxd-generate-data-product" / "reference" / "closure-record.md"

# The three tools whose relative order encodes "reattach before rebuild".
LIST = "list_data_products"
RESUME = "resume_data_product"
BUILD = "build_data_product"

# Text that would only be present under the old three-tool runtime model.
STALE_PHRASES = [
    "no list, status, or rediscovery",
    "no list, status, resume",
    "reopen-by-rebuild",
    "reopening is always a rebuild",
    "reopening is therefore always a rebuild",
    "exactly three tools",
]

# The deleted reference doc must stay deleted (folded into context-and-resume).
REMOVED_DOC = POCKET_LOOP / "reference" / "reopen.md"


def _first_index(haystack: str, needle: str) -> int:
    idx = haystack.find(needle)
    assert idx != -1, f"expected to find {needle!r} in the reattach guidance"
    return idx


def test_context_and_resume_exists_and_reopen_removed():
    assert CONTEXT_AND_RESUME.is_file(), "context-and-resume.md must exist"
    assert SCHEDULING.is_file(), "scheduling.md must exist"
    assert not REMOVED_DOC.exists(), (
        "reopen.md must be deleted — its content folded into context-and-resume.md"
    )


def test_closure_path_and_self_check_contracts_name_the_closure_root():
    closure_path = "`…/nxd-pocket/<workflow>/closure/`"
    assert closure_path in CONTEXT_AND_RESUME.read_text()
    assert closure_path in HANDOFF_EXPORT.read_text()
    build_record = BUILD_RECORD.read_text()
    assert "scripts/self_check.py" not in build_record
    assert "python3 self_check.py" in build_record


def test_reattach_guidance_orders_list_resume_then_build_fallback():
    text = CONTEXT_AND_RESUME.read_text()
    # All three tools are named in the reattach playbook.
    for tool in (LIST, RESUME, BUILD):
        assert tool in text, f"context-and-resume.md must name {tool}"
    # Resume-first ordering: list, then resume, then build appears only later
    # (as the fallback), never as the first-taught recovery step.
    i_list = _first_index(text, LIST)
    i_resume = _first_index(text, RESUME)
    i_build = _first_index(text, BUILD)
    assert i_list < i_resume, "list_data_products must be taught before resume"
    assert i_resume < i_build, (
        "resume_data_product must be taught before the build_data_product "
        "rebuild fallback — rebuild is the fallback, not the default"
    )


def test_fallback_is_gated_on_artifact_gone():
    text = CONTEXT_AND_RESUME.read_text().lower()
    # The rebuild fallback must be conditioned on the artifact being gone,
    # not offered as an unconditional alternative.
    assert "collected" in text and "artifact_unavailable" in text, (
        "the rebuild fallback must name the collected / artifact_unavailable states"
    )
    # And the gating must be explicit: rebuild is the fallback / only-when path,
    # never offered unconditionally. Guard against an edit that keeps the state
    # names but drops the condition.
    assert re.search(r"rebuild is the fallback", text) or re.search(
        r"only when the (published )?artifact is (genuinely )?gone", text
    ), "the rebuild fallback must be explicitly gated, not offered unconditionally"


def _strip_markdown(text: str) -> str:
    # Drop emphasis/code markers so a reintroduction that keeps the markdown
    # (``**no** list, status``) still matches the plain stale phrase.
    return re.sub(r"[*`_]", "", text).lower()


@pytest.mark.parametrize(
    "doc",
    [SKILL, CONTEXT_AND_RESUME, SCHEDULING, GENERATE_DP_CLOSURE_RECORD],
    ids=lambda p: p.parent.name + "/" + p.name,
)
def test_no_stale_three_tool_framing(doc):
    text = _strip_markdown(doc.read_text())
    for phrase in STALE_PHRASES:
        assert phrase.lower() not in text, (
            f"{doc} still carries stale three-tool framing: {phrase!r}"
        )


def test_skill_names_the_six_tools_and_delegates():
    text = SKILL.read_text()
    # The skill body must name the reattach tools and point at the two new docs.
    for tool in (LIST, RESUME):
        assert tool in text, f"SKILL.md must reference {tool}"
    assert "reference/scheduling.md" in text
    assert "reference/context-and-resume.md" in text

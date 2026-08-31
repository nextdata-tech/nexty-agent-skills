"""The verify-before-build closure file list must read identically everywhere.

Four skill files tell an agent what a finished closure contains, and they are
written by two different workstreams. If they disagree, an agent verifies
against whichever one it happened to read and ships a closure missing the file
the other one names. So the list is a frozen string and this test compares them
after collapsing whitespace — line wrapping may differ, wording may not.

Un-skipped at integration: WS4 and WS5 have both landed, so the four carriers
exist and must agree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from _closure_files import FILE_LIST, GENERATED_CLOSURE_FILES, collapse

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

# §9, frozen, and defined once in _closure_files so the sibling gate in
# test_generation_subagent_gate.py cannot drift from it.
CARRIERS = (
    SRC / "nxd-generate-data-product" / "SKILL.md",
    SRC / "nxd-run-job-loop" / "reference" / "scheduling.md",
    SRC / "nxd-run-job-loop" / "reference" / "handoff-export.md",
    SRC / "nxd-review-closure" / "SKILL.md",
)

COAUTHOR_PROMPTS = (
    REPO / "evals" / "public" / "coauthor-supplied-rubric" / "prompt.md",
    REPO / "evals" / "public" / "coauthor-executable-policy-readback" / "prompt.md",
)





@pytest.mark.parametrize("path", CARRIERS, ids=lambda p: p.name)
def test_the_file_list_appears_verbatim(path):
    assert path.is_file(), f"{path} is missing"
    assert collapse(FILE_LIST) in collapse(path.read_text(encoding="utf-8")), (
        f"{path.relative_to(REPO)} does not carry the frozen verify-before-build "
        "list. An agent that reads this file must verify the same set as an agent "
        "that reads any of the others."
    )


@pytest.mark.parametrize("name", GENERATED_CLOSURE_FILES)
def test_the_generated_record_files_are_named_in_the_generator(name):
    text = (SRC / "nxd-generate-data-product" / "SKILL.md").read_text(encoding="utf-8")
    assert name in text, f"the generator never mentions emitting {name}"


@pytest.mark.parametrize("prompt", COAUTHOR_PROMPTS, ids=lambda path: path.parent.name)
def test_coauthor_prompts_name_the_complete_closure_records(prompt):
    text = prompt.read_text(encoding="utf-8")
    for name in (*GENERATED_CLOSURE_FILES, "README.md"):
        assert name in text, f"{prompt.relative_to(REPO)} omits required closure file {name}"

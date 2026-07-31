"""The verify-before-build closure file list must read identically everywhere.

Four skill files tell an agent what a finished closure contains, and they are
written by two different workstreams. If they disagree, an agent verifies
against whichever one it happened to read and ships a closure missing the file
the other one names. So the list is a frozen string and this test compares them
after collapsing whitespace — line wrapping may differ, wording may not.

SKIPPED until integration: it asserts against files owned by WS4 and WS5 and
cannot pass until both land. A red suite mid-fan-out is indistinguishable from a
real regression.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

# §9, frozen. Nothing here may be paraphrased, pluralized or reordered.
FILE_LIST = (
    "`spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`, "
    "`requirements.txt`, `dp-spec.approved.md`, `dp-spec.lock.json`, "
    "`build-record.json`, `README.md`, the connector companion artifact — and, "
    "for a credentialed source, `SENSITIVE` and `.gitignore`"
)

CARRIERS = (
    SRC / "nxd-generate-dp" / "SKILL.md",
    SRC / "nxd-pocket-loop" / "reference" / "scheduling.md",
    SRC / "nxd-pocket-loop" / "reference" / "handoff-export.md",
    SRC / "nxd-review-closure" / "SKILL.md",
)

GENERATED_CLOSURE_FILES = (
    "dp-spec.approved.md",
    "dp-spec.lock.json",
    "build-record.json",
)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


pytestmark = pytest.mark.skip(
    reason="un-skip at integration — asserts against WS4/WS5-owned files"
)


@pytest.mark.parametrize("path", CARRIERS, ids=lambda p: p.name)
def test_the_file_list_appears_verbatim(path):
    assert path.is_file(), f"{path} is missing"
    assert _collapse(FILE_LIST) in _collapse(path.read_text(encoding="utf-8")), (
        f"{path.relative_to(REPO)} does not carry the frozen verify-before-build "
        "list. An agent that reads this file must verify the same set as an agent "
        "that reads any of the others."
    )


@pytest.mark.parametrize("name", GENERATED_CLOSURE_FILES)
def test_the_generated_record_files_are_named_in_the_generator(name):
    text = (SRC / "nxd-generate-dp" / "SKILL.md").read_text(encoding="utf-8")
    assert name in text, f"the generator never mentions emitting {name}"

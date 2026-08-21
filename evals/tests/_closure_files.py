"""The frozen verify-before-build closure file list, defined exactly once.

Four skill files tell an agent what a finished closure contains, and two
separate gate modules assert they all carry this list verbatim
(`test_closure_layout_gate.py` over all four carriers,
`test_generation_subagent_gate.py` over `scheduling.md`). The string used to be
copy-pasted byte-identically into both, each marked "frozen" — so an edit to the
file set had to land in two places, and an edit that reached only one would
leave the other asserting a list no carrier produces: a gate that fails for a
confusing reason, or worse, verifies wording nothing writes.

Change the set here and both gates move together.
"""

from __future__ import annotations

import re

# §9, frozen. Nothing here may be paraphrased, pluralized or reordered.
FILE_LIST = (
    "`spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`, "
    "`requirements.txt`, `dp-blueprint.approved.md`, `dp-blueprint.lock.json`, "
    "`build-record.json`, `README.md`, the connector companion artifact where the "
    "type has one — and, "
    "for a credentialed source, `SENSITIVE` and `.gitignore`"
)

# The generated records inside that set — the three files the retired prose doc
# was replaced by, which the generator must name explicitly.
GENERATED_CLOSURE_FILES = (
    "dp-blueprint.approved.md",
    "dp-blueprint.lock.json",
    "build-record.json",
)


def collapse(text: str) -> str:
    """Line wrapping may differ between carriers; wording may not."""
    return re.sub(r"\s+", " ", text).strip()

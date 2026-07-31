"""`CONTEXT.md` is retired. It must survive nowhere in the shipped pack.

The retirement is only real if nothing still tells an agent to write the file.
A single leftover instruction in a reference doc keeps producing it, and a
closure carrying a hand-written prose record alongside a hashed spec snapshot is
worse than either alone — two sources of truth, one of them unverifiable.

ONE carve-out, by exact filename: the design note whose subject IS the
retirement. It cannot avoid naming the thing it retired, and it is the
historical record of why the file went away. Never a prefix, never a pattern —
a second exempted file would let the rot back in.

SKIPPED until integration: it asserts against files owned by WS3, WS4 and WS5
and fails until all of them land.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = (REPO / "src", REPO / "docs")

CARVE_OUT = REPO / "docs" / "architecture" / "dp-spec-authoritative.md"
FORBIDDEN = ("CONTEXT.md", "context-doc.md")

pytestmark = pytest.mark.skip(
    reason="un-skip at integration — asserts against WS3/WS4/WS5-owned files"
)


def _files() -> list[Path]:
    found: list[Path] = []
    for root in SEARCH_ROOTS:
        found.extend(p for p in root.rglob("*") if p.is_file())
    return found


@pytest.mark.parametrize("needle", FORBIDDEN)
def test_the_retired_names_appear_nowhere(needle):
    offenders = []
    for path in _files():
        if path == CARVE_OUT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if needle in text:
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, (
        f"{needle} still appears in: {sorted(offenders)}. A leftover instruction "
        "keeps producing the file this change retired."
    )


def test_the_context_doc_file_itself_is_gone():
    assert not (REPO / "src" / "nxd-generate-dp" / "reference" / "context-doc.md").exists()


def test_the_carve_out_is_one_exact_path():
    assert CARVE_OUT.is_file()
    assert CARVE_OUT.name == "dp-spec-authoritative.md"

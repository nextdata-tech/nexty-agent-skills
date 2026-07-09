"""Drift guard for the vendored PoC scoring primitives.

``src/nxd_eval/_ex_core/poc_scoring/{scoring,structure_check}.py`` are copied
verbatim from the text-to-SQL PoC harness. That PoC tree is not present on every
checkout, so we can't diff the copy against a live source of truth here. Instead
we pin each vendored file's SHA-256: an *accidental* edit (a stray formatter run,
a well-meaning "cleanup") fails this test loudly, while a *deliberate* re-vendor
is a one-line, reviewed hash bump in this file.

When you intentionally re-copy the two files from the PoC harness because its
scoring contract changed:
  1. re-copy the files,
  2. run ``shasum -a 256 src/nxd_eval/_ex_core/poc_scoring/*.py``,
  3. update the pins below in the same commit,
  4. confirm ``test_scoring_adapter.py`` still passes (the semantics didn't
     silently move under you).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_VENDOR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "nxd_eval"
    / "_ex_core"
    / "poc_scoring"
)

# SHA-256 of the verbatim PoC copies. Bump deliberately on re-vendor (see module
# docstring); never edit the files in place without bumping these.
_PINNED = {
    "scoring.py": "f5724f3b8a8c741b48bdc797cc4bfc2ce455ea0cba81a57fefd96cbada4ca0db",
    "structure_check.py": "2624ec76e12ee4f1384325a5eed5fcfdd224b9eda3e7e1bdb48c984272e21987",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_vendored_files_match_pinned_hashes():
    for name, want in _PINNED.items():
        path = _VENDOR / name
        assert path.exists(), f"vendored primitive missing: {path}"
        got = _sha256(path)
        assert got == want, (
            f"{name} drifted from its pinned hash.\n"
            f"  pinned: {want}\n"
            f"  actual: {got}\n"
            "If this is a deliberate re-vendor, bump the pin in this file "
            "(see module docstring); otherwise you edited a verbatim PoC copy "
            "in place — revert it."
        )


def test_pinned_set_covers_every_vendored_module():
    # If someone adds a third vendored primitive, force them to pin it too, so the
    # drift guard can't be silently bypassed by dropping in an unpinned file.
    on_disk = {p.name for p in _VENDOR.glob("*.py") if p.name != "__init__.py"}
    assert on_disk == set(_PINNED), (
        f"vendored *.py set {sorted(on_disk)} != pinned set {sorted(_PINNED)}; "
        "add the new file to _PINNED with its SHA-256."
    )

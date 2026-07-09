"""Drift guard for the vendored PoC scoring primitives.

``_ex_core/_primitives/{scoring,structure_check}.py`` are copied *verbatim* from
the text-to-SQL PoC harness they originated in, so their whole-file SHA-256 is
pinned. (``_ex_core/score.py`` is NOT a copy — nxd_eval owns it as the
deterministic-EX source of truth; the cross-DP harness imports it. So it needs
no drift guard.)

The PoC source tree is not present on every checkout, so we can't diff against a
live source of truth here. Pinning catches an *accidental* edit (a stray
formatter run, a well-meaning "cleanup") loudly, while a *deliberate* re-vendor
is a one-line, reviewed hash bump in this file.

When you intentionally re-copy a primitive because the upstream scoring contract
changed:
  1. re-copy the file(s),
  2. run ``shasum -a 256 src/nxd_eval/_ex_core/_primitives/*.py``,
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
    / "_primitives"
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

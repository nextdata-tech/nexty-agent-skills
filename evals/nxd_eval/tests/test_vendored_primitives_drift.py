"""Drift guard for the vendored deterministic-EX core.

Three files are copied from the text-to-SQL PoC / cross-DP harness they
originated in and must stay in lockstep with those origins:

* ``_ex_core/_primitives/{scoring,structure_check}.py`` — copied *verbatim*, so
  their whole-file SHA-256 is pinned.
* ``_ex_core/score.py`` — copied from ``cross-dp-joins/harness/score.py`` with
  its import block adapted for a package import (``T2SQL_POC_ROOT`` path-loading
  → ``from ._primitives import …``). The import block is intentionally
  package-specific, so we pin a hash of the *scoring logic only* — everything
  from the ``COMPILER_STRATEGY`` definition to EOF. That body carries the
  harness-layer name-aware multi-measure guard (part of "what PASS means"), so a
  silent edit there — or drift from the cross-DP origin — fails this test.

Those source trees are not present on every checkout, so we can't diff against a
live source of truth here. Pinning catches an *accidental* edit (a stray
formatter run, a well-meaning "cleanup") loudly, while a *deliberate* re-vendor
is a one-line, reviewed hash bump in this file.

When you intentionally re-copy a file because the upstream scoring contract
changed:
  1. re-copy the file(s),
  2. for a primitive: ``shasum -a 256 src/nxd_eval/_ex_core/_primitives/*.py``;
     for ``score.py``: re-run this test to read the new body hash from the
     failure message (or recompute the ``COMPILER_STRATEGY``-onward slice),
  3. update the pins below in the same commit,
  4. confirm ``test_scoring_adapter.py`` still passes (the semantics didn't
     silently move under you).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_EX_CORE = (
    Path(__file__).resolve().parents[1] / "src" / "nxd_eval" / "_ex_core"
)
_VENDOR = _EX_CORE / "_primitives"

# SHA-256 of the verbatim PoC copies. Bump deliberately on re-vendor (see module
# docstring); never edit the files in place without bumping these.
_PINNED = {
    "scoring.py": "f5724f3b8a8c741b48bdc797cc4bfc2ce455ea0cba81a57fefd96cbada4ca0db",
    "structure_check.py": "2624ec76e12ee4f1384325a5eed5fcfdd224b9eda3e7e1bdb48c984272e21987",
}

# score.py is a copy of cross-dp-joins/harness/score.py with an adapted import
# block; pin only the scoring-logic body (COMPILER_STRATEGY -> EOF) so the part
# that defines "what PASS means" can't silently drift from its origin.
_SCORE_BODY_MARKER = 'COMPILER_STRATEGY = '
_SCORE_BODY_PINNED = (
    "9a113ea09f00a2a6d6c878869d2204cd30495bda1fb0c25974e0e05d35f9ae9c"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _score_body_sha256() -> str:
    src = (_EX_CORE / "score.py").read_text()
    body = src[src.index(_SCORE_BODY_MARKER):]
    return hashlib.sha256(body.encode()).hexdigest()


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


def test_score_body_matches_pinned_hash():
    got = _score_body_sha256()
    assert got == _SCORE_BODY_PINNED, (
        "the scoring logic in _ex_core/score.py drifted from its pinned hash.\n"
        f"  pinned: {_SCORE_BODY_PINNED}\n"
        f"  actual: {got}\n"
        "This body is a copy of cross-dp-joins/harness/score.py (the name-aware "
        "multi-measure guard etc.). If this is a deliberate re-vendor, bump "
        "_SCORE_BODY_PINNED in this file; otherwise you edited the scoring logic "
        "in place — revert it, or move the change to the cross-DP origin and "
        "re-copy. (The import block above COMPILER_STRATEGY is excluded, so "
        "adapting imports does not trip this.)"
    )


def test_pinned_set_covers_every_vendored_module():
    # If someone adds a third vendored primitive, force them to pin it too, so the
    # drift guard can't be silently bypassed by dropping in an unpinned file.
    on_disk = {p.name for p in _VENDOR.glob("*.py") if p.name != "__init__.py"}
    assert on_disk == set(_PINNED), (
        f"vendored *.py set {sorted(on_disk)} != pinned set {sorted(_PINNED)}; "
        "add the new file to _PINNED with its SHA-256."
    )

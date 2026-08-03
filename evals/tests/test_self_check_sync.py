"""The shipped ``scripts/self_check.py`` must stay byte-identical to the fenced
script an agent copies out of ``self-check.md``.

At real session time the agent does not import ``scripts/self_check.py`` — it
writes the fenced block from ``reference/self-check.md`` into the closure and
runs it there. That fence is therefore the source of truth for runtime
behaviour, and a checked-in twin only earns its keep if the two cannot silently
diverge. These tests are that guarantee:

- the markdown carries exactly one ``self_check.py`` fence,
- the fence body equals ``scripts/self_check.py`` byte-for-byte, and
- both parse as valid Python.

Edit the fence, and this test fails until ``scripts/self_check.py`` is
regenerated from it (or vice versa). Neither copy is allowed to drift.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF_CHECK_MD = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "self-check.md"
SELF_CHECK_PY = REPO_ROOT / "scripts" / "self_check.py"

_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _fence_body() -> str:
    """The single ``# self_check.py`` fenced block from the reference doc."""
    blocks = _FENCE.findall(SELF_CHECK_MD.read_text())
    self_check = [b for b in blocks if b.lstrip().startswith("# self_check.py")]
    assert len(self_check) == 1, (
        f"expected exactly one '# self_check.py' python fence in "
        f"{SELF_CHECK_MD.name}, found {len(self_check)}"
    )
    return self_check[0]


def test_shipped_file_matches_fence_byte_for_byte() -> None:
    fence = _fence_body()
    shipped = SELF_CHECK_PY.read_text()
    assert shipped == fence, (
        "scripts/self_check.py has drifted from the self-check.md fence. "
        "The fence is what the agent runs at session time; regenerate the file "
        "from it (or update the fence) so the two stay identical."
    )


def test_fence_is_valid_python() -> None:
    ast.parse(_fence_body(), "self-check.md:fence")


def test_shipped_file_is_valid_python() -> None:
    ast.parse(SELF_CHECK_PY.read_text(), str(SELF_CHECK_PY))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

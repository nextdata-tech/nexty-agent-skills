"""The labeled-root checkers must read a looped closure as they read an unrolled one.

`multi-source-labeled-roots` regressed PASS -> FAIL in CI on a closure that was
correct. The agent pinned both labeled roots to `NXD_TRANSFORM_ROOT` and then
looped over them:

    for source_root, model in ((orders_root, "orders"), (users_root, "users")):
        filesystem(bucket_url=str(source_root / model), file_glob="*.csv")

The checker propagates root-ness through `ast.Assign`/`ast.AnnAssign` only, so a
root bound by a `for` target vanished from the analysis and
`transform-uses-pinned-root` failed. The baseline PASS had been recorded against
an agent that happened to spell the same thing out. Nothing in the suite covered
the loop form -- the existing `VALID_TRANSFORM` is unrolled -- so the blind spot
was invisible until an agent wrote the DRY version.

Same class as the `urllib.parse` false positive on the api-source gate: keying
on a bound name instead of resolving what it refers to. These tests pin both
directions -- correct closures are read correctly, and the loop is not a hole a
genuinely unpinned closure can hide in.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS / "tools"))

from loop_unroll import unroll_literal_loops  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


SUPERVISOR = _load(
    "loop_unroll_supervisor_checker",
    EVALS / "public/multi-source-labeled-roots-supervisor/fixtures/check_supervisor_pin.py",
)

HEAD = '''
import os
from pathlib import Path
from dlt.sources.filesystem import filesystem

def _root_from_path_file(root, filename):
    value = (root / filename).read_text("utf-8").strip()
    return root / value

def ingest():
    execution_root = Path(os.environ["NXD_TRANSFORM_ROOT"])
    orders_root = _root_from_path_file(execution_root, "csv-source-orders-path")
    users_root = _root_from_path_file(execution_root, "csv-source-users-path")
'''

# Every spelling below is the SAME correct closure. The checker must not have an
# opinion about which one the agent chose.
EQUIVALENT_SPELLINGS = {
    "unrolled": '''
    filesystem(bucket_url=orders_root / "orders")
    filesystem(bucket_url=users_root / "users")
''',
    "loop over inline literal": '''
    for source_root, model in ((orders_root, "orders"), (users_root, "users")):
        filesystem(bucket_url=str(source_root / model), file_glob="*.csv")
''',
    "loop over named literal": '''
    PAIRS = ((orders_root, "orders"), (users_root, "users"))
    for source_root, model in PAIRS:
        filesystem(bucket_url=str(source_root / model), file_glob="*.csv")
''',
    "loop over zip": '''
    for source_root, model in zip((orders_root, users_root), ("orders", "users")):
        filesystem(bucket_url=str(source_root / model), file_glob="*.csv")
''',
    "loop over list of lists": '''
    for source_root, model in [[orders_root, "orders"], [users_root, "users"]]:
        filesystem(bucket_url=str(source_root / model), file_glob="*.csv")
''',
}


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "main.py"
    path.write_text(HEAD + body, encoding="utf-8")
    return path


@pytest.mark.parametrize("spelling", sorted(EQUIVALENT_SPELLINGS))
def test_every_spelling_of_a_correct_closure_passes(tmp_path: Path, spelling: str):
    path = _write(tmp_path, EQUIVALENT_SPELLINGS[spelling])
    assert SUPERVISOR.transform_uses_pinned_roots(path), (
        f"{spelling!r} pins both roots exactly as the unrolled form does"
    )


def test_an_unpinned_loop_is_still_rejected(tmp_path: Path):
    """The fix must not turn the loop into a hole.

    Unrolling makes more closures READABLE, not more closures acceptable: a
    closure whose roots come from cwd rather than the pinned execution root
    fails whether or not it is written as a loop.
    """
    path = tmp_path / "main.py"
    path.write_text('''
import os
from pathlib import Path
from dlt.sources.filesystem import filesystem

def ingest():
    execution_root = Path(os.environ["NXD_TRANSFORM_ROOT"])
    for source_root, model in ((Path.cwd(), "orders"), (Path.cwd(), "users")):
        filesystem(bucket_url=str(source_root / model), file_glob="*.csv")
''', encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)


def test_a_partially_pinned_loop_is_rejected(tmp_path: Path):
    # Only one of the two roots is pinned. Unrolling must expose that rather
    # than let the pinned iteration vouch for the other.
    path = _write(tmp_path, '''
    for source_root, model in ((orders_root, "orders"), (Path.cwd(), "users")):
        filesystem(bucket_url=str(source_root / model), file_glob="*.csv")
''')
    assert not SUPERVISOR.transform_uses_pinned_roots(path)


# ---------------------------------------------------------------------------
# unroll_literal_loops itself
# ---------------------------------------------------------------------------


def _unparse(src: str) -> str:
    return ast.unparse(unroll_literal_loops(ast.parse(src)))


def test_tuple_target_is_destructured_and_constants_inlined():
    out = _unparse('for a, b in ((x, "orders"), (y, "users")):\n    f(a, b)\n')
    # Both the binding and the inlined constant: name propagation reads the
    # first, label matching reads the second.
    assert "a = x" in out and "b = 'orders'" in out
    assert "f(x, 'orders')" in out and "f(y, 'users')" in out
    assert "for " not in out


def test_nested_literal_loops_are_both_expanded():
    out = _unparse('for a in (1, 2):\n    for b in (3, 4):\n        f(a, b)\n')
    assert "for " not in out
    for pair in ("f(1, 3)", "f(1, 4)", "f(2, 3)", "f(2, 4)"):
        assert pair in out, out


def test_a_non_literal_loop_is_left_alone():
    """An unanalyzable loop must stay as it is, failing exactly as before.

    Silently dropping it would be the dangerous direction: the check would then
    be reasoning about code that is not there.
    """
    src = "for row in fetch_rows():\n    f(row)\n"
    assert "for row in fetch_rows()" in _unparse(src)


@pytest.mark.parametrize("statement", ["break", "continue"])
def test_loops_carrying_flow_control_are_left_alone(statement: str):
    # Unrolling asserts every iteration's body runs, which is what break and
    # continue deny.
    src = f'for a in (1, 2):\n    if a:\n        {statement}\n    f(a)\n'
    assert "for a in (1, 2)" in _unparse(src)


def test_a_nested_loops_break_does_not_block_the_outer_loop():
    # The break belongs to the inner loop, so the outer one is still expandable.
    src = 'for a in (1, 2):\n    for b in fetch():\n        break\n    f(a)\n'
    out = _unparse(src)
    assert "f(1)" in out and "f(2)" in out


def test_a_name_the_body_rebinds_is_not_substituted():
    # Substituting under a rebinding would report on a value the code replaced.
    out = _unparse('for a in ("x",):\n    a = other()\n    f(a)\n')
    assert "f('x')" not in out


def test_enumerate_over_a_literal_is_expanded():
    out = _unparse('for i, v in enumerate(("orders", "users")):\n    f(i, v)\n')
    assert "f(0, 'orders')" in out and "f(1, 'users')" in out


def test_expansion_is_bounded():
    """A pathological literal must not be expanded without limit."""
    src = f"for a in ({','.join(str(n) for n in range(400))},):\n    f(a)\n    g(a)\n"
    assert "for a in (" in _unparse(src), "should decline rather than expand"


def test_unparseable_input_falls_back_to_the_original_tree():
    tree = ast.parse("x = 1\n")
    assert unroll_literal_loops(tree) is not None

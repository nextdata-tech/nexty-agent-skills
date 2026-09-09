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
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS / "tools"))

import loop_unroll  # noqa: E402
from loop_unroll import unroll_literal_loops  # noqa: E402
from loop_unroll import MAX_EXPANDED_NODES  # noqa: E402


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
# DictComp normalization and unroll_literal_loops
# ---------------------------------------------------------------------------


def _unparse(src: str) -> str:
    return ast.unparse(unroll_literal_loops(ast.parse(src)))


DICT_COMP_SOURCE = '''
import os
from pathlib import Path
from dlt.sources.filesystem import filesystem

_LABELED_ROOTS = (("orders", "csv-source-orders-path"),
                  ("users", "csv-source-users-path"))

def _relative_root(root, path_file, data_root):
    relative = (root / path_file).read_text("utf-8").strip()
    return root / relative

def ingest():
    root = Path(os.environ["NXD_TRANSFORM_ROOT"])
    source_roots = {
        label: _relative_root(root, path_file, f"data-{label}")
        for label, path_file in _LABELED_ROOTS
    }
    for label, model in _LABELED_ROOTS:
        filesystem(bucket_url=str(source_roots[label] / model), file_glob="*.csv")
'''


def _dict_comps(tree: ast.AST) -> list[ast.DictComp]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.DictComp)]


def test_labeled_root_dict_comprehension_is_expanded_and_inlined():
    tree = unroll_literal_loops(ast.parse(DICT_COMP_SOURCE))
    assert not _dict_comps(tree)

    source_roots = next(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "source_roots"
                for target in node.targets)
    )
    assert isinstance(source_roots, ast.Dict)
    assert [key.value for key in source_roots.keys] == ["orders", "users"]
    assert all(
        not any(isinstance(name, ast.Name) and name.id in {"label", "path_file"}
                and isinstance(name.ctx, ast.Load)
                for name in ast.walk(value))
        for value in source_roots.values
    )


def test_public_checker_accepts_the_live_labeled_root_shape(tmp_path: Path):
    root = tmp_path / "closure"
    (root / "transform").mkdir(parents=True)
    for name, content in {
        "spec.py": "",
        "models.py": "",
        "infra-profile.yaml": "services:\n  - name: csv-source-orders\n  - name: csv-source-users\n",
        "requirements.txt": "",
        "companion-files": "data-orders\ndata-users\n",
        "README.md": "directory-companion supervisor\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    (root / "transform/main.py").write_text(DICT_COMP_SOURCE, encoding="utf-8")

    fixture_root = EVALS / "public/multi-source-labeled-roots/fixtures"
    for label in ("orders", "users"):
        source = fixture_root / f"source-{label}" / label / f"{label}.csv"
        destination = root / f"data-{label}" / label / f"{label}.csv"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        (root / f"csv-source-{label}-path").write_text(
            f"data-{label}\n", encoding="utf-8"
        )

    result = subprocess.run(
        [
            sys.executable,
            str(fixture_root / "check_labeled_multi_source.py"),
            "--fixtures",
            str(fixture_root),
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout


def test_supervisor_checker_accepts_the_live_labeled_root_shape(tmp_path: Path):
    path = tmp_path / "main.py"
    path.write_text(DICT_COMP_SOURCE, encoding="utf-8")
    assert SUPERVISOR.transform_uses_pinned_roots(path)


def test_unsafe_same_shape_expands_but_fails_provenance(tmp_path: Path):
    source = DICT_COMP_SOURCE.replace(
        'source_roots = {\n'
        '        label: _relative_root(root, path_file, f"data-{label}")\n',
        'source_roots = {\n'
        '        label: Path.cwd() / path_file\n',
    )
    tree = unroll_literal_loops(ast.parse(source))
    assert not _dict_comps(tree), "the checker must inspect the expanded shape"
    path = tmp_path / "main.py"
    path.write_text(source, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)


@pytest.mark.parametrize(
    "source",
    [
        "result = {label: path for label, path in get_rows()}",
        "result = {label: path for label, path in ((\"orders\", \"x\"),) if label}",
        "result = {left: right for left in (\"a\",) for right in (\"b\",)}",
        "result = {label: path for label, path in ((\"same\", \"x\"), (\"same\", \"y\"))}",
        "result = {(seen := label): path for label, path in ((\"orders\", \"x\"),)}",
        "result = {label: (lambda: label)() for label in (\"orders\",)}",
        "result = {label: [item for item in (1,)] for label in (\"orders\",)}",
        "result = {label: path for label, path in ((\"orders\",),)}",
        "result = {label: path for label, *rest in ((\"orders\", \"x\"),)}",
        "result = {label: path for label, path in ((root, \"x\"),)}",
        "async def build():\n    return {label: path async for label, path in ((\"orders\", \"x\"),)}",
    ],
)
def test_unsafe_dict_comprehensions_are_left_unchanged(source: str):
    tree = unroll_literal_loops(ast.parse(source))
    assert _dict_comps(tree), source


def test_inline_list_iterable_remains_eligible():
    source = (
        'result = {label: path for label, path in '
        '[["orders", "x"], ["users", "y"]]}'
    )
    assert not _dict_comps(unroll_literal_loops(ast.parse(source)))


@pytest.mark.parametrize(
    "source",
    [
        '''
_PAIRS = [["orders", "x"], ["users", "y"]]
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = [["orders", "x"], ["users", "y"]]
_PAIRS[0] = ["archive", "z"]
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = [["orders", "x"], ["users", "y"]]
_PAIRS.append(["archive", "z"])
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = [["orders", "x"], ["users", "y"]]
alias = _PAIRS
alias.append(["archive", "z"])
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = (("orders", "x"), ["users", "y"])
result = {label: path for label, path in _PAIRS}
''',
    ],
)
def test_named_lists_never_supply_dict_comprehension_rows(source: str):
    assert _dict_comps(unroll_literal_loops(ast.parse(source))), source


def test_named_iterable_expansion_requires_unique_binding():
    sources = [
        '''
if False:
    _PAIRS = (("orders", "x"),)
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = (("orders", "x"),)
_PAIRS = (("users", "y"),)
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = (("orders", "x"),)
if enabled:
    _PAIRS = (("users", "y"),)
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = (("orders", "x"),)
def build(_PAIRS):
    return _PAIRS
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = (("orders", "x"),)
import source as _PAIRS
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = (("orders", "x"),)
try:
    raise RuntimeError
except RuntimeError as _PAIRS:
    pass
result = {label: path for label, path in _PAIRS}
''',
        '''
_PAIRS = (("orders", "x"),)
match value:
    case _ as _PAIRS:
        pass
result = {label: path for label, path in _PAIRS}
''',
    ]
    for source in sources:
        assert _dict_comps(unroll_literal_loops(ast.parse(source))), source


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 requires Python 3.12")
@pytest.mark.parametrize("type_parameter", ["_PAIRS", "**_PAIRS", "*_PAIRS"])
def test_pep695_type_parameter_shadowing_blocks_named_iterable_expansion(
    type_parameter: str,
):
    source = f'''
_PAIRS = (("orders", "x"),)
def shadow[{type_parameter}]():
    pass
result = {{label: path for label, path in _PAIRS}}
'''
    assert _dict_comps(unroll_literal_loops(ast.parse(source))), source


def test_dict_comprehension_budget_is_checked_before_row_copies(
    monkeypatch: pytest.MonkeyPatch,
):
    rows = ", ".join(f"(\"key-{index}\", \"value-{index}\")"
                      for index in range(MAX_EXPANDED_NODES))
    source = f"result = {{key: value for key, value in ({rows},)}}"
    tree = ast.parse(source)

    def unexpected_copy(_node: ast.AST):
        raise AssertionError("oversized expansion copied a row before budget refusal")

    monkeypatch.setattr(loop_unroll.copy, "deepcopy", unexpected_copy)
    tree = unroll_literal_loops(tree)
    assert _dict_comps(tree), "an oversized expansion must remain a DictComp"


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

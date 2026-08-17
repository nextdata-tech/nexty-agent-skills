"""Regression tests for the labeled-root eval checkers."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


EVALS = Path(__file__).parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PUBLIC = _load(
    "labeled_root_public_checker",
    EVALS / "public/multi-source-labeled-roots/fixtures/check_labeled_multi_source.py",
)
SUPERVISOR = _load(
    "labeled_root_supervisor_checker",
    EVALS / "public/multi-source-labeled-roots-supervisor/fixtures/check_supervisor_pin.py",
)


VALID_TRANSFORM = """
import os
from pathlib import Path
from dlt.sources.filesystem import filesystem

def ingest():
    execution_root = Path(os.environ["NXD_TRANSFORM_ROOT"])
    orders_path = execution_root / "csv-source-orders-path"
    users_path = execution_root / "csv-source-users-path"
    orders_relative = orders_path.read_text(encoding="utf-8").strip()
    users_relative = users_path.read_text(encoding="utf-8").strip()
    orders_root = execution_root / orders_relative
    users_root = execution_root / users_relative
    filesystem(bucket_url=orders_root / "orders")
    filesystem(bucket_url=users_root / "users")
"""


def test_path_checker_rejects_unpinned_conditional_branch(tmp_path: Path) -> None:
    transform = VALID_TRANSFORM.replace(
        "orders_root = execution_root / orders_relative",
        "orders_root = (execution_root if True else Path.cwd()) / orders_relative",
    )
    path = tmp_path / "main.py"
    path.write_text(transform, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)


def test_manifest_checker_rejects_all_mutation_destinations() -> None:
    for operation in (
        'Path("companion-files").touch()',
        'os.unlink("companion-files")',
        'Path("other").replace("companion-files")',
    ):
        tree = ast.parse("from pathlib import Path\nimport os\n" + operation)
        assert PUBLIC.transform_writes_manifest(tree), operation


def test_path_checker_accepts_pinned_path_files(tmp_path: Path) -> None:
    path = tmp_path / "main.py"
    path.write_text(VALID_TRANSFORM, encoding="utf-8")
    assert SUPERVISOR.transform_uses_pinned_roots(path)

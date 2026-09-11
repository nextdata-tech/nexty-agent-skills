"""Regression tests for the labeled-root eval checkers."""

from __future__ import annotations

import ast
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


EVALS = Path(__file__).parents[1]
PUBLIC_CHECKER = EVALS / "public/multi-source-labeled-roots/fixtures/check_labeled_multi_source.py"
PUBLIC_FIXTURES = EVALS / "public/multi-source-labeled-roots/fixtures"


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


MODEL_ROOT_TRANSFORM = """
import os
from pathlib import Path
from dlt.sources.filesystem import filesystem

def _root_from_path_file(execution_root, label):
    path_file = execution_root / f"csv-source-{label}-path"
    relative_root = path_file.read_text(encoding="utf-8").strip()
    return execution_root / relative_root

def ingest():
    execution_root = Path(os.environ["NXD_TRANSFORM_ROOT"])
    roots = {
        label: _root_from_path_file(execution_root, label)
        for label in ("orders", "users")
    }
    for label, model in (("orders", "orders"), ("users", "users")):
        model_root = roots[label] / model
        filesystem(bucket_url=str(model_root), file_glob="*.csv")
"""


ONE_LABEL_UNROOTED_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "model_root = roots[label] / model",
    "model_root = (roots[label] if label == \"orders\" else Path.cwd()) / model",
)


REASSIGNED_UNROOTED_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "model_root = roots[label] / model",
    "model_root = roots[label] / model\n        model_root = Path.cwd() / model",
)


STATEMENT_BRANCH_UNROOTED_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "model_root = roots[label] / model",
    "if label == \"orders\":\n"
    "            model_root = roots[label] / model\n"
    "        else:\n"
    "            model_root = Path.cwd() / model",
)


ONE_READER_FOR_BOTH_LABELS_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "        filesystem(bucket_url=str(model_root), file_glob=\"*.csv\")\n",
    "    filesystem(bucket_url=str(model_root), file_glob=\"*.csv\")\n",
)


AMBIGUOUS_READER_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "    for label, model in ((\"orders\", \"orders\"), (\"users\", \"users\")):\n"
    "        model_root = roots[label] / model\n"
    "        filesystem(bucket_url=str(model_root), file_glob=\"*.csv\")\n",
    "    filesystem(\n"
    "        bucket_url=str(roots[\"orders\"] / roots[\"users\"] / \"users\"),\n"
    "        file_glob=\"*.csv\",\n"
    "    )\n",
)


SUBSCRIPT_REASSIGNMENT_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "    for label, model in ((\"orders\", \"orders\"), (\"users\", \"users\")):\n",
    "    roots[\"users\"] = Path.cwd()\n"
    "    for label, model in ((\"orders\", \"orders\"), (\"users\", \"users\")):\n",
)


MIXED_NAME_SUBSCRIPT_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "model_root = roots[label] / model\n"
    "        filesystem(bucket_url=str(model_root), file_glob=\"*.csv\")",
    "model_root = roots[label] / model\n"
    "        filesystem(bucket_url=str(model_root / roots[\"users\"]), file_glob=\"*.csv\")",
)


SUBSCRIPT_ALIAS_REASSIGNMENT_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "    for label, model in ((\"orders\", \"orders\"), (\"users\", \"users\")):\n",
    "    alias = roots\n"
    "    alias[\"users\"] = Path.cwd()\n"
    "    for label, model in ((\"orders\", \"orders\"), (\"users\", \"users\")):\n",
)


UNPINNED_OPERAND_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "model_root = roots[label] / model",
    "model_root = roots[label] / Path.cwd()",
)


CONTAMINATED_EXECUTION_ROOT_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    'execution_root = Path(os.environ["NXD_TRANSFORM_ROOT"])',
    'execution_root = Path(os.environ["NXD_TRANSFORM_ROOT"]) / Path.cwd()',
)


RELATIVE_RESOLVE_OPERAND_TRANSFORM = MODEL_ROOT_TRANSFORM.replace(
    "model_root = roots[label] / model",
    "model_root = roots[label] / Path(\".\").resolve()",
)


def _write_public_closure(root: Path, transform: str, readme: str) -> None:
    (root / "transform").mkdir(parents=True)
    (root / "data-orders/orders").mkdir(parents=True)
    (root / "data-users/users").mkdir(parents=True)
    (root / "spec.py").write_text("# transform-only labeled sources\n", encoding="utf-8")
    (root / "models.py").write_text("# orders and users\n", encoding="utf-8")
    (root / "infra-profile.yaml").write_text(
        "services:\n"
        "  - name: csv-source-orders\n"
        "  - name: csv-source-users\n",
        encoding="utf-8",
    )
    (root / "requirements.txt").write_text("dlt\n", encoding="utf-8")
    (root / "companion-files").write_text("data-orders\ndata-users\n", encoding="utf-8")
    (root / "README.md").write_text(readme, encoding="utf-8")
    (root / "csv-source-orders-path").write_text("data-orders\n", encoding="utf-8")
    (root / "csv-source-users-path").write_text("data-users\n", encoding="utf-8")
    (root / "transform/main.py").write_text(transform, encoding="utf-8")
    for label in ("orders", "users"):
        source = PUBLIC_FIXTURES / f"source-{label}/{label}/{label}.csv"
        target = root / f"data-{label}/{label}/{label}.csv"
        shutil.copy2(source, target)


def _run_public_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PUBLIC_CHECKER), "--fixtures", str(PUBLIC_FIXTURES),
         "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


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


def test_model_root_dataflow_is_pinned_for_both_checkers(tmp_path: Path) -> None:
    transform_path = tmp_path / "main.py"
    transform_path.write_text(MODEL_ROOT_TRANSFORM, encoding="utf-8")
    assert SUPERVISOR.transform_uses_pinned_roots(transform_path)

    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        MODEL_ROOT_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CHECKS PASSED" in result.stdout


def test_model_root_dataflow_rejects_one_unrooted_label(tmp_path: Path) -> None:
    transform_path = tmp_path / "main.py"
    transform_path.write_text(ONE_LABEL_UNROOTED_TRANSFORM, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(transform_path)

    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        ONE_LABEL_UNROOTED_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL transform-uses-pinned-root" in result.stdout


def test_model_root_dataflow_rejects_unrooted_reassignment_and_branch(
    tmp_path: Path,
) -> None:
    for index, transform in enumerate((
        REASSIGNED_UNROOTED_TRANSFORM,
        STATEMENT_BRANCH_UNROOTED_TRANSFORM,
    )):
        path = tmp_path / f"main-{index}.py"
        path.write_text(transform, encoding="utf-8")
        assert not SUPERVISOR.transform_uses_pinned_roots(path)
        closure = tmp_path / f"closure-{index}"
        _write_public_closure(
            closure,
            transform,
            "This closure requires a desktop supervisor with directory-companion support.\n",
        )
        result = _run_public_checker(closure)
        assert result.returncode != 0
        assert "FAIL transform-uses-pinned-root" in result.stdout


def test_model_root_dataflow_requires_a_reader_per_label(tmp_path: Path) -> None:
    path = tmp_path / "main.py"
    path.write_text(ONE_READER_FOR_BOTH_LABELS_TRANSFORM, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)
    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        ONE_READER_FOR_BOTH_LABELS_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL transform-uses-pinned-root" in result.stdout


def test_model_root_dataflow_rejects_ambiguous_reader_provenance(
    tmp_path: Path,
) -> None:
    path = tmp_path / "main.py"
    path.write_text(AMBIGUOUS_READER_TRANSFORM, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)
    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        AMBIGUOUS_READER_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL transform-uses-pinned-root" in result.stdout


def test_model_root_dataflow_rejects_subscript_reassignment(tmp_path: Path) -> None:
    path = tmp_path / "main.py"
    path.write_text(SUBSCRIPT_REASSIGNMENT_TRANSFORM, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)
    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        SUBSCRIPT_REASSIGNMENT_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL transform-uses-pinned-root" in result.stdout


def test_model_root_dataflow_rejects_mixed_name_and_subscript_provenance(
    tmp_path: Path,
) -> None:
    path = tmp_path / "main.py"
    path.write_text(MIXED_NAME_SUBSCRIPT_TRANSFORM, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)
    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        MIXED_NAME_SUBSCRIPT_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL transform-uses-pinned-root" in result.stdout


def test_model_root_dataflow_rejects_alias_subscript_reassignment(
    tmp_path: Path,
) -> None:
    path = tmp_path / "main.py"
    path.write_text(SUBSCRIPT_ALIAS_REASSIGNMENT_TRANSFORM, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)
    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        SUBSCRIPT_ALIAS_REASSIGNMENT_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL transform-uses-pinned-root" in result.stdout


def test_model_root_dataflow_rejects_unpinned_path_operand(tmp_path: Path) -> None:
    path = tmp_path / "main.py"
    path.write_text(UNPINNED_OPERAND_TRANSFORM, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)
    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        UNPINNED_OPERAND_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL transform-uses-pinned-root" in result.stdout


def test_model_root_dataflow_rejects_contaminated_execution_root(
    tmp_path: Path,
) -> None:
    path = tmp_path / "main.py"
    path.write_text(CONTAMINATED_EXECUTION_ROOT_TRANSFORM, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)
    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        CONTAMINATED_EXECUTION_ROOT_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL transform-uses-pinned-root" in result.stdout


def test_model_root_dataflow_rejects_relative_resolve_operand(
    tmp_path: Path,
) -> None:
    path = tmp_path / "main.py"
    path.write_text(RELATIVE_RESOLVE_OPERAND_TRANSFORM, encoding="utf-8")
    assert not SUPERVISOR.transform_uses_pinned_roots(path)
    closure = tmp_path / "closure"
    _write_public_closure(
        closure,
        RELATIVE_RESOLVE_OPERAND_TRANSFORM,
        "This closure requires a desktop supervisor with directory-companion support.\n",
    )
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL transform-uses-pinned-root" in result.stdout


def test_public_checker_requires_directory_companion_documentation(tmp_path: Path) -> None:
    closure = tmp_path / "closure"
    _write_public_closure(closure, MODEL_ROOT_TRANSFORM, "supervisor only\n")
    result = _run_public_checker(closure)
    assert result.returncode != 0
    assert "FAIL runtime-capability-documented" in result.stdout

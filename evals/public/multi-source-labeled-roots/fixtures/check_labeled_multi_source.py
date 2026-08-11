#!/usr/bin/env python3
"""Runner-side structural closure check for labeled CSV roots.

This intentionally models the directory-copy shape without invoking a live
desktop supervisor. Supervisor parser and refusal semantics belong to the
supervisor's own integration tests.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import shutil
import tempfile
from pathlib import Path


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{label}: {detail}" if detail else label)
    print(f"PASS {label}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def effective_manifest(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    return [line.strip() for line in raw.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def assert_no_symlinks(path: Path) -> None:
    check(f"no-symlinks:{path.name}", not path.is_symlink())
    for member in path.rglob("*"):
        check(f"no-symlinks:{member.relative_to(path)}", not member.is_symlink())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    fixtures = args.fixtures.resolve()

    required = ["spec.py", "models.py", "infra-profile.yaml",
                "transform/main.py", "requirements.txt", "companion-files",
                "README.md"]
    for rel in required:
        check(f"required:{rel}", (root / rel).is_file())

    manifest = root / "companion-files"
    declared = effective_manifest(manifest)
    expected = ["data-orders", "data-users"]
    check("manifest-exact-roots", declared == expected,
          f"expected {expected!r}, got {declared!r}")
    check("manifest-sorted-unique", declared == sorted(set(declared)))

    for entry in declared:
        rel = Path(entry)
        check(f"manifest-relative:{entry}", not rel.is_absolute() and
              rel.parts == (entry,) and not entry.endswith("/"))
        check(f"manifest-not-owned-root:{entry}", entry not in
              {"data", "transform", "contracts"})
        target = root / rel
        check(f"declared-directory:{entry}", target.is_dir() and
              not target.is_symlink())
        assert_no_symlinks(target)
        regular_files = [p for p in target.rglob("*") if p.is_file()]
        check(f"declared-tree-nonempty:{entry}", bool(regular_files))

    for left in declared:
        for right in declared:
            if left == right:
                continue
            left_parts = Path(left).parts
            right_parts = Path(right).parts
            check(f"no-overlap:{left}:{right}", not (
                left_parts[:len(right_parts)] == right_parts or
                right_parts[:len(left_parts)] == left_parts))

    expected_files = {
        "orders": ("orders", "orders.csv"),
        "users": ("users", "users.csv"),
    }
    for label, parts in expected_files.items():
        source = fixtures / f"source-{label}" / Path(*parts)
        output = root / f"data-{label}" / Path(*parts)
        check(f"source-preserved:{label}", source.is_file() and output.is_file())
        check(f"source-bytes-preserved:{label}", sha256(source) == sha256(output))

    empty_source = fixtures / "source-archive" / "archive" / "archive.csv"
    check("empty-source-is-empty", empty_source.read_text(encoding="utf-8").count("\n") == 1)
    check("empty-root-not-carried", not (root / "data-archive").exists())
    check("empty-root-not-declared", "data-archive" not in declared)
    check("empty-path-file-not-carried",
          not (root / "csv-source-archive-path").exists())
    profile = (root / "infra-profile.yaml").read_text(encoding="utf-8")
    spec = (root / "spec.py").read_text(encoding="utf-8")
    check("empty-profile-service-omitted", "csv-source-archive" not in profile)
    check("empty-spec-binding-omitted", "csv-source-archive" not in spec)

    for label in expected_files:
        path_file = root / f"csv-source-{label}-path"
        check(f"relative-path-file:{label}", path_file.is_file() and
              path_file.read_text(encoding="utf-8").strip() == f"data-{label}")

    transform = (root / "transform/main.py").read_text(encoding="utf-8")
    try:
        tree = ast.parse(transform, filename=str(root / "transform/main.py"))
    except SyntaxError as exc:
        fail(f"transform-python-syntax: {exc}")

    string_constants = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    def is_pinned_root_lookup(node: ast.AST) -> bool:
        if not isinstance(node, ast.Subscript):
            return False
        target = node.value
        if not (isinstance(target, ast.Attribute)
                and target.attr == "environ"
                and isinstance(target.value, ast.Name)
                and target.value.id == "os"):
            return False
        index = node.slice
        if isinstance(index, ast.Index):
            index = index.value
        return (isinstance(index, ast.Constant)
                and index.value == "NXD_TRANSFORM_ROOT")

    def contains_name(node: ast.AST, names: set[str]) -> bool:
        return any(isinstance(child, ast.Name) and child.id in names
                   for child in ast.walk(node))

    def assignment_names(node: ast.AST) -> set[str]:
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        return {target.id for target in targets if isinstance(target, ast.Name)}

    assignments = [node for node in ast.walk(tree)
                   if isinstance(node, (ast.Assign, ast.AnnAssign))]
    path_file_names = {
        f"csv-source-{label}-path" for label in expected_files
    }
    root_names: set[str] = set()
    for node in assignments:
        value = node.value
        if any(is_pinned_root_lookup(child) for child in ast.walk(value)):
            root_names.update(assignment_names(node))
    changed = True
    while changed:
        changed = False
        for node in assignments:
            value = node.value
            if contains_name(value, root_names):
                before = len(root_names)
                root_names.update(assignment_names(node))
                changed |= len(root_names) != before

    path_reader_functions: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        parameters = {arg.arg for arg in node.args.args}
        for child in ast.walk(node):
            if (isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "read_text"
                    and contains_name(child.func.value, parameters)):
                path_reader_functions.add(node.name)
                break

    path_derived_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in assignments:
            value = node.value
            has_path_reader = any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id in path_reader_functions
                for child in ast.walk(value)
            )
            has_direct_path_read = any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "read_text"
                and any(isinstance(grandchild, ast.Constant)
                        and grandchild.value in path_file_names
                        for grandchild in ast.walk(child))
                for child in ast.walk(value)
            )
            if (has_path_reader or has_direct_path_read
                    or contains_name(value, path_derived_names)):
                before = len(path_derived_names)
                path_derived_names.update(assignment_names(node))
                changed |= len(path_derived_names) != before

    def filesystem_bucket_uses_pinned_root() -> bool:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_filesystem = (
                isinstance(function, ast.Name) and function.id == "filesystem"
            ) or (
                isinstance(function, ast.Attribute) and function.attr == "filesystem"
            )
            if not is_filesystem:
                continue
            if any(keyword.arg == "bucket_url"
                   and contains_name(keyword.value, root_names)
                   for keyword in node.keywords
                   if keyword.value is not None):
                return True
        return False

    def has_pinned_root_lookup() -> bool:
        return any(is_pinned_root_lookup(node) for node in ast.walk(tree))

    def has_labeled_root_expression(label: str) -> bool:
        return f"csv-source-{label}-path" in string_constants

    def filesystem_bucket_uses_path_root() -> bool:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_filesystem = (
                isinstance(function, ast.Name) and function.id == "filesystem"
            ) or (
                isinstance(function, ast.Attribute) and function.attr == "filesystem"
            )
            if not is_filesystem:
                continue
            if any(keyword.arg == "bucket_url"
                   and contains_name(keyword.value, path_derived_names)
                   for keyword in node.keywords
                   if keyword.value is not None):
                return True
        return False

    check("transform-uses-pinned-root", has_pinned_root_lookup()
          and filesystem_bucket_uses_pinned_root()
          and filesystem_bucket_uses_path_root())
    for label in expected_files:
        check(f"transform-opens:{label}", has_labeled_root_expression(label))
    check("transform-does-not-open-empty-root", "data-archive" not in string_constants)

    manifest_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in assignments:
            value = node.value
            has_manifest_path = (
                any(isinstance(child, ast.Constant)
                    and child.value == "companion-files"
                    for child in ast.walk(value))
                or contains_name(value, manifest_names)
            )
            if has_manifest_path:
                before = len(manifest_names)
                manifest_names.update(assignment_names(node))
                changed |= len(manifest_names) != before

    def references_manifest_path(node: ast.AST) -> bool:
        return (contains_name(node, manifest_names)
                or any(isinstance(child, ast.Constant)
                       and child.value == "companion-files"
                       for child in ast.walk(node)))

    writes_manifest = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        method = function.attr if isinstance(function, ast.Attribute) else None
        if method in {"write_text", "write_bytes", "unlink", "rename", "replace"}:
            writes_manifest |= references_manifest_path(function.value)
        elif method == "open":
            mode_nodes = [node.args[0]] if node.args else []
            mode_nodes.extend(keyword.value for keyword in node.keywords
                              if keyword.arg == "mode")
            writes_manifest |= (
                references_manifest_path(function.value)
                and any(isinstance(mode, ast.Constant)
                        and isinstance(mode.value, str)
                        and set(mode.value) & {"w", "a", "x"}
                        for mode in mode_nodes)
            )
        elif isinstance(function, ast.Name) and function.id == "open":
            mode_nodes = [node.args[1]] if len(node.args) > 1 else []
            mode_nodes.extend(keyword.value for keyword in node.keywords
                              if keyword.arg == "mode")
            writes_manifest |= (
                bool(node.args) and references_manifest_path(node.args[0])
                and any(isinstance(mode, ast.Constant)
                        and isinstance(mode.value, str)
                        and set(mode.value) & {"w", "a", "x"}
                        for mode in mode_nodes)
            )
    check("transform-does-not-write-manifest", not writes_manifest)
    absolute_literals = {
        value for value in string_constants
        if value.startswith("/") and not value.startswith("//")
    }
    check("transform-no-absolute-path-literals", not absolute_literals,
          f"found {sorted(absolute_literals)!r}")

    readme = (root / "README.md").read_text(encoding="utf-8")
    check("runtime-floor-documented", all(marker in readme for marker in (
        "companion-directory-probe",
        "published=yes",
        "0.41.162",
        "da0b75bfc0eed5ae74b66fde35570bc40ed859b3",
    )))

    profile = (root / "infra-profile.yaml").read_text(encoding="utf-8")
    for label in expected_files:
        check(f"profile-label:{label}", f"csv-source-{label}" in profile)

    # Exercise a structural directory-copy model. This is deliberately not a
    # supervisor E2E; supervisor parser/refusal behavior is tested in nxd.
    with tempfile.TemporaryDirectory(prefix="labeled-roots-pin-") as tmp:
        snapshot = Path(tmp)
        shutil.copy2(manifest, snapshot / "companion-files")
        for entry in declared:
            shutil.copytree(root / entry, snapshot / entry)
        for entry in declared:
            check(f"pinned-root:{entry}", (snapshot / entry).is_dir())
            assert_no_symlinks(snapshot / entry)

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

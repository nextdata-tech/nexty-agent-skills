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
import unicodedata
from pathlib import Path


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{label}: {detail}" if detail else label)
    print(f"PASS {label}")


def check_input_binding(root: Path, spec: str, profile: str) -> None:
    """Keep transform-only labeled roots out of desktop input bindings."""
    tree = ast.parse(spec, filename=str(root / "spec.py"))
    bindings = {
        target.id: value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and isinstance(value := node.value, ast.Constant)
        and isinstance(value.value, str)
    }
    inputs = [node for node in ast.walk(tree)
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name)
              and node.func.id == "source_aligned_input"]
    sources = [node for node in ast.walk(tree)
               if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)
               and node.func.attr == "source"]
    if not inputs:
        return
    refs = []
    for node in sources:
        arg = node.args[0] if node.args else None
        refs.append(arg.value if isinstance(arg, ast.Constant)
                    else bindings.get(arg.id) if isinstance(arg, ast.Name)
                    else None)
    expected = "/infra-profile/desktop-local#/services/csv-source"
    check("source-aligned-unlabeled-csv",
          bool(refs) and all(ref == expected for ref in refs),
          f"got {refs!r}")
    check("source-aligned-csv-service-present",
          any(line.strip() == "- name: csv-source"
              for line in profile.splitlines()))
    check("source-aligned-csv-path-present",
          (root / "csv-source-path").is_file())


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
        if member.is_symlink():
            continue
        try:
            member.name.encode("utf-8")
            valid_utf8 = True
        except UnicodeEncodeError:
            valid_utf8 = False
        check(f"utf8-name:{member.relative_to(path)}", valid_utf8)
        check(
            f"nfc-name:{member.relative_to(path)}",
            unicodedata.normalize("NFC", member.name) == member.name,
        )
        check(
            f"regular-member:{member.relative_to(path)}",
            member.is_dir() or member.is_file(),
        )


def transform_writes_manifest(tree: ast.AST) -> bool:
    """Reject any transform-time mutation of the root manifest."""
    assignments = [node for node in ast.walk(tree)
                   if isinstance(node, (ast.Assign, ast.AnnAssign))]

    def assignment_names(node: ast.AST) -> set[str]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {target.id for target in targets if isinstance(target, ast.Name)}

    def contains_name(node: ast.AST, names: set[str]) -> bool:
        return any(isinstance(child, ast.Name) and child.id in names
                   for child in ast.walk(node))

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
        if method in {
            "write_text", "write_bytes", "touch", "unlink", "rename", "replace"
        }:
            writes_manifest |= references_manifest_path(function.value)
            if method in {"unlink", "rename", "replace"}:
                writes_manifest |= any(
                    references_manifest_path(argument) for argument in node.args
                )
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
        elif method in {"remove", "unlink"}:
            writes_manifest |= any(
                references_manifest_path(argument) for argument in node.args
            )
    return writes_manifest


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
    check("manifest-not-symlink", not manifest.is_symlink())
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
    models = (root / "models.py").read_text(encoding="utf-8")
    transform = (root / "transform/main.py").read_text(encoding="utf-8")
    check_input_binding(root, spec, profile)
    check("empty-profile-service-omitted", "csv-source-archive" not in profile)
    check("empty-spec-binding-omitted", "archive" not in spec)
    check("empty-model-omitted", "archive" not in models)
    check("empty-transform-reference-omitted",
          "data-archive" not in transform
          and "csv-source-archive-path" not in transform)

    for label in expected_files:
        path_file = root / f"csv-source-{label}-path"
        check(f"relative-path-file:{label}", path_file.is_file() and
              path_file.read_text(encoding="utf-8").strip() == f"data-{label}")

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

    def contains_text_read(node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "read_text"
            for child in ast.walk(node)
        )

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
        label: f"csv-source-{label}-path" for label in expected_files
    }
    root_names: set[str] = set()
    for node in assignments:
        value = node.value
        if (any(is_pinned_root_lookup(child) for child in ast.walk(value))
                and not contains_text_read(value)):
            root_names.update(assignment_names(node))
    changed = True
    while changed:
        changed = False
        for node in assignments:
            value = node.value
            if contains_name(value, root_names) and not contains_text_read(value):
                before = len(root_names)
                root_names.update(assignment_names(node))
                changed |= len(root_names) != before

    pinned_root_functions: set[str] = set()
    path_reader_functions: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        function_assignments = [child for child in ast.walk(node)
                                if isinstance(child, (ast.Assign, ast.AnnAssign))]
        function_root_names: set[str] = set()
        for assignment in function_assignments:
            if any(is_pinned_root_lookup(child)
                   for child in ast.walk(assignment.value)):
                function_root_names.update(assignment_names(assignment))
        changed = True
        while changed:
            changed = False
            for assignment in function_assignments:
                if contains_name(assignment.value, function_root_names):
                    before = len(function_root_names)
                    function_root_names.update(assignment_names(assignment))
                    changed |= len(function_root_names) != before
        returns_pinned_root = any(
            isinstance(child, ast.Return)
            and child.value is not None
            and (contains_name(child.value, function_root_names)
                 or any(is_pinned_root_lookup(grandchild)
                        for grandchild in ast.walk(child.value)))
            for child in ast.walk(node)
        )
        if returns_pinned_root:
            pinned_root_functions.add(node.name)
        parameters = {arg.arg for arg in node.args.args}
        parameter_derived_names = set(parameters)
        changed = True
        while changed:
            changed = False
            for assignment in function_assignments:
                if (contains_name(assignment.value, parameter_derived_names)
                        and not contains_text_read(assignment.value)):
                    before = len(parameter_derived_names)
                    parameter_derived_names.update(assignment_names(assignment))
                    changed |= len(parameter_derived_names) != before
        has_read_text = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "read_text"
            for statement in node.body
            for child in ast.walk(statement)
        )
        uses_parameter_in_read_receiver = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "read_text"
            and contains_name(child.func.value, parameter_derived_names)
            for statement in node.body
            for child in ast.walk(statement)
        )
        if has_read_text and uses_parameter_in_read_receiver:
            path_reader_functions.add(node.name)

    path_file_arg_names: dict[str, set[str]] = {label: set() for label in expected_files}
    path_derived_names: dict[str, set[str]] = {label: set() for label in expected_files}
    path_container_labels: dict[str, dict[str, set[str]]] = {}
    path_container_root_labels: dict[str, dict[str, set[str]]] = {}
    label_iterator_values: dict[str, set[str]] = {}
    iterator_bindings: dict[str, dict[int, set[str]]] = {}
    loop_path_bindings: dict[str, dict[str, str]] = {}
    constant_iterables: dict[str, list[ast.AST]] = {}
    for assignment in assignments:
        value = assignment.value
        if not isinstance(value, (ast.Tuple, ast.List)):
            continue
        items = [item for item in value.elts if isinstance(item, ast.Tuple)]
        if len(items) != len(value.elts):
            continue
        for name in assignment_names(assignment):
            constant_iterables[name] = items
    for node in ast.walk(tree):
        if not isinstance(node, ast.For) or not isinstance(node.target, ast.Tuple):
            continue
        if not node.target.elts or not isinstance(node.target.elts[0], ast.Name):
            continue
        items = (list(node.iter.elts) if isinstance(node.iter, (ast.Tuple, ast.List))
                 else constant_iterables.get(node.iter.id, [])
                 if isinstance(node.iter, ast.Name) else [])
        if not items:
            continue
        for item in items:
            if (isinstance(item, ast.Tuple) and item.elts
                    and all(isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                            for value in item.elts)):
                for index, value in enumerate(item.elts):
                    target = node.target.elts[index] if index < len(node.target.elts) else None
                    if isinstance(target, ast.Name):
                        iterator_bindings.setdefault(target.id, {}).setdefault(
                            index, set()
                        ).add(value.value)
                if (len(node.target.elts) > 1
                        and isinstance(node.target.elts[1], ast.Name)):
                    loop_path_bindings.setdefault(
                        node.target.elts[1].id, {}
                    )[item.elts[0].value] = item.elts[1].value
                if isinstance(item.elts[0].value, str):
                    label_iterator_values.setdefault(
                        node.target.elts[0].id, set()
                    ).add(item.elts[0].value)

    def has_label_path_reference(label: str) -> bool:
        path_file_name = path_file_names[label]
        if path_file_name in string_constants:
            return True
        for node in ast.walk(tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            literals = "".join(
                value.value for value in node.values
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            )
            if "csv-source-" not in literals or "-path" not in literals:
                continue
            if any(
                isinstance(value.value, ast.Name)
                and (value.value.id == "label"
                     or label in label_iterator_values.get(value.value.id, set()))
                for value in node.values
                if isinstance(value, ast.FormattedValue)
            ):
                return True
        return False

    def reads_label_path(candidate: ast.AST, label: str) -> bool:
        path_file_name = path_file_names[label]

        def contains_loop_path_name(node: ast.AST) -> bool:
            return any(
                isinstance(child, ast.Name)
                and loop_path_bindings.get(child.id, {}).get(label) == path_file_name
                for child in ast.walk(node)
            )

        def references_label_path(node: ast.AST) -> bool:
            return (contains_name(node, path_file_arg_names[label])
                    or contains_loop_path_name(node)
                    or any(isinstance(child, ast.Constant)
                           and child.value == path_file_name
                           for child in ast.walk(node)))

        def helper_argument_is_label_path(node: ast.AST) -> bool:
            return any(
                references_label_path(argument)
                or (isinstance(argument, ast.Name)
                    and label in label_iterator_values.get(argument.id, set()))
                or (isinstance(argument, ast.Constant)
                    and argument.value == label)
                for argument in node.args
            )

        def is_direct_read(node: ast.AST) -> bool:
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "read_text"):
                return (any(isinstance(child, ast.Constant)
                            and child.value == path_file_name
                            for child in ast.walk(node.func.value))
                        or references_label_path(node.func.value))
            if isinstance(node, ast.Attribute) and node.attr in {
                "strip", "lstrip", "rstrip", "decode"
            }:
                return is_direct_read(node.value)
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"strip", "lstrip", "rstrip", "decode"}):
                return is_direct_read(node.func.value)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                return (node.func.id in path_reader_functions
                        and helper_argument_is_label_path(node))
            return False

        def is_path_value(node: ast.AST) -> bool:
            if is_direct_read(node):
                return True
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
                return is_path_value(node.left) or is_path_value(node.right)
            if isinstance(node, ast.Call):
                function = node.func
                if (isinstance(function, ast.Name)
                        and function.id in {"Path", "str", "fspath"}):
                    return any(is_path_value(arg) for arg in node.args)
                if (isinstance(function, ast.Attribute)
                        and function.attr in {"join", "joinpath", "resolve", "absolute"}):
                    return is_path_value(function.value) or any(
                        is_path_value(arg) for arg in node.args
                    )
            if isinstance(node, ast.Attribute) and node.attr in {"parent", "name"}:
                return is_path_value(node.value)
            if isinstance(node, ast.JoinedStr):
                return any(is_path_value(value.value) for value in node.values
                           if isinstance(value, ast.FormattedValue))
            if isinstance(node, ast.IfExp):
                return is_path_value(node.body) and is_path_value(node.orelse)
            return False

        return is_path_value(candidate)

    def uses_path_value(node: ast.AST, names: set[str]) -> bool:
        if isinstance(node, ast.Name) and node.id in names:
            return True
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
            return uses_path_value(node.left, names) or uses_path_value(node.right, names)
        if isinstance(node, ast.Call):
            function = node.func
            if (isinstance(function, ast.Name)
                    and function.id in {"Path", "str", "fspath"}):
                return any(uses_path_value(arg, names) for arg in node.args)
            if (isinstance(function, ast.Attribute)
                    and function.attr in {"join", "joinpath", "resolve", "absolute"}):
                return (uses_path_value(function.value, names)
                        or any(uses_path_value(arg, names) for arg in node.args))
        if isinstance(node, ast.Attribute) and node.attr in {"parent", "name"}:
            return uses_path_value(node.value, names)
        if isinstance(node, ast.JoinedStr):
            return any(uses_path_value(value.value, names)
                       for value in node.values if isinstance(value, ast.FormattedValue))
        if isinstance(node, ast.IfExp):
            return (uses_path_value(node.body, names)
                    and uses_path_value(node.orelse, names))
        return False

    def has_label_container_access(
        candidate: ast.AST, label: str, roots: set[str] | None = None
    ) -> bool:
        for child in ast.walk(candidate):
            if not isinstance(child, ast.Subscript):
                continue
            if not isinstance(child.value, ast.Name):
                continue
            index = child.slice
            if isinstance(index, ast.Index):
                index = index.value
            if isinstance(index, ast.Constant) and isinstance(index.value, str):
                if (label in path_container_labels.get(child.value.id, {}).get(index.value, set())
                        and (roots is None
                             or child.value.id in roots
                             or label in path_container_root_labels.get(
                                 child.value.id, {}
                             ).get(index.value, set()))):
                    return True
            elif isinstance(index, ast.Name):
                for key, labels in path_container_labels.get(child.value.id, {}).items():
                    if (key == label and label in labels
                            and key in label_iterator_values.get(index.id, set())
                            and (roots is None
                                 or child.value.id in roots
                                 or key in path_container_root_labels.get(
                                     child.value.id, {}
                                 ).get(key, set()))):
                        return True
        return False

    def reader_matches_label(candidate: ast.AST, label: str) -> bool:
        subscripts = [
            child for child in ast.walk(candidate)
            if isinstance(child, ast.Subscript) and isinstance(child.value, ast.Name)
        ]
        if subscripts:
            key_matches = False
            for child in subscripts:
                index = child.slice
                if isinstance(index, ast.Index):
                    index = index.value
                if isinstance(index, ast.Constant) and index.value == label:
                    key_matches = True
                if isinstance(index, ast.Name):
                    keys = path_container_labels.get(child.value.id, {})
                    if (label in keys
                            and label in label_iterator_values.get(index.id, set())):
                        key_matches = True
            if not key_matches:
                return False
            container_literals = {
                child.slice.value for child in subscripts
                if isinstance(child.slice, ast.Constant)
                and isinstance(child.slice.value, str)
            }
            literal_labels = {
                child.value for child in ast.walk(candidate)
                if isinstance(child, ast.Constant) and child.value in expected_files
            }
            model_literals = literal_labels - container_literals
            iterator_label = any(
                label in values
                for child in ast.walk(candidate)
                if isinstance(child, ast.Name)
                for values in iterator_bindings.get(child.id, {}).values()
            )
            return not model_literals or label in model_literals or iterator_label
        if any(isinstance(child, ast.Constant) and child.value == label
               for child in ast.walk(candidate)):
            return True
        for child in ast.walk(candidate):
            if not isinstance(child, ast.Name):
                continue
            if any(label in values
                   for values in iterator_bindings.get(child.id, {}).values()):
                return True
        return False

    changed = True
    while changed:
        changed = False
        for node in assignments:
            value = node.value
            names = assignment_names(node)
            for label, path_file_name in path_file_names.items():
                if any(isinstance(child, ast.Constant)
                       and child.value == path_file_name
                       for child in ast.walk(value)):
                    before = len(path_file_arg_names[label])
                    path_file_arg_names[label].update(names)
                    changed |= len(path_file_arg_names[label]) != before

                if (reads_label_path(value, label)
                        or has_label_container_access(value, label)
                        or uses_path_value(value, path_derived_names[label])):
                    before = len(path_derived_names[label])
                    # A mapping containing several labeled roots must retain
                    # its key-level provenance; the subscript check below
                    # handles roots["orders"] / roots["users"] separately.
                    is_multi_label_dict = (
                        isinstance(value, ast.Dict)
                        and sum(
                            reads_label_path(item, label_name)
                            for label_name in expected_files
                            for item in value.values
                            if item is not None
                        ) > 1
                    )
                    if not is_multi_label_dict:
                        path_derived_names[label].update(names)
                    changed |= len(path_derived_names[label]) != before

                if isinstance(value, ast.Dict):
                    for key_node, item in zip(value.keys, value.values):
                        if (not isinstance(key_node, ast.Constant)
                                or not isinstance(key_node.value, str)
                                or item is None):
                            continue
                        for label_name in expected_files:
                            if reads_label_path(item, label_name):
                                for target_name in names:
                                    path_container_labels.setdefault(
                                        target_name, {}
                                    ).setdefault(key_node.value, set()).add(label_name)
                                    if contains_name(item, root_names):
                                        path_container_root_labels.setdefault(
                                            target_name, {}
                                        ).setdefault(key_node.value, set()).add(label_name)
                elif isinstance(value, ast.Name) and value.id in path_container_labels:
                    for target_name in names:
                        path_container_labels[target_name] = {
                            key: set(labels)
                            for key, labels in path_container_labels[value.id].items()
                        }
                        path_container_root_labels[target_name] = {
                            key: set(labels)
                            for key, labels in path_container_root_labels.get(
                                value.id, {}
                            ).items()
                        }

            for function_call in ast.walk(value):
                if (isinstance(function_call, ast.Call)
                        and isinstance(function_call.func, ast.Name)
                        and (function_call.func.id in pinned_root_functions
                             or (function_call.func.id in path_reader_functions
                                 and contains_name(function_call, root_names)))):
                    root_names.update(names)

    def preserves_pinned_root(value: ast.AST) -> bool:
        if contains_text_read(value):
            return False
        return (
            any(is_pinned_root_lookup(child) for child in ast.walk(value))
            or contains_name(value, root_names)
            or any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id in pinned_root_functions
                for child in ast.walk(value)
            )
        )

    invalidated_root_names = {
        name
        for node in assignments
        for name in assignment_names(node)
        if name in root_names and not preserves_pinned_root(node.value)
    }
    conditional_root_names = {
        name
        for node in assignments
        for name in assignment_names(node)
        if name in root_names
        and any(isinstance(child, ast.IfExp) for child in ast.walk(node.value))
    }
    valid_root_names = root_names - invalidated_root_names - conditional_root_names

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
                   and (contains_name(keyword.value, valid_root_names)
                        or any(
                                has_label_container_access(
                                    keyword.value, label, valid_root_names
                            )
                            for label in expected_files
                        ))
                   for keyword in node.keywords
                   if keyword.value is not None):
                return True
        return False

    def has_pinned_root_lookup() -> bool:
        return any(is_pinned_root_lookup(node) for node in ast.walk(tree))

    def filesystem_bucket_uses_path_root(label: str) -> bool:
        path_file_name = path_file_names[label]
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
                   and reader_matches_label(keyword.value, label)
                   and (contains_name(keyword.value, valid_root_names)
                        or has_label_container_access(
                            keyword.value, label, valid_root_names
                        ))
                   and (uses_path_value(keyword.value, path_derived_names[label])
                        or has_label_container_access(
                            keyword.value, label, valid_root_names
                        )
                        or reads_label_path(keyword.value, label))
                   for keyword in node.keywords
                   if keyword.value is not None):
                return True
        return False

    check("transform-uses-pinned-root", has_pinned_root_lookup()
          and filesystem_bucket_uses_pinned_root()
          and all(filesystem_bucket_uses_path_root(label)
                  for label in expected_files))
    for label in expected_files:
        check(f"transform-opens:{label}", has_label_path_reference(label))
    check("transform-does-not-open-empty-root", "data-archive" not in string_constants)

    check("transform-does-not-write-manifest",
          not transform_writes_manifest(tree))
    absolute_literals = {
        value for value in string_constants
        if value.startswith("/") and not value.startswith("//")
    }
    check("transform-no-absolute-path-literals", not absolute_literals,
          f"found {sorted(absolute_literals)!r}")
    check("transform-no-authoring-absolute-path", str(root) not in transform)

    readme = (root / "README.md").read_text(encoding="utf-8")
    check("runtime-capability-documented", all(marker in readme for marker in (
        "directory-companion",
        "supervisor",
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

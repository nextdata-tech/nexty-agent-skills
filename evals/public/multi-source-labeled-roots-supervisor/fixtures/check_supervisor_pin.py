#!/usr/bin/env python3
"""Opt-in live supervisor check for the labeled CSV closure.

The ordinary public scenario checks the closure contract without a runtime.
This checker is deliberately separate: when run with the desktop harness it
builds the landed closure through the real supervisor and verifies the rows
that can only exist if the declared directory trees were pinned and opened by
the transform.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import os
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))

from loop_unroll import unroll_literal_loops  # noqa: E402


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


def supervisor() -> Path:
    configured = os.environ.get("EVAL_DESKTOP_SUPERVISOR_DIR", "").strip()
    if configured:
        candidate = Path(configured).expanduser() / "nxd-desktop-supervisor"
        if candidate.is_file():
            return candidate
    found = shutil.which("nxd-desktop-supervisor")
    if found:
        return Path(found)
    fail("supervisor-not-found")


def build_env() -> dict[str, str]:
    env = dict(os.environ)
    python = os.environ.get("EVAL_DESKTOP_PYTHON", "").strip()
    if python:
        env.setdefault("NXD_DESKTOP_PYTHON", python)
    return env


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def effective_manifest(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def source_rows(fixtures: Path, label: str) -> list[tuple[str, object]]:
    path = fixtures / f"source-{label}" / label / f"{label}.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if label == "orders":
        return [(row["order_id"], Decimal(row["amount"])) for row in rows]
    return [(row["user_id"], row["region"]) for row in rows]


def transform_uses_pinned_roots(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    # Same reasoning as the public checker: root-ness propagates through
    # assignments, so a `for` target would be invisible to it. See
    # evals/tools/loop_unroll.py.
    tree = unroll_literal_loops(tree)

    def is_root_lookup(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "environ"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "os"
            and isinstance(node.slice, ast.Constant)
            and node.slice.value == "NXD_TRANSFORM_ROOT"
        )

    has_root_lookup = any(
        is_root_lookup(node)
        for node in ast.walk(tree)
    )
    constants = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assignments = [node for node in ast.walk(tree)
                   if isinstance(node, (ast.Assign, ast.AnnAssign))]
    path_file_names = {
        label: f"csv-source-{label}-path" for label in ("orders", "users")
    }

    def assignment_names(node: ast.AST) -> set[str]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {target.id for target in targets if isinstance(target, ast.Name)}

    def assignment_subscript_containers(node: ast.AST) -> set[str]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {
            target.value.id
            for target in targets
            if isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
        }

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

    def contains_unpinned_path(
        node: ast.AST, trusted_names: set[str] | None = None
    ) -> bool:
        trusted_names = trusted_names or set()

        def has_trusted_path_argument(call: ast.Call) -> bool:
            return any(
                contains_name(argument, trusted_names)
                or any(
                    is_root_lookup(descendant)
                    for descendant in ast.walk(argument)
                )
                for argument in call.args
            )

        return any(
            isinstance(child, ast.Call)
            and (
                (isinstance(child.func, ast.Attribute)
                 and child.func.attr in {"abspath", "realpath", "cwd", "getcwd"}
                 and not (
                     child.func.attr in {"abspath", "realpath"}
                     and has_trusted_path_argument(child)
                 ))
                or (isinstance(child.func, ast.Attribute)
                    and child.func.attr in {
                        "absolute", "expanduser", "home", "resolve"
                    }
                    and not (
                        contains_name(child.func.value, trusted_names)
                        or any(
                            is_root_lookup(grandchild)
                            for grandchild in ast.walk(child.func.value)
                        )
                    ))
                or (isinstance(child.func, ast.Name)
                    and child.func.id in {
                        "abspath", "realpath", "expanduser", "getcwd"
                    }
                    and not (
                        child.func.id in {"abspath", "realpath", "expanduser"}
                        and has_trusted_path_argument(child)
                    ))
            )
            for child in ast.walk(node)
        )

    root_names: set[str] = set()
    for node in assignments:
        if (any(is_root_lookup(child) for child in ast.walk(node.value))
                and not contains_text_read(node.value)
                and not contains_unpinned_path(node.value, root_names)):
            root_names.update(assignment_names(node))
    changed = True
    while changed:
        changed = False
        for node in assignments:
            if (contains_name(node.value, root_names)
                    and not contains_text_read(node.value)
                    and not contains_unpinned_path(node.value, root_names)):
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
            if (any(is_root_lookup(child) for child in ast.walk(assignment.value))
                    and not contains_unpinned_path(
                        assignment.value, function_root_names
                    )):
                function_root_names.update(assignment_names(assignment))
        changed = True
        while changed:
            changed = False
            for assignment in function_assignments:
                if (contains_name(assignment.value, function_root_names)
                        and not contains_unpinned_path(
                            assignment.value, function_root_names
                        )):
                    before = len(function_root_names)
                    function_root_names.update(assignment_names(assignment))
                    changed |= len(function_root_names) != before
        returns_pinned_root = any(
            isinstance(child, ast.Return)
            and child.value is not None
            and (contains_name(child.value, function_root_names)
                 or any(is_root_lookup(grandchild)
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

    path_file_arg_names: dict[str, set[str]] = {label: set() for label in path_file_names}
    path_derived_names: dict[str, set[str]] = {label: set() for label in path_file_names}
    path_definition_labels: dict[tuple[int, str], set[str]] = {}
    poisoned_container_names: set[str] = set()
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
        if path_file_name in constants:
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
            if not isinstance(child, ast.Subscript) or not isinstance(child.value, ast.Name):
                continue
            index = child.slice
            if isinstance(index, ast.Index):
                index = index.value
            if isinstance(index, ast.Constant) and isinstance(index.value, str):
                if (label in path_container_labels.get(child.value.id, {}).get(index.value, set())
                        and child.value.id not in poisoned_container_names
                        and (roots is None
                             or child.value.id in roots
                             or label in path_container_root_labels.get(
                                 child.value.id, {}
                             ).get(index.value, set()))):
                    return True
            elif isinstance(index, ast.Name):
                for key, labels in path_container_labels.get(child.value.id, {}).items():
                    if (key == label and label in labels
                            and child.value.id not in poisoned_container_names
                            and key in label_iterator_values.get(index.id, set())
                            and (roots is None
                                 or child.value.id in roots
                                 or key in path_container_root_labels.get(
                                     child.value.id, {}
                                 ).get(key, set()))):
                        return True
        return False

    node_order: dict[int, int] = {}
    node_scope: dict[int, ast.AST | None] = {}

    def index_nodes(node: ast.AST, scope: ast.AST | None = None) -> None:
        current_scope = node if isinstance(node, ast.FunctionDef) else scope
        node_order[id(node)] = len(node_order)
        node_scope[id(node)] = current_scope
        for child in ast.iter_child_nodes(node):
            index_nodes(child, current_scope)

    index_nodes(tree)

    def reaching_definition_matches_label(
        name: str, label: str, reference: ast.AST
    ) -> bool:
        reference_order = node_order.get(id(reference), -1)
        scope = node_scope.get(id(reference))
        definitions = [
            assignment for assignment in assignments
            if name in assignment_names(assignment)
            and node_scope.get(id(assignment)) is scope
            and node_order.get(id(assignment), -1) < reference_order
        ]
        if not definitions and scope is not None:
            definitions = [
                assignment for assignment in assignments
                if name in assignment_names(assignment)
                and node_scope.get(id(assignment)) is None
                and node_order.get(id(assignment), -1) < reference_order
            ]
        if not definitions:
            return False
        reaching = max(definitions, key=lambda assignment: node_order[id(assignment)])
        if any(
            isinstance(child, ast.Subscript)
            and isinstance(child.value, ast.Name)
            and child.value.id in poisoned_container_names
            for child in ast.walk(reaching.value)
        ):
            return False
        if contains_unpinned_path(reaching.value, root_names):
            return False
        return label in path_definition_labels.get((id(reaching), name), set())

    def reader_matches_label(
        candidate: ast.AST, label: str, reference: ast.AST
    ) -> bool:
        reaching_labels = {
            candidate_label
            for child in ast.walk(candidate)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
            for candidate_label in path_file_names
            if reaching_definition_matches_label(child.id, candidate_label, reference)
        }
        subscripts = [
            child for child in ast.walk(candidate)
            if isinstance(child, ast.Subscript) and isinstance(child.value, ast.Name)
        ]
        if subscripts:
            key_matches = False
            subscript_labels: set[str] = set()
            for child in subscripts:
                index = child.slice
                if isinstance(index, ast.Index):
                    index = index.value
                if (isinstance(index, ast.Constant)
                        and child.value.id not in poisoned_container_names):
                    if index.value == label:
                        key_matches = True
                    if index.value in path_file_names:
                        subscript_labels.add(index.value)
                if isinstance(index, ast.Name):
                    keys = path_container_labels.get(child.value.id, {})
                    if (child.value.id not in poisoned_container_names
                            and label in keys
                            and label in label_iterator_values.get(index.id, set())):
                        key_matches = True
                    if child.value.id not in poisoned_container_names:
                        subscript_labels.update(
                            key_name for key_name in keys
                            if key_name in label_iterator_values.get(index.id, set())
                        )
            if subscript_labels:
                return ((not reaching_labels or reaching_labels == {label})
                        and subscript_labels == {label})
            if reaching_labels:
                return reaching_labels == {label}
            if not key_matches:
                return False
            container_literals = {
                child.slice.value for child in subscripts
                if isinstance(child.slice, ast.Constant)
                and isinstance(child.slice.value, str)
            }
            literal_labels = {
                child.value for child in ast.walk(candidate)
                if isinstance(child, ast.Constant) and child.value in path_file_names
            }
            model_literals = literal_labels - container_literals
            iterator_label = any(
                label in values
                for child in ast.walk(candidate)
                if isinstance(child, ast.Name)
                for values in iterator_bindings.get(child.id, {}).values()
            )
            return not model_literals or label in model_literals or iterator_label
        if reaching_labels:
            return reaching_labels == {label}
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
            names = assignment_names(node)
            for label, path_file_name in path_file_names.items():
                if any(isinstance(child, ast.Constant)
                       and child.value == path_file_name
                       for child in ast.walk(node.value)):
                    before = len(path_file_arg_names[label])
                    path_file_arg_names[label].update(names)
                    changed |= len(path_file_arg_names[label]) != before

                if (reads_label_path(node.value, label)
                        or has_label_container_access(node.value, label, root_names)
                        or uses_path_value(node.value, path_derived_names[label])):
                    before = len(path_derived_names[label])
                    is_multi_label_dict = (
                        isinstance(node.value, ast.Dict)
                        and sum(
                            reads_label_path(item, label_name)
                            for label_name in path_file_names
                            for item in node.value.values
                            if item is not None
                        ) > 1
                    )
                    if not is_multi_label_dict:
                        path_derived_names[label].update(names)
                        for name in names:
                            path_definition_labels.setdefault(
                                (id(node), name), set()
                            ).add(label)
                    changed |= len(path_derived_names[label]) != before

                if isinstance(node.value, ast.Dict):
                    for key_node, item in zip(node.value.keys, node.value.values):
                        if (not isinstance(key_node, ast.Constant)
                                or not isinstance(key_node.value, str)
                                or item is None):
                            continue
                        for label_name in path_file_names:
                            if reads_label_path(item, label_name):
                                for target_name in names:
                                    path_container_labels.setdefault(
                                        target_name, {}
                                    ).setdefault(key_node.value, set()).add(label_name)
                                    if contains_name(item, root_names):
                                        path_container_root_labels.setdefault(
                                            target_name, {}
                                        ).setdefault(key_node.value, set()).add(label_name)
                elif isinstance(node.value, ast.Name) and node.value.id in path_container_labels:
                    for target_name in names:
                        path_container_labels[target_name] = {
                            key: set(labels)
                            for key, labels in path_container_labels[node.value.id].items()
                        }
                        path_container_root_labels[target_name] = {
                            key: set(labels)
                            for key, labels in path_container_root_labels.get(
                                node.value.id, {}
                            ).items()
                        }

            for function_call in ast.walk(node.value):
                if (isinstance(function_call, ast.Call)
                        and isinstance(function_call.func, ast.Name)
                        and (function_call.func.id in pinned_root_functions
                             or (function_call.func.id in path_reader_functions
                                 and contains_name(function_call, root_names)))):
                    root_names.update(names)

    poisoned_container_names.update(
        container
        for node in assignments
        for container in assignment_subscript_containers(node)
        if container in path_container_labels
    )
    changed = True
    while changed:
        changed = False
        for node in assignments:
            names = assignment_names(node)
            if not isinstance(node.value, ast.Name):
                continue
            source = node.value.id
            if source not in path_container_labels:
                continue
            for name in names:
                if name not in path_container_labels:
                    continue
                if ((source in poisoned_container_names
                     or name in poisoned_container_names)
                        and (source not in poisoned_container_names
                             or name not in poisoned_container_names)):
                    poisoned_container_names.update({source, name})
                    changed = True

    def preserves_pinned_root(value: ast.AST) -> bool:
        if contains_text_read(value):
            return False
        return (
            any(is_root_lookup(child) for child in ast.walk(value))
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
    conditional_path_names = {
        label: {
            name
            for node in assignments
            for name in assignment_names(node)
            if name in path_derived_names[label]
            and any(isinstance(child, ast.IfExp) for child in ast.walk(node.value))
        }
        for label in path_file_names
    }
    valid_path_names = {
        label: path_derived_names[label] - conditional_path_names[label]
        for label in path_file_names
    }
    poisoned_path_names = {
        name
        for node in assignments
        for name in assignment_names(node)
        if name in set().union(*path_derived_names.values())
        and (not path_definition_labels.get((id(node), name), set())
             or contains_unpinned_path(node.value, root_names))
    }
    valid_path_names = {
        label: names - poisoned_path_names
        for label, names in valid_path_names.items()
    }

    def uses_root_in_reader(label: str) -> bool:
        path_file_name = path_file_names[label]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            is_filesystem = (
                isinstance(node.func, ast.Name) and node.func.id == "filesystem"
            ) or (
                isinstance(node.func, ast.Attribute) and node.func.attr == "filesystem"
            )
            if not is_filesystem:
                continue
            for keyword in node.keywords:
                if keyword.arg != "bucket_url" or keyword.value is None:
                    continue
                if not reader_matches_label(keyword.value, label, node):
                    continue
                if any(isinstance(child, ast.IfExp)
                       for child in ast.walk(keyword.value)):
                    continue
                if contains_unpinned_path(keyword.value, root_names):
                    continue
                if ((contains_name(keyword.value, valid_root_names)
                     or contains_name(keyword.value, valid_path_names[label])
                     or has_label_container_access(
                         keyword.value, label, valid_root_names
                     ))
                        and (uses_path_value(
                            keyword.value, valid_path_names[label]
                        )
                        or has_label_container_access(
                            keyword.value, label, valid_root_names
                        )
                        or reads_label_path(keyword.value, label))):
                    return True
        return False

    return has_root_lookup and all(
        has_label_path_reference(label) and uses_root_in_reader(label)
        for label in ("orders", "users")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    fixtures = args.fixtures.resolve()

    root = args.root.resolve()
    supervisor_bin = supervisor()
    data_dir = root / ".desktop-check-tmp" / "labeled-roots-supervisor"
    data_dir.mkdir(parents=True, exist_ok=True)
    workflow = "labeled-orders-users-supervisor"
    command = [
        str(supervisor_bin), "create",
        "--data-dir", str(data_dir),
        "--definition", str(root),
        "--workflow", workflow,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            env=build_env(),
        )
        detail = (result.stderr.strip() or result.stdout.strip() or "(no output)")
        check("supervisor-create", result.returncode == 0, detail[-2000:])
        check("supervisor-published", "published=yes" in result.stdout,
              result.stdout[-2000:])

        declared = effective_manifest(root / "companion-files")
        check("closure-manifest", declared == ["data-orders", "data-users"],
              f"got {declared!r}")
        check("closure-empty-root-omitted", not (root / "data-archive").exists())
        check("closure-empty-path-file-omitted",
              not (root / "csv-source-archive-path").exists())
        profile = (root / "infra-profile.yaml").read_text(encoding="utf-8")
        spec = (root / "spec.py").read_text(encoding="utf-8")
        models = (root / "models.py").read_text(encoding="utf-8")
        transform = (root / "transform/main.py").read_text(encoding="utf-8")
        check_input_binding(root, spec, profile)
        check("closure-empty-profile-service-omitted",
              "csv-source-archive" not in profile)
        check("closure-empty-spec-binding-omitted",
              "archive" not in spec)
        check("closure-empty-model-omitted", "archive" not in models)
        check("closure-empty-transform-reference-omitted",
              "data-archive" not in transform
              and "csv-source-archive-path" not in transform)
        check("transform-pinned-roots",
              transform_uses_pinned_roots(root / "transform/main.py"))
        for label in ("orders", "users"):
            source = fixtures / f"source-{label}" / label / f"{label}.csv"
            closure_file = root / f"data-{label}" / label / f"{label}.csv"
            check(f"closure-bytes:{label}",
                  sha256(source) == sha256(closure_file))

        databases = sorted(data_dir.glob("generations/*/data.duckdb"))
        check("published-database", len(databases) == 1,
              f"found {[str(path) for path in databases]!r}")
        if len(databases) != 1:
            return
        definitions = data_dir / "definitions" / "sha256-v1"
        snapshots = sorted(
            path for path in definitions.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ) if definitions.is_dir() else []
        check("pinned-snapshot", len(snapshots) == 1,
              f"found {[str(path) for path in snapshots]!r}")
        if len(snapshots) != 1:
            return
        snapshot = snapshots[0]
        check("pinned-manifest",
              effective_manifest(snapshot / "companion-files") == declared)
        check("pinned-empty-root-omitted", not (snapshot / "data-archive").exists())
        check("pinned-empty-path-file-omitted",
              not (snapshot / "csv-source-archive-path").exists())
        pinned_profile = (snapshot / "infra-profile.yaml").read_text(encoding="utf-8")
        pinned_spec = (snapshot / "spec.py").read_text(encoding="utf-8")
        pinned_models = (snapshot / "models.py").read_text(encoding="utf-8")
        check("pinned-empty-profile-service-omitted",
              "csv-source-archive" not in pinned_profile)
        check("pinned-empty-spec-binding-omitted", "archive" not in pinned_spec)
        check("pinned-empty-model-omitted", "archive" not in pinned_models)
        check("pinned-transform-no-authoring-absolute-path",
              str(root) not in (snapshot / "transform/main.py").read_text(encoding="utf-8"))
        for label in ("orders", "users"):
            source = fixtures / f"source-{label}" / label / f"{label}.csv"
            pinned_file = snapshot / f"data-{label}" / label / f"{label}.csv"
            check(f"pinned-bytes:{label}", sha256(source) == sha256(pinned_file))

        connection = duckdb.connect(str(databases[0]), read_only=True)
        try:
            tables = {
                row[0] for row in connection.execute("SHOW TABLES").fetchall()
            }
            check("published-model-set", tables == {"orders", "users"},
                  f"got {sorted(tables)!r}")
            orders = connection.execute(
                'SELECT order_id, amount FROM "orders" ORDER BY order_id'
            ).fetchall()
            users = connection.execute(
                'SELECT user_id, region FROM "users" ORDER BY user_id'
            ).fetchall()
            check("pinned-rows:orders", orders == source_rows(fixtures, "orders"),
                  f"got {orders!r}")
            check("pinned-rows:users", users == source_rows(fixtures, "users"),
                  f"got {users!r}")
        finally:
            connection.close()
    except subprocess.TimeoutExpired:
        fail("supervisor-create-timeout")
    finally:
        try:
            subprocess.run(
                [str(supervisor_bin), "stop", "--data-dir", str(data_dir)],
                capture_output=True,
                text=True,
                timeout=30,
                env=build_env(),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        shutil.rmtree(data_dir, ignore_errors=True)

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

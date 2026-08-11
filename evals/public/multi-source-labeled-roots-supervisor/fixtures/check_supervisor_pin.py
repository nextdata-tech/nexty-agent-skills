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
from decimal import Decimal
from pathlib import Path

import duckdb


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{label}: {detail}" if detail else label)
    print(f"PASS {label}")


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

    def assignment_names(node: ast.AST) -> set[str]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {target.id for target in targets if isinstance(target, ast.Name)}

    def contains_name(node: ast.AST, names: set[str]) -> bool:
        return any(isinstance(child, ast.Name) and child.id in names
                   for child in ast.walk(node))

    root_names: set[str] = set()
    for node in assignments:
        if any(
            is_root_lookup(child)
            for child in ast.walk(node.value)
        ):
            root_names.update(assignment_names(node))
    changed = True
    while changed:
        changed = False
        for node in assignments:
            if contains_name(node.value, root_names):
                before = len(root_names)
                root_names.update(assignment_names(node))
                changed |= len(root_names) != before

    uses_root_in_reader = any(
        isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name) and node.func.id == "filesystem"
            or isinstance(node.func, ast.Attribute) and node.func.attr == "filesystem"
        )
        and any(keyword.arg == "bucket_url"
                and contains_name(keyword.value, root_names)
                for keyword in node.keywords if keyword.value is not None)
        for node in ast.walk(tree)
    )
    return has_root_lookup and uses_root_in_reader and all(
        f"csv-source-{label}-path" in constants or f"data-{label}" in constants
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
        for label in ("orders", "users"):
            source = fixtures / f"source-{label}" / label / f"{label}.csv"
            pinned_file = snapshot / f"data-{label}" / label / f"{label}.csv"
            check(f"pinned-bytes:{label}", sha256(source) == sha256(pinned_file))

        connection = duckdb.connect(str(databases[0]), read_only=True)
        try:
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

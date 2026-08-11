#!/usr/bin/env python3
"""Runner-side structural and pin-copy check for labeled CSV roots."""

from __future__ import annotations

import argparse
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
                "transform/main.py", "requirements.txt", "companion-files"]
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

    for label in expected_files:
        path_file = root / f"csv-source-{label}-path"
        check(f"relative-path-file:{label}", path_file.is_file() and
              path_file.read_text(encoding="utf-8").strip() == f"data-{label}")

    transform = (root / "transform/main.py").read_text(encoding="utf-8")
    check("transform-uses-pinned-root", "NXD_TRANSFORM_ROOT" in transform)
    for label in expected_files:
        # Accept either explicit roots or the documented `f"data-{label}"`
        # loop; both preserve the label-specific path at runtime.
        uses_label = label in transform and ("data-" in transform or
                                             f"data-{label}" in transform)
        check(f"transform-opens:{label}", uses_label)
    check("transform-does-not-open-empty-root", "data-archive" not in transform)
    check("transform-does-not-write-manifest", "write_text" not in transform or
          "companion-files" not in transform)
    check("transform-no-fixture-absolute-path", str(fixtures) not in transform)

    profile = (root / "infra-profile.yaml").read_text(encoding="utf-8")
    for label in expected_files:
        check(f"profile-label:{label}", f"csv-source-{label}" in profile)

    # Exercise the same directory-copy shape the supervisor uses: the manifest
    # must be sufficient to reproduce both roots at their declared paths.
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

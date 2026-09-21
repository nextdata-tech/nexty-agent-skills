"""Runner-side static contract checks for the Google Drive source eval."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from api_connector_gate import (  # noqa: E402
    find_closure,
    profile_attributes,
    string_literals,
    transform_sources,
)


HTTP_CALL_NAMES = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "urlopen",
    "request",
    "send",
}


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{label}: {detail}" if detail else label)
    print(f"PASS {label}")


def parse_sources(root: Path) -> list[ast.Module]:
    modules: list[ast.Module] = []
    for path in transform_sources(root):
        try:
            modules.append(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        except SyntaxError as exc:
            fail(f"source-parses: {path.name}: {exc}")
    return modules


def called_names(modules: list[ast.Module]) -> set[str]:
    names: set[str] = set()
    for module in modules:
        for node in ast.walk(module):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    names.add(node.func.attr)
    return names


def imported_modules(modules: list[ast.Module]) -> set[str]:
    modules_seen: set[str] = set()
    for module in modules:
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                modules_seen.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules_seen.add(node.module)
    return modules_seen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--secret-marker-file", type=Path, required=True)
    args = parser.parse_args()

    root = find_closure(args.root)
    token = args.secret_marker_file.read_text(encoding="utf-8").strip()
    required = (
        "spec.py",
        "models.py",
        "infra-profile.yaml",
        "transform/main.py",
        "connectivity_check.py",
        "requirements.txt",
        "README.md",
        ".gitignore",
        "SENSITIVE",
    )
    for rel in required:
        check(f"file:{rel}", (root / rel).is_file())

    fields, public = profile_attributes(root)
    check("profile:source-kind", fields.get("source_kind") == "google_drive_files")
    check("profile:base-url", fields.get("base_url") == "https://www.googleapis.com/drive/v3")
    check("profile:folder", fields.get("drive_folder_id") == "folder_eval_42")
    check("profile:query", "trashed = false" in fields.get("drive_query", ""))
    check("profile:mime-filter", fields.get("drive_file_mime_type") == "text/csv")
    check("profile:bearer-auth", fields.get("auth_type") == "bearer")
    check("profile:synthetic-token", fields.get("auth_token") == token)
    check("profile:token-private", public.get("auth_token") == "false")
    check("sensitivity:gitignore", "infra-profile.yaml" in (root / ".gitignore").read_text(encoding="utf-8"))
    check("sensitivity:marker", "auth_token" in (root / "SENSITIVE").read_text(encoding="utf-8"))

    modules = parse_sources(root)
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in transform_sources(root)
    )
    imports = imported_modules(modules)
    calls = called_names(modules)
    literals = [literal for module in modules for literal in string_literals(module)]
    check("client:google-api", any(name.startswith("googleapiclient") for name in imports))
    check("client:build", "build" in calls)
    check("client:files-list", "files" in text and "list" in text)
    check("client:file-download", "get_media" in text or "export_media" in text)
    check("pagination:next-page-token", "nextPageToken" in text)
    check("filter:csv", "mimeType" in text or "drive_file_mime_type" in text)
    check("filter:folder", "drive_folder_id" in text or "drive_query" in text)
    check("rows:csv-reader", "DictReader" in text)
    check("rows:dlt-resource", "resource" in text and "dlt" in text)
    check("desktop:duckdb-pipeline", "DuckDbOutput" in text and "pipeline" in text and "pipeline.run" in text)
    check("rows:lineage", all(field in text for field in (
        "_drive_file_id", "_drive_file_name", "_drive_modified_time"
    )))
    check("auth:flat-token", "auth_token" in text and "secrets" in text)
    check("source:token-not-in-code", token not in literals)
    leaked = []
    for path in root.rglob("*"):
        # source-contract.yaml is runner-supplied input and intentionally carries
        # the synthetic token; only generated closure files belong in this scan.
        if not path.is_file() or path.name in {"infra-profile.yaml", "source-contract.yaml"}:
            continue
        if token in path.read_text(encoding="utf-8", errors="replace"):
            leaked.append(str(path.relative_to(root)))
    check("source:token-only-in-profile", not leaked, ", ".join(leaked))
    forbidden = {
        "requests",
        "httpx",
        "aiohttp",
        "urllib.request",
        "httplib2",
    }
    check("source:no-hand-rolled-http", not any(
        module in imports or any(module + "." in imported for imported in imports)
        for module in forbidden
    ))
    lowered = text.lower()
    check("source:read-only", not any(
        marker in lowered for marker in ("permissions().create", "permissions().update", "files().delete", "files().create")
    ))
    check("probe:present", (root / "connectivity_check.py").stat().st_size > 0)
    check("probe:does-not-carry-token", token not in (root / "connectivity_check.py").read_text(encoding="utf-8"))
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Runner-side static contract checks for the Google Sheets source eval."""

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


def imported_modules(modules: list[ast.Module]) -> set[str]:
    modules_seen: set[str] = set()
    for module in modules:
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                modules_seen.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules_seen.add(node.module)
    return modules_seen


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


def call_lines(modules: list[ast.Module], names: set[str]) -> list[int]:
    lines: list[int] = []
    for module in modules:
        for node in ast.walk(module):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if name in names:
                lines.append(node.lineno)
    return lines


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
    check("profile:source-kind", fields.get("source_kind") == "google_sheets")
    check("profile:base-url", fields.get("base_url") == "https://sheets.googleapis.com/v4")
    check("profile:spreadsheet", fields.get("spreadsheet_id") == "spreadsheet_eval_42")
    check("profile:range", fields.get("sheet_range") == "Orders!A1:D3")
    check("profile:render-option", fields.get("value_render_option") == "UNFORMATTED_VALUE")
    check("profile:bearer-auth", fields.get("auth_type") == "bearer")
    check("profile:synthetic-token", fields.get("auth_token") == token)
    check("profile:read-only", fields.get("access") == "read-only")
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
    check("client:sheets-credentials", "google.oauth2.credentials" in imports)
    check("client:build", "build" in calls)
    check("client:sheets-v4", "sheets" in literals and "v4" in literals)
    check("client:values-get", "values" in text and "get" in text and "execute" in calls)
    check("request:spreadsheet", "spreadsheetId" in text and "secrets" in text)
    check("request:range", "range" in text and "sheet_range" in text)
    check("request:render-option", "valueRenderOption" in text and "value_render_option" in text)
    check("range:strict-validation", "fullmatch" in calls and "ValueError" in text)
    validation_lines = call_lines(modules, {"fullmatch", "validate_a1_range", "validate_range"})
    build_lines = call_lines(modules, {"build"})
    check("range:validation-before-client", bool(validation_lines and build_lines and min(validation_lines) < min(build_lines)))
    check("range:no-second-tab-literal", "InternalNotes" not in literals)
    check("rows:header", "headers" in text and "rows" in text)
    check("rows:blank-cell", "None" in text)
    check("rows:short-row-padding", "zip_longest" in text or "len(row)" in text)
    check("rows:dlt-resource", "resource" in text and "dlt" in text and "yield" in text)
    check("desktop:duckdb-pipeline", "DuckDbOutput" in text and "pipeline" in text and "pipeline.run" in text)
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
    forbidden_modules = {
        "requests",
        "httpx",
        "aiohttp",
        "urllib.request",
        "httplib2",
    }
    check("source:no-hand-rolled-http", not any(
        module in imports or any(module + "." in imported for imported in imports)
        for module in forbidden_modules
    ))
    lowered = text.lower()
    check("source:read-only", not any(
        marker in lowered
        for marker in (
            "batchupdate",
            "values().append",
            "values().update",
            "values().clear",
            "permissions().create",
            "permissions().update",
        )
    ))
    check("probe:present", (root / "connectivity_check.py").stat().st_size > 0)
    check("probe:does-not-carry-token", token not in (root / "connectivity_check.py").read_text(encoding="utf-8"))
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

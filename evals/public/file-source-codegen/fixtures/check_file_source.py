"""Runner-side static checks for the local file-source codegen eval."""

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
    result: set[str] = set()
    for module in modules:
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                result.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                result.add(node.module)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--secret-marker-file", type=Path, required=True)
    args = parser.parse_args()

    root = find_closure(args.root)
    required = (
        "spec.py",
        "models.py",
        "infra-profile.yaml",
        "transform/main.py",
        "file-source-path",
        "requirements.txt",
        "README.md",
    )
    for rel in required:
        check(f"file:{rel}", (root / rel).is_file())

    profile = (root / "infra-profile.yaml").read_text(encoding="utf-8", errors="replace")
    fields, _ = profile_attributes(root)
    check("profile:file-source-service", "name: file-source" in profile)
    check("profile:generic-secrets", "nxd:generic-secrets:1.0.0" in profile)
    check("profile:no-credential-attributes", not fields)
    check("path:relative", (root / "file-source-path").read_text(encoding="utf-8").strip() == "data")
    check("path:no-api-probe", not (root / "connectivity_check.py").exists())

    modules = parse_sources(root)
    imports = imported_modules(modules)
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in transform_sources(root))
    literals = [literal for module in modules for literal in string_literals(module)]
    check("reader:filesystem", "filesystem" in text)
    check("reader:jsonl", "read_jsonl" in text)
    check("reader:parquet", "read_parquet" in text)
    check("reader:plain-json", "json.load" in text and "dlt.resource" in text)
    check("reader:format-detection", "_detect_format" in text or "suffix" in text)
    check("reader:model-roots", all(model in text for model in ("events", "refunds", "inventory")))
    check("reader:resource-names", "with_name" in text)
    check("reader:file-secrets", "file_source" in text and "secrets" in text)
    check("desktop:duckdb-pipeline", "DuckDbOutput" in text and "pipeline" in text and "pipeline.run" in text)
    forbidden = {"requests", "httpx", "aiohttp", "urllib.request", "httplib2"}
    check("source:no-hand-rolled-http", not any(
        module in imports or any(module + "." in imported for imported in imports)
        for module in forbidden
    ))
    check("source:no-network-literals", not any(
        literal.startswith(("http://", "https://")) for literal in literals
    ))
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

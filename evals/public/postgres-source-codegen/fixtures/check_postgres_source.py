"""Runner-side static checks for the Postgres source codegen eval."""

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
    token = args.secret_marker_file.read_text(encoding="utf-8").strip()
    required = (
        "spec.py",
        "models.py",
        "infra-profile.yaml",
        "transform/main.py",
        "db-source-tables",
        "requirements.txt",
        "README.md",
        ".gitignore",
        "SENSITIVE",
    )
    for rel in required:
        check(f"file:{rel}", (root / rel).is_file())

    fields, public = profile_attributes(root)
    expected = {
        "host": "db.eval.internal",
        "port": "5432",
        "database": "commerce",
        "schema": "analytics",
        "user": "readonly_eval",
        "password": token,
    }
    for key, value in expected.items():
        check(f"profile:{key}", fields.get(key) == value)
    for key in ("host", "port", "database", "schema"):
        check(f"profile:{key}-public", public.get(key) == "true")
    for key in ("user", "password"):
        check(f"profile:{key}-private", public.get(key) == "false")
    tables = (root / "db-source-tables").read_text(encoding="utf-8", errors="replace")
    check("tables:orders", "orders_model=analytics.orders" in tables)
    check("tables:customers", "customers_model=analytics.customers" in tables)
    check("tables:no-password", token not in tables)
    check("sensitivity:gitignore", "infra-profile.yaml" in (root / ".gitignore").read_text(encoding="utf-8"))
    check("sensitivity:marker", "password" in (root / "SENSITIVE").read_text(encoding="utf-8"))

    modules = parse_sources(root)
    imports = imported_modules(modules)
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in transform_sources(root))
    literals = [literal for module in modules for literal in string_literals(module)]
    check("connector:sql-database", "dlt.sources.sql_database" in imports and "sql_database" in text)
    check("connector:schema", "schema" in text and "secrets" in text)
    check("connector:table-names", "table_names" in text)
    check("connector:resource-renaming", "with_name" in text)
    check("connector:table-map", "db-source-tables" in text or "table_map" in text)
    check("connector:flat-secrets", all(key in text for key in ("host", "port", "database", "user", "password")))
    check("connector:password-not-in-source", token not in literals and token not in text)
    check("desktop:duckdb-pipeline", "DuckDbOutput" in text and "pipeline" in text and "pipeline.run" in text)
    check("source:no-http", not any(module.startswith(("requests", "httpx", "urllib", "aiohttp")) for module in imports))
    check("source:no-write-sql", not any(marker in text.lower() for marker in ("insert into", "update ", "delete from", "create table")))
    check("source:no-data-export", not (root / "data").exists())
    check("probe:no-connectivity-script", not (root / "connectivity_check.py").exists())
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

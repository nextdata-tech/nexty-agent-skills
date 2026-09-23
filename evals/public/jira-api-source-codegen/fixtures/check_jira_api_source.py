"""Runner-side static checks for the Jira source codegen eval."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from api_connector_gate import (  # noqa: E402
    find_closure,
    no_hardcoded_url_or_path,
    profile_attributes,
    string_literals,
    transform_sources,
    uses_rest_api_resources,
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
    expected = {
        "source_kind": "jira",
        "base_url": "https://acme.atlassian.test",
        "endpoint_issues": "/rest/api/3/search",
        "jql_issues": "project = DATA ORDER BY created ASC",
        "start_at": "0",
        "max_results": "50",
        "auth_type": "http_basic",
        "auth_username": "jira_eval_user",
        "auth_password": token,
    }
    for key, value in expected.items():
        check(f"profile:{key}", fields.get(key) == value)
    for key in ("source_kind", "base_url", "endpoint_issues", "jql_issues", "start_at", "max_results", "auth_type", "auth_username"):
        check(f"profile:{key}-public", public.get(key) == "true")
    check("profile:auth-password-private", public.get("auth_password") == "false")
    check("profile:no-write-endpoints", not any(key.startswith("endpoint_") and key != "endpoint_issues" for key in fields))
    check("sensitivity:gitignore", "infra-profile.yaml" in (root / ".gitignore").read_text(encoding="utf-8"))
    check("sensitivity:marker", "auth_password" in (root / "SENSITIVE").read_text(encoding="utf-8"))

    modules = parse_sources(root)
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in transform_sources(root))
    literals = [literal for module in modules for literal in string_literals(module)]
    connector_ok, detail = uses_rest_api_resources(root)
    check("connector:dlt-rest", connector_ok, detail)
    no_url, detail = no_hardcoded_url_or_path(root, ("acme.atlassian.test",), ("/rest/api/3/",))
    check("connector:profile-topology", no_url, detail)
    check("payload:issues", "issues" in text)
    check("payload:offset-pagination", all(part in text for part in ("startAt", "maxResults", "total")))
    check("payload:jql-from-secrets", "jql_issues" in text and "secrets" in text)
    check("payload:fields-flattened", "fields" in text and any(marker in text for marker in ("displayName", "status_name", "assignee_name", "flatten")))
    check("auth:dispatches-auth-type", "auth_type" in text and "http_basic" in text and "secrets" in text)
    check("auth:basic-fields", "auth_username" in text and any(name in text for name in ("auth_password", "auth_token")))
    check("auth:token-not-in-source", token not in literals and token not in text)
    leaked = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name in {"infra-profile.yaml", "source-contract.yaml"}:
            continue
        if token in path.read_text(encoding="utf-8", errors="replace"):
            leaked.append(str(path.relative_to(root)))
    check("auth:token-only-in-profile", not leaked, ", ".join(leaked))
    forbidden_literals = {str(literal).lower() for literal in literals}
    check("operations:read-only", not any(
        literal == "post"
        or "/rest/api/3/issue" in literal
        or literal.rstrip("/").endswith(("/create", "/update", "/transition"))
        for literal in forbidden_literals
    ))
    check("desktop:duckdb-pipeline", "DuckDbOutput" in text and "pipeline" in text and "pipeline.run" in text)
    check("probe:present", (root / "connectivity_check.py").stat().st_size > 0)
    check("probe:does-not-carry-token", token not in (root / "connectivity_check.py").read_text(encoding="utf-8"))
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

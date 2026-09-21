"""Runner-side static contract checks for the HubSpot source codegen eval."""

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


def source_text(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in transform_sources(root)
    )


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
    check("profile:source-kind", fields.get("source_kind") == "hubspot")
    check("profile:base-url", fields.get("base_url") == "https://api.hubapi.com")
    check("profile:contacts-endpoint", fields.get("endpoint_contacts") == "/crm/objects/2026-03/contacts")
    check("profile:search-endpoint", fields.get("endpoint_contact_search") == "/crm/objects/2026-03/contacts/search")
    check("profile:bearer-auth", fields.get("auth_type") == "bearer")
    check("profile:synthetic-token", fields.get("auth_token") == token)
    check("profile:token-private", public.get("auth_token") == "false")
    check("profile:scope", "crm.objects.contacts.read" in fields.get("required_scopes", ""))
    check("sensitivity:gitignore", "infra-profile.yaml" in (root / ".gitignore").read_text(encoding="utf-8"))
    check("sensitivity:marker", "auth_token" in (root / "SENSITIVE").read_text(encoding="utf-8"))

    modules = parse_sources(root)
    text = source_text(root)
    connector_ok, connector_detail = uses_rest_api_resources(root)
    check("connector:dlt-rest", connector_ok, connector_detail)
    no_url, url_detail = no_hardcoded_url_or_path(
        root, ("api.hubapi.com",), ("/crm/objects/",)
    )
    check("connector:profile-topology", no_url, url_detail)
    literals = [literal for module in modules for literal in string_literals(module)]
    check("connector:token-not-in-source", token not in literals)
    leaked = []
    for path in root.rglob("*"):
        # source-contract.yaml is runner-supplied input and intentionally carries
        # the synthetic token; only generated closure files belong in this scan.
        if not path.is_file() or path.name in {"infra-profile.yaml", "source-contract.yaml"}:
            continue
        if token in path.read_text(encoding="utf-8", errors="replace"):
            leaked.append(str(path.relative_to(root)))
    check("connector:token-only-in-profile", not leaked, ", ".join(leaked))
    check("auth:dispatches-auth-type", "auth_type" in text and "auth" in text and "secrets" in text)
    check("payload:results-envelope", "results" in literals or '"results"' in text or "'results'" in text)
    check("payload:cursor", "paging" in text and "after" in text)
    check("payload:search-post", "POST" in text or "post" in text.lower())
    check("payload:search-body", "properties" in text and "filterGroups" in text)
    check("desktop:duckdb-pipeline", "DuckDbOutput" in text and "pipeline" in text and "pipeline.run" in text)
    forbidden_paths = [
        literal for literal in literals
        if literal.strip().lower().rstrip("/").endswith(("/create", "/update"))
    ]
    check("operations:read-only", not forbidden_paths, ", ".join(forbidden_paths))
    check("probe:present", (root / "connectivity_check.py").stat().st_size > 0)
    check("probe:does-not-carry-token", token not in (root / "connectivity_check.py").read_text(encoding="utf-8"))
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

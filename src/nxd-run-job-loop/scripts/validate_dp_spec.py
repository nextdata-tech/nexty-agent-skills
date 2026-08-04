#!/usr/bin/env python3
"""Validate the canonical human-editable dp-spec v2 Markdown document.

This entry point deliberately has no legacy parser.  The loop, lock writer and
generator all consume the same ``dp_spec_v2`` AST and diagnostics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import dp_spec_v2 as v2  # noqa: E402


def _issue(issue: v2.ValidationIssue) -> dict[str, str]:
    return {
        "schema": v2.SPEC_DIAGNOSTIC_SCHEMA_ID,
        "code": issue.code,
        "path": issue.path,
        "severity": "error",
        "owner": issue.owner,
        "control": issue.control,
        "stage": "s0_spec",
        "origin": "tool_computed",
        "message": issue.message,
    }


def validate(path: Path) -> dict:
    """Return the stable report envelope used by lock/build-record tooling."""
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = v2.parse(raw)
        issues = v2.validate(parsed)
        diagnostics = [_issue(issue) for issue in issues]
        return {
            "schema": "nxd-diagnostic-report-v2",
            "tool": "validate_dp_spec",
            "target": str(path),
            "ok": not diagnostics,
            "spec_hash": v2.semantic_hash(parsed),
            "counts": {"error": len(diagnostics), "warning": 0, "info": 0},
            "diagnostics": diagnostics,
        }
    except v2.UnsupportedVersionError as exc:
        return {
            "schema": "nxd-diagnostic-report-v2",
            "tool": "validate_dp_spec",
            "target": str(path),
            "ok": False,
            "spec_hash": None,
            "counts": {"error": 1, "warning": 0, "info": 0},
            "diagnostics": [{
                "schema": v2.SPEC_DIAGNOSTIC_SCHEMA_ID,
                "code": "spec.frontmatter.unsupported_version",
                "path": "v2:frontmatter.dp_spec_version",
                "severity": "error",
                "owner": "user",
                "control": "enum",
                "stage": "s0_spec",
                "origin": "tool_computed",
                "message": str(exc),
            }],
        }
    except (OSError, UnicodeError, v2.ParseError) as exc:
        return {
            "schema": "nxd-diagnostic-report-v2",
            "tool": "validate_dp_spec",
            "target": str(path),
            "ok": False,
            "spec_hash": None,
            "counts": {"error": 1, "warning": 0, "info": 0},
            "diagnostics": [{
                "schema": v2.SPEC_DIAGNOSTIC_SCHEMA_ID,
                "code": "spec.parse.invalid",
                "path": "v2:document",
                "severity": "error",
                "owner": "user",
                "control": "text",
                "stage": "s0_spec",
                "origin": "tool_computed",
                "message": str(exc),
            }],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = validate(args.spec)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for diag in report["diagnostics"]:
            print(f"{diag['severity'].upper()} {diag['code']} {diag['path']}: {diag['message']}")
        if report["ok"]:
            print("ok")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

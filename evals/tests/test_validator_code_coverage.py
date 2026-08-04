"""Coverage of the v2 validator's stable diagnostics and harness contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-run-job-loop" / "scripts"
FIXTURE = REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md"
VALIDATOR = SCRIPTS / "validate_dp_spec.py"
sys.path.insert(0, str(SCRIPTS))

import dp_spec_v2 as v2  # noqa: E402
import validate_dp_spec  # noqa: E402


def text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def report(tmp_path: Path, value: str) -> dict:
    path = tmp_path / "dp-spec.md"
    path.write_text(value, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(VALIDATOR), str(path), "--json"], capture_output=True, text=True)
    assert proc.stdout
    return json.loads(proc.stdout)


def codes(value: str) -> set[str]:
    try:
        return {item.code for item in v2.validate(value)}
    except v2.ParseError as exc:
        return {str(exc).split(":", 1)[0]}


def test_valid_spec_report_is_v2_and_field_addressed(tmp_path: Path):
    payload = report(tmp_path, text())
    assert payload["schema"] == "nxd-diagnostic-report-v2"
    assert payload["ok"] is True
    assert payload["spec_hash"].startswith("sha256:")


@pytest.mark.parametrize(
    ("needle", "expected"),
    [
        ("## Outputs", "v2.section.missing"),
        ("- Delivery refs: `finance_semantic_port`", "v2.field.missing"),
    ],
)
def test_structural_gaps_are_stable(tmp_path: Path, needle: str, expected: str):
    value = text()
    if needle == "## Outputs":
        value = value.replace(needle, "## Removed", 1)
    else:
        value = value.replace(needle + "\n", "", 1)
    payload = report(tmp_path, value)
    assert payload["ok"] is False
    assert any(d["code"] == expected for d in payload["diagnostics"])
    assert all({"schema", "path", "code", "severity", "owner", "control", "message"} <= set(d) for d in payload["diagnostics"])
    assert all(d["schema"] == v2.SPEC_DIAGNOSTIC_SCHEMA_ID for d in payload["diagnostics"])


def test_output_reachability_and_delivery_usage_are_diagnostics(tmp_path: Path):
    value = text().replace("- Questions: `monthly_revenue_by_customer`\n", "- Questions: `other_question`\n", 1)
    value = value.replace("### Question `monthly_revenue_by_customer`", "### Question `monthly_revenue_by_customer`\n\n", 1)
    payload = report(tmp_path, value)
    codes_seen = {d["code"] for d in payload["diagnostics"]}
    assert "v2.output.question_ref" in codes_seen
    assert "v2.question.unserved" in codes_seen


def test_v1_returns_unsupported_version(tmp_path: Path):
    payload = report(tmp_path, text().replace("dp_spec_version: 2", "dp_spec_version: 1", 1))
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["code"] == "spec.frontmatter.unsupported_version"
    assert payload["spec_hash"] is None


def test_opaque_operation_and_policy_are_rejected():
    value = text().replace("- Operation: `aggregate`", "- Operation: `free_form_sql`", 1)
    assert "v2.transform.operation" in codes(value)
    assert "v2.section.policy" in codes(text() + "\n## Policy\n\nNot allowed.\n")


def test_shared_splitter_exports_are_removed_from_validator():
    assert not hasattr(validate_dp_spec, "split_frontmatter")
    assert not hasattr(validate_dp_spec, "split_sections")
    assert "dp_spec_v2" in VALIDATOR.read_text(encoding="utf-8")

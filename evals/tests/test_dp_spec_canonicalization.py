"""Semantic v2 canonicalization and source-editing contract tests."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-run-job-loop" / "scripts"
WORKED_EXAMPLE = REPO / "src" / "nxd-run-job-loop" / "reference" / "dp-spec.md"
sys.path.insert(0, str(SCRIPTS))

import dp_spec_v2 as v2  # noqa: E402
import dp_diagnostics as dpd  # noqa: E402


def sample() -> str:
    blocks = re.findall(r"^```markdown\n(.*?)^```", WORKED_EXAMPLE.read_text(encoding="utf-8"), re.S | re.M)
    assert len(blocks) == 1
    return blocks[0]


def test_shared_entry_point_uses_v2_content_hash():
    text = sample()
    assert v2.semantic_hash(text) == dpd.spec_hash(text.encode())
    assert v2.semantic_hash(text.replace("status: proposed", "status: draft", 1)) == v2.semantic_hash(text)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.replace("Provide an auditable", "Provide an auditable  ", 1),
        lambda s: s.replace("\n\n## Models", "\n\n\n## Models", 1),
        lambda s: s.replace("- Description: Pristine order relation.", "<!-- note -->\n- Description: Pristine order relation."),
    ],
)
def test_nonsemantic_formatting_does_not_move_hash(mutate):
    assert v2.semantic_hash(sample()) == v2.semantic_hash(mutate(sample()))


def test_semantic_content_and_unknown_body_move_hash():
    original = sample()
    changed = original.replace("Pristine order relation.", "Source order relation.", 1)
    assert v2.semantic_hash(original) != v2.semantic_hash(changed)
    unknown = original + "\n## Notes\n\nThis is retained and hashed.\n"
    unknown_changed = unknown.replace("retained and hashed", "retained and changed")
    assert v2.semantic_hash(unknown) != v2.semantic_hash(unknown_changed)


def test_canonical_object_is_closed_v2_and_excludes_lifecycle():
    obj = v2.canonical_object(sample())
    assert obj["schema"] == "nxd-dp-spec-schema-v2"
    assert obj["frontmatter"] == {"dp_spec_version": 2, "name": "monthly_revenue", "workflow": "monthly-revenue"}
    assert set(obj["models"]["orders"]) >= {"id", "kind", "fields"}
    assert "sections" not in obj


def test_v1_fails_closed_with_stable_error():
    with pytest.raises(v2.UnsupportedVersionError, match="unsupported_version"):
        v2.parse(sample().replace("dp_spec_version: 2", "dp_spec_version: 1", 1))


def test_crlf_is_not_normalized():
    with pytest.raises(v2.ParseError, match="CRLF"):
        v2.parse(sample().replace("\n", "\r\n"))


def test_approve_and_patch_bind_and_revoke_content(tmp_path: Path):
    path = tmp_path / "dp-spec.md"
    path.write_text(sample(), encoding="utf-8")
    proposed = v2.parse(path.read_text(encoding="utf-8"))
    approved = v2.approve(proposed, base_hash=v2.semantic_hash(proposed))
    parsed_approved = v2.parse(approved)
    assert parsed_approved.document.frontmatter.status == "approved"
    assert parsed_approved.document.frontmatter.approved_content_hash == v2.semantic_hash(parsed_approved)
    revoked = v2.targeted_patch(
        parsed_approved,
        base_hash=v2.semantic_hash(parsed_approved),
        path="v2:models[orders].description",
        value="Changed description.",
    )
    parsed_revoked = v2.parse(revoked)
    assert parsed_revoked.document.frontmatter.status == "proposed"
    assert parsed_revoked.document.frontmatter.approved_content_hash is None


def test_section_schema_is_section_specific_and_closed():
    schema = v2.SCHEMA
    model_item = schema["properties"]["models"]["additionalProperties"]
    assert model_item["additionalProperties"] is False
    assert "kind" in model_item["properties"]
    assert "operation" not in model_item["properties"]

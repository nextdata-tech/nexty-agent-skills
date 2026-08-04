"""Focused contract tests for the additive dp-spec v2 helper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-run-job-loop" / "scripts"
FIXTURE = Path(__file__).parent / "fixtures" / "dp-spec-v2-valid.md"
sys.path.insert(0, str(SCRIPTS))

import dp_spec_v2 as v2  # noqa: E402


def sample() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def replace_once(text: str, before: str, after: str) -> str:
    assert before in text
    return text.replace(before, after, 1)


def codes(text: str) -> set[str]:
    try:
        return {issue.code for issue in v2.validate_with_graph(text)}
    except v2.ParseError as exc:
        return {str(exc)}


def test_valid_sample_has_typed_ast_source_map_and_semantic_hash():
    parsed = v2.parse(sample())
    assert not v2.validate_with_graph(parsed)
    assert parsed.document.frontmatter.dp_spec_version == 2
    assert parsed.document.models[1].id == "monthly_customer_revenue"
    assert "v2:models[monthly_customer_revenue].produced_by" in parsed.source_map.spans
    assert parsed.source_map.spans["v2:models[monthly_customer_revenue].produced_by"].line_start > 1
    assert v2.semantic_hash(parsed).startswith("sha256:")


@pytest.mark.parametrize(
    "before, after",
    [
        ("- Kind: `base`", "kind: base"),
        ("- Type: `csv`", "- type: csv"),
    ],
)
def test_no_yaml_ish_section_bodies(before: str, after: str):
    with pytest.raises(v2.ParseError, match="YAML-ish"):
        v2.parse(replace_once(sample(), before, after))


def test_outputs_are_explicit_and_required():
    missing_field = replace_once(sample(), "- Projection: `customer_id, month, revenue`\n", "")
    assert "v2.field.missing" in codes(missing_field)
    no_section = sample().replace("## Outputs\n\n### Output `monthly_revenue_port`\n- Model: `monthly_customer_revenue`\n- Questions: `monthly_revenue_by_customer`\n- Projection: `customer_id, month, revenue`\n- Order by: `month desc, customer_id asc`\n- Delivery refs: `finance_semantic_port`\n\n", "")
    assert "v2.section.missing" in codes(no_section)


def test_transform_graph_and_model_origins_are_checked():
    text = replace_once(sample(), "- Produced by: `aggregate_monthly_revenue`", "- Produced by: `other_step`")
    assert "v2.model.origin" in codes(text)
    text = replace_once(sample(), "- Input: `orders_csv`", "- Input: `missing_input`")
    assert "v2.model.origin" in codes(text)


def test_invalid_output_references_are_rejected():
    text = replace_once(sample(), "- Model: `monthly_customer_revenue`", "- Model: `missing_model`")
    assert "v2.output.model_ref" in codes(text)
    text = replace_once(sample(), "- Questions: `monthly_revenue_by_customer`", "- Questions: `missing_question`")
    assert "v2.output.question_ref" in codes(text)


def test_multiple_producers_and_cycles_are_rejected():
    extra = """
### Step `second_producer`
- Operation: `project`
- Inputs: `orders`
- Output: `monthly_customer_revenue`
- Fields: `order_id`
"""
    text = replace_once(sample(), "## Outputs", extra + "\n## Outputs")
    assert "v2.model.producer_count" in codes(text)

    cyclic = sample()
    cyclic = replace_once(cyclic, "- Inputs: `orders`", "- Inputs: `monthly_customer_revenue`")
    assert "v2.transform.cycle" in codes(cyclic)


def test_transform_operation_is_closed_and_structured():
    unsupported = replace_once(sample(), "- Operation: `aggregate`", "- Operation: `free_form_sql`")
    assert "v2.transform.operation" in codes(unsupported)
    missing_aggregate = replace_once(sample(), "- Measures: `revenue=sum(orders.amount_usd)`\n", "")
    assert "v2.field.missing" in codes(missing_aggregate)

    join = replace_once(sample(), "- Operation: `aggregate`", "- Operation: `join`")
    join = replace_once(join, "- Inputs: `orders`", "- Inputs: `orders, monthly_customer_revenue`")
    assert "v2.field.missing" in codes(join)


def test_transform_operations_define_their_output_shape_and_forbid_cross_op_fields():
    extra_output_field = replace_once(
        sample(),
        "- Fields: `customer_id, month, revenue`",
        "- Fields: `customer_id, month, revenue, extra_field`",
    )
    assert "v2.transform.output_shape" in codes(extra_output_field)
    aggregate_with_dedup_rule = replace_once(
        sample(),
        "- Null handling: `ignore`",
        "- Null handling: `ignore`\n- Winner: `last`",
    )
    assert "v2.transform.field.unknown" in codes(aggregate_with_dedup_rule)


def test_policy_is_not_a_v2_section_and_procedures_are_versioned():
    policy = sample() + "\n## Policy\n\nNo standalone policy is allowed.\n"
    assert "v2.section.policy" in codes(policy)
    procedure = replace_once(sample(), "- Operation: `aggregate`", "- Operation: `apply_procedure`")
    procedure = replace_once(procedure, "- Group by: `orders.customer_id, orders.month`\n", "- Procedure: `score_orders`\n")
    procedure = replace_once(procedure, "- Measures: `revenue=sum(orders.amount_usd)`\n", "")
    assert "v2.procedure.version" in codes(procedure)


def test_blocking_open_question_prevents_approval():
    text = replace_once(sample(), "status: proposed", "status: approved")
    text += """
### Question `refund_policy`
- Blocking: `yes`
- Target: `model:monthly_customer_revenue`

Should refunds be included in monthly revenue?
"""
    assert "v2.approval.blocked" in codes(text)


def test_semantic_hash_ignores_formatting_but_diff_finds_semantics():
    formatted = sample().replace("\n\n## Models", "\n\n\n## Models").replace("Order rows supplied by finance.", "Order rows supplied by finance.  ")
    assert v2.semantic_hash(sample()) == v2.semantic_hash(formatted)
    changed = replace_once(sample(), "Monthly revenue per customer.", "Monthly recognized revenue per customer.")
    diff = v2.semantic_diff(sample(), changed)
    assert diff == [{
        "path": "v2:models[monthly_customer_revenue].description",
        "before": "Monthly revenue per customer.",
        "after": "Monthly recognized revenue per customer.",
    }]
    lifecycle = sample().replace("status: proposed", "status: draft", 1)
    assert v2.semantic_diff(sample(), lifecycle) == []


def test_targeted_patch_preserves_comments_and_rejects_stale_base():
    original = sample().replace("- Description: Pristine order relation.", "<!-- preserve this comment -->\n- Description: Pristine order relation.")
    parsed = v2.parse(original)
    assert v2.semantic_hash(parsed) == v2.semantic_hash(sample())
    path = "v2:models[orders].description"
    patched = v2.targeted_patch(parsed, base_hash=v2.semantic_hash(parsed), path=path, value="Unchanged source order relation.")
    assert "<!-- preserve this comment -->" in patched
    assert "- Description: Unchanged source order relation." in patched
    kind_path = "v2:models[orders].kind"
    kind_patched = v2.targeted_patch(v2.parse(sample()), base_hash=v2.semantic_hash(sample()), path=kind_path, value="reference")
    assert "- Kind: `reference`" in kind_patched
    with pytest.raises(v2.StalePatchError):
        v2.targeted_patch(parsed, base_hash="sha256:stale", path=path, value="x")


def test_duplicate_headings_and_preamble_are_never_silently_dropped():
    with pytest.raises(v2.ParseError, match="duplicate section"):
        v2.parse(sample() + "\n## Models\n")
    preamble = replace_once(sample(), "---\n\n## Intent", "---\n\nA preamble must be reported.\n\n## Intent")
    assert "v2.document.preamble" in codes(preamble)


def test_new_emitter_is_proposal_and_cli_is_additive(tmp_path: Path):
    proposal = v2.new_document("new_product", "new-product")
    assert "dp_spec_version: 2" in proposal
    assert v2.validate_with_graph(proposal)
    spec = tmp_path / "spec.md"
    spec.write_text(sample(), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "dp_spec_v2.py"), "validate", str(spec)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"ok": true' in result.stdout


def test_emitting_canonical_content_defaults_to_a_proposal():
    emitted = v2.emit(v2.canonical_object(sample()))
    parsed = v2.parse(emitted)
    assert parsed.document.frontmatter.status == "proposed"
    assert not v2.validate(parsed)


def test_v1_is_rejected_as_unsupported_version():
    old = sample().replace("dp_spec_version: 2", "dp_spec_version: 1", 1)
    with pytest.raises(v2.UnsupportedVersionError, match="unsupported_version"):
        v2.parse(old)


def test_approval_binds_content_and_patch_revokes_it():
    proposed = v2.parse(sample())
    approved_raw = v2.approve(proposed, base_hash=v2.semantic_hash(proposed))
    approved = v2.parse(approved_raw)
    assert approved.document.frontmatter.status == "approved"
    assert approved.document.frontmatter.approved_content_hash == v2.semantic_hash(approved)
    changed = v2.targeted_patch(approved, base_hash=v2.semantic_hash(approved), path="v2:models[orders].description", value="Changed order relation.")
    changed_doc = v2.parse(changed).document
    assert changed_doc.frontmatter.status == "proposed"
    assert changed_doc.frontmatter.approved_content_hash is None


def test_crlf_is_rejected_instead_of_normalized():
    with pytest.raises(v2.ParseError, match="CRLF"):
        v2.parse(sample().replace("\n", "\r\n"))


def test_opaque_derive_expression_is_rejected():
    text = sample().replace("Operation: `aggregate`", "Operation: `derive`", 1)
    text = text.replace("- Group by: `orders.customer_id, orders.month`", "- Expressions: `revenue = orders.amount_usd + orders.amount_usd`", 1)
    text = text.replace("- Measures: `revenue=sum(orders.amount_usd)`\n", "", 1)
    assert "v2.field.missing" in codes(text) or "v2.transform.structure" in codes(text)


def test_derive_field_copies_must_be_qualified():
    text = sample().replace("Operation: `aggregate`", "Operation: `derive`", 1)
    text = text.replace(
        "- Group by: `orders.customer_id, orders.month`\n",
        "- Expressions: `revenue = amount_usd`\n",
        1,
    )
    text = text.replace("- Measures: `revenue=sum(orders.amount_usd)`\n", "", 1)
    assert "v2.transform.structure" in codes(text)


def test_input_type_is_closed():
    text = sample().replace("- Type: `csv`", "- Type: `spreadsheet`", 1)
    assert "v2.input.type" in codes(text)

"""Contract tests for the prose-first DP-spec authoring boundary."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-run-job-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dp_spec_authoring as v3  # noqa: E402
import dp_diagnostics as dpd  # noqa: E402
import dp_spec_v2 as v2  # noqa: E402
import validate_dp_spec as vds  # noqa: E402


def sample(status: str = "proposed") -> str:
    return f'''---
dp_spec_version: 3
name: monthly_revenue
workflow: monthly-revenue
status: {status}
---

## Intent

Provide an auditable monthly revenue relation for finance review.

## Questions

What was monthly revenue for each customer?

## Scope

Include paid orders and exclude refunds until the refund rule is decided.

## Terms

### Customer

A person or organization responsible for an order.

## Inputs

### Orders

Load completed orders from the monthly export.

#### Expectations

Rows have an order identifier and amounts are expressed in EUR.

## Models

### Monthly revenue

Revenue grouped by customer and month.

## Transform

Group accepted orders by customer and month and sum their amounts.

## Outputs

### Monthly revenue by customer

The user-visible monthly revenue relation.

#### Promises

Refunds are excluded and accepted rows reconcile to the result.

## Decisions

### Refund treatment

Refunds are excluded until a timing rule is supplied.

## Open Questions

'''


def proposal_for(text: str, *, open_questions: list[dict] | None = None) -> dict:
    parsed = v3.parse(text)
    provenance = {
        "v3:intent.text": "explicit",
        "v3:questions.text": "explicit",
        "v3:scope.text": "explicit",
        "v3:terms[customer].text": "explicit",
        "v3:terms[customer].priority": "platform_fixed",
        "v3:inputs[orders].text": "explicit",
        "v3:models[monthly_revenue].text": "explicit",
        "v3:transform.text": "explicit",
        "v3:outputs[monthly_revenue_by_customer].text": "explicit",
        "v3:decisions[refund_treatment].text": "explicit",
        "v3:delivery": "platform_fixed",
    }
    provenance = {
        path: origin
        for path, origin in provenance.items()
        if origin == "platform_fixed" or path in parsed.source_map.spans
    }
    spans = {
        path: parsed.source_map.spans[path].to_dict()
        for path, origin in provenance.items()
        if origin != "platform_fixed"
    }
    payload = {
        "intent": "Provide monthly revenue for finance.",
        "questions": [{"id": "monthly_revenue", "question": "What was monthly revenue?"}],
        "scope": "Paid orders only.",
        "terms": [{
            "id": "customer",
            "name": "Customer",
            "definition": "A person or organization responsible for an order.",
            "synonyms": ["account holder"],
            "related_terms": [],
            "examples": [],
            "term_values": [],
            "tags": {"domain": "business"},
            "priority": "P3",
        }],
        "inputs": [{
            "id": "orders",
            "expectations": [{
                "id": "orders_have_ids",
                "model": "orders",
                "guarantee": "Every accepted order has an identifier.",
                "rule": "order_id is non-null",
                "fields": ["order_id"],
            }],
        }],
        "models": [
            {"id": "orders", "fields": ["order_id", "amount"]},
            {"id": "monthly_revenue", "fields": ["customer_id", "month", "revenue"]},
        ],
        "transform": [{"id": "aggregate_monthly_revenue", "operation": "aggregate"}],
        "outputs": [{
            "id": "monthly_revenue_by_customer",
            "promises": [{
                "id": "reconciles_to_inputs",
                "model": "monthly_revenue",
                "guarantee": "The output reconciles to accepted input rows.",
                "rule": "sum(output.revenue) equals accepted order amount",
                "fields": ["revenue"],
            }],
        }],
        "decisions": [{
            "id": "refund_treatment",
            "target": "transform:aggregate_monthly_revenue",
            "ruling": "Exclude refunds until a timing rule is supplied.",
            "status": "locked",
        }],
        "open_questions": open_questions or [],
        "delivery": {
            "kind": "semantic_query",
            "profile": "desktop-local",
            "port": "duckdb",
            "provenance": "platform_fixed",
        },
        "contracts": [
            {
                "id": "orders_have_ids",
                "attachment": "input:orders",
                "model": "orders",
                "phase": "pre_transform",
                "guarantee": "Every accepted order has an identifier.",
                "rule": "order_id is non-null",
                "fields": ["order_id"],
            },
            {
                "id": "reconciles_to_inputs",
                "attachment": "output:monthly_revenue_by_customer",
                "model": "monthly_revenue",
                "phase": "post_transform",
                "guarantee": "The output reconciles to accepted input rows.",
                "rule": "sum(output.revenue) equals accepted order amount",
                "fields": ["revenue"],
            },
        ],
    }
    return {
        "schema": v3.PROPOSAL_SCHEMA_ID,
        "authoring_version": v3.AUTHORING_VERSION,
        "source_hash": v3.semantic_hash(parsed),
        "proposal": payload,
        "provenance": provenance,
        "source_spans": spans,
        "anchors": {},
        "echo": {
            "text": "I understood the monthly revenue goal, the inline customer term, the input expectation, the output promise, the P3 default priority for the customer term, and the fixed local delivery.",
            "coverage": list(provenance),
        },
    }


def test_parser_keeps_free_prose_and_exposes_form_spans():
    parsed = v3.parse(sample())

    assert parsed.frontmatter.dp_spec_version == 3
    assert parsed.sections["terms"].text == "A person or organization responsible for an order."
    assert "#### Expectations" in parsed.sections["inputs"].text
    assert "#### Promises" in parsed.sections["outputs"].text
    assert "v3:terms[customer].text" in parsed.source_map.spans
    assert "v3:inputs[orders].text" in parsed.source_map.spans
    assert not v3.validate(parsed)


def test_parser_accepts_natural_language_colons_and_markdown_lists():
    text = sample().replace(
        "Group accepted orders by customer and month and sum their amounts.",
        "Use the order date: group by customer and month.\n\n- Exclude test accounts\n- Preserve the source amount",
    )
    assert not v3.validate(text)


def test_parser_treats_fenced_headings_as_free_prose_and_enforces_section_order():
    text = sample().replace(
        "Group accepted orders by customer and month and sum their amounts.",
        "Example:\n\n```markdown\n## Inputs\n### A heading in an example\n```",
    )
    parsed = v3.parse(text)
    assert "## Inputs" in parsed.sections["transform"].text
    assert "### A heading in an example" in parsed.sections["transform"].text

    out_of_order = sample().replace(
        "## Intent\n\nProvide an auditable monthly revenue relation for finance review.\n\n## Questions",
        "## Questions\n\nWhat was monthly revenue for each customer?\n\n## Intent",
    )
    assert "v3.section.order" in {issue.code for issue in v3.validate(out_of_order)}


def test_fenced_code_indentation_is_semantic_but_outer_whitespace_is_not():
    first = sample().replace(
        "Group accepted orders by customer and month and sum their amounts.",
        "```python\n  value = 1\n```",
    )
    second = first.replace("  value = 1", "    value = 1")
    assert v3.semantic_hash(first) != v3.semantic_hash(second)

    outer_a = sample().replace("Provide an auditable", "Provide    an auditable")
    outer_b = sample().replace("Provide an auditable", "Provide an auditable")
    assert v3.semantic_hash(outer_a) == v3.semantic_hash(outer_b)


def test_v1_and_v2_are_not_accepted_by_the_new_authoring_boundary():
    for version in (1, 2):
        with pytest.raises(v3.UnsupportedVersionError, match="unsupported_version"):
            v3.parse(sample().replace("dp_spec_version: 3", f"dp_spec_version: {version}", 1))


def test_unknown_or_duplicate_top_level_sections_fail_closed():
    with pytest.raises(v3.ParseError, match="unknown top-level section"):
        v3.parse(sample() + "\n## Delivery\n\nDo not author transport here.\n")
    with pytest.raises(v3.ParseError, match="duplicate section"):
        v3.parse(sample() + "\n## Terms\n")
    with pytest.raises(v3.ParseError, match="unsupported H1"):
        v3.parse(sample() + "\n# Policy\n\nDo not add a user-authored policy section.\n")


@pytest.mark.parametrize(
    "heading",
    ("#\tPolicy", "   # Policy", "Policy\n======"),
)
def test_all_commonmark_h1_forms_are_rejected(heading):
    with pytest.raises(v3.ParseError, match="unsupported H1"):
        v3.parse(sample() + f"\n{heading}\n")


def test_fence_closer_must_match_and_unclosed_fences_fail():
    fenced = sample().replace(
        "## Transform\n\nGroup accepted orders by customer and month and sum their amounts.",
        "## Transform\n\n```python\nvalue = '~~~'\n    indented = True\n```",
    )
    changed = fenced.replace("    indented = True", "  indented = True")
    assert v3.semantic_hash(fenced) != v3.semantic_hash(changed)
    with pytest.raises(v3.ParseError, match="unclosed fenced code block"):
        v3.parse(fenced.replace("```\n\n## Outputs", "~~~\n\n## Outputs"))


def test_populated_terms_and_subsections_cannot_be_silently_omitted():
    missing_inputs = sample().replace(
        "## Inputs\n\n### Orders\n\nLoad completed orders from the monthly export.\n\n#### Expectations\n\nRows have an order identifier and amounts are expressed in EUR.\n\n",
        "",
    )
    proposal = proposal_for(missing_inputs)
    assert "v3.section.missing" in {
        issue.code for issue in v3.validate_proposal(v3.parse(missing_inputs), proposal)
    }

    proposal = proposal_for(sample())
    proposal["proposal"]["terms"] = []
    assert "v3.proposal.section_omitted" in {
        issue.code for issue in v3.validate_proposal(v3.parse(sample()), proposal)
    }

    extra_block = sample().replace(
        "## Terms\n\n### Customer\n\nA person or organization responsible for an order.",
        "## Terms\n\n### Customer\n\nA person or organization responsible for an order.\n\n### Uncaptured\n\nThis must be represented in the typed proposal.",
    )
    assert "v3.provenance.source_block_uncovered" in {
        issue.code for issue in v3.validate_proposal(v3.parse(extra_block), proposal_for(extra_block))
    }


def test_subsection_anchors_can_map_display_headings_to_typed_ids_and_scalars():
    renamed = sample().replace("### Customer", "### Customer profile")
    renamed_proposal = proposal_for(renamed)
    renamed_parsed = v3.parse(renamed)
    renamed_proposal["provenance"]["v3:terms[customer].text"] = "explicit"
    renamed_proposal["source_spans"]["v3:terms[customer].text"] = renamed_parsed.source_map.spans["v3:terms[customer_profile].text"].to_dict()
    renamed_proposal["anchors"] = {"v3:terms[customer_profile].text": "v3:terms[customer].text"}
    renamed_proposal["echo"]["coverage"].append("v3:terms[customer].text")
    assert not v3.validate_proposal(renamed_parsed, renamed_proposal)

    scalar = sample().replace(
        "## Scope\n\nInclude paid orders and exclude refunds until the refund rule is decided.",
        "## Scope\n\n### Finance scope\n\nInclude paid orders and exclude refunds until the refund rule is decided.",
    )
    scalar_proposal = proposal_for(scalar)
    scalar_parsed = v3.parse(scalar)
    scalar_proposal["source_spans"]["v3:scope.text"] = scalar_parsed.source_map.spans["v3:scope[finance_scope].text"].to_dict()
    scalar_proposal["anchors"] = {"v3:scope[finance_scope].text": "v3:scope.text"}
    assert not v3.validate_proposal(scalar_parsed, scalar_proposal)


@pytest.mark.parametrize("priority", ("P3", "P4"))
def test_value_level_priority_provenance_can_be_source_bound(priority):
    text = sample()
    parsed = v3.parse(text)
    proposal = proposal_for(text)
    path = "v3:terms[customer].priority"
    proposal["proposal"]["terms"][0]["priority"] = priority
    proposal["provenance"][path] = "explicit"
    proposal["source_spans"][path] = parsed.source_map.spans["v3:terms[customer].text"].to_dict()
    proposal["echo"]["coverage"].append(path)
    proposal["echo"]["text"] += f" The {priority} term priority is source-bound."
    assert not v3.validate_proposal(parsed, proposal)


def test_explicit_anchors_cannot_merge_two_source_subsections_into_one_term():
    text = sample().replace(
        "### Customer\n\nA person or organization responsible for an order.",
        "### Customer\n\nA person or organization responsible for an order.\n\n### Customer alias\n\nAn alternate customer label.",
    )
    parsed = v3.parse(text)
    proposal = proposal_for(text)
    proposal["anchors"] = {"v3:terms[customer_alias].text": "v3:terms[customer].text"}
    assert "v3.provenance.anchor_duplicate" in {
        issue.code for issue in v3.validate_proposal(parsed, proposal)
    }


def test_proposal_validation_requires_echo_terms_contracts_and_fixed_delivery():
    text = sample()
    proposal = proposal_for(text)
    parsed = v3.parse(text)

    assert not v3.validate_proposal(parsed, proposal)

    proposal["echo"]["coverage"] = []
    assert "v3.echo.uncovered" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["proposal"]["terms"][0]["related_terms"] = ["missing"]
    assert "v3.term.related_ref" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["proposal"]["delivery"]["port"] = "static-artifact"
    assert "v3.delivery.fixed_profile" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["proposal"]["contracts"] = []
    assert "v3.contract.inventory_mismatch" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["proposal"]["models"] = ["not an object"]
    assert "v3.proposal.item_shape" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["proposal"]["transform"][0]["operation"] = "invent"
    assert "v3.transform.operation" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["echo"]["text"] = "OK."
    assert "v3.echo.default_disclosure" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["proposal"]["terms"][0]["priority"] = "P4"
    assert "v3.term.priority_provenance" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}


@pytest.mark.parametrize(
    ("path", "mutate", "code"),
    [
        ("questions", lambda value: value[0].update(extra=True), "v3.proposal.unknown_key"),
        ("terms", lambda value: value[0].update(tags=["business"]), "v3.term.tags"),
        ("inputs", lambda value: value[0].update(expectations={}), "v3.proposal.list"),
        ("models", lambda value: value[0].update(extra=True), "v3.proposal.unknown_key"),
        ("transform", lambda value: value[0].update(operation=None), "v3.proposal.required_field"),
        ("outputs", lambda value: value[0].update(promises=[{"id": "bad"}]), "v3.proposal.required_field"),
        ("decisions", lambda value: value[0].update(status=True), "v3.decision.status"),
        ("open_questions", lambda value: value.append({"id": "bad", "question": "bad", "blocking": "yes"}), "v3.open_question.blocking"),
        ("contracts", lambda value: value[0].update(extra=True), "v3.proposal.unknown_key"),
        ("delivery", lambda value: value.update(extra=True), "v3.proposal.unknown_key"),
    ],
)
def test_typed_proposal_nested_shapes_fail_closed(path, mutate, code):
    text = sample()
    proposal = proposal_for(text)
    mutate(proposal["proposal"][path])
    issues = v3.validate_proposal(v3.parse(text), proposal)
    assert code in {issue.code for issue in issues}


def test_malformed_unhashable_nested_values_return_issues_not_tracebacks():
    text = sample()
    parsed = v3.parse(text)

    proposal = proposal_for(text)
    proposal["proposal"]["terms"][0]["priority"] = []
    assert "v3.term.priority" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    del proposal["proposal"]["terms"][0]["priority"]
    assert "v3.proposal.required_field" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["proposal"]["decisions"][0]["status"] = []
    assert "v3.decision.status" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["provenance"]["v3:intent.text"] = []
    assert "v3.provenance.value" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}

    proposal = proposal_for(text)
    proposal["proposal"]["contracts"][0]["fields"] = [["order_id"]]
    assert "v3.proposal.field_list" in {issue.code for issue in v3.validate_proposal(parsed, proposal)}


def test_populated_source_sections_cannot_be_silently_omitted_from_typed_proposal():
    text = sample()
    proposal = proposal_for(text)
    for key in ("questions", "inputs", "models", "transform", "outputs"):
        proposal["proposal"][key] = []
    proposal["provenance"] = {"v3:delivery": "platform_fixed"}
    proposal["source_spans"] = {}
    proposal["echo"]["coverage"] = ["v3:delivery"]
    codes = {issue.code for issue in v3.validate_proposal(v3.parse(text), proposal)}
    assert "v3.proposal.section_omitted" in codes
    assert "v3.provenance.section_uncovered" in codes


def test_contracts_match_every_source_guarantee_and_rule_and_reject_duplicate_ids():
    text = sample()

    proposal = proposal_for(text)
    proposal["proposal"]["contracts"][0]["guarantee"] = "A different guarantee."
    assert "v3.contract.content_mismatch" in {
        issue.code for issue in v3.validate_proposal(v3.parse(text), proposal)
    }

    proposal = proposal_for(text)
    proposal["proposal"]["inputs"][0]["expectations"][0]["id"] = "reconciles_to_inputs"
    assert "v3.contract.source_duplicate_id" in {
        issue.code for issue in v3.validate_proposal(v3.parse(text), proposal)
    }

    proposal = proposal_for(text)
    proposal["proposal"]["contracts"].append(dict(proposal["proposal"]["contracts"][0]))
    assert "v3.contract.duplicate_id" in {
        issue.code for issue in v3.validate_proposal(v3.parse(text), proposal)
    }


def test_approval_binds_source_and_typed_proposal_and_patch_revokes():
    text = sample()
    parsed = v3.parse(text)
    proposal = proposal_for(text)

    approved = v3.parse(v3.approve(parsed, proposal, base_hash=v3.semantic_hash(parsed)))
    assert approved.frontmatter.status == "approved"
    assert approved.frontmatter.approved_content_hash == v3.semantic_hash(approved)
    assert approved.frontmatter.approved_proposal_hash == v3.proposal_hash(proposal)
    assert not v3.validate_approval(approved, proposal)

    malicious_approved = proposal_for(text)
    malicious_approved["proposal"]["decisions"][0]["ruling"] = "Overwrite the prior locked decision."
    with pytest.raises(ValueError, match="locked_evidence_invalid"):
        v3.approve(
            approved,
            malicious_approved,
            base_hash=v3.semantic_hash(approved),
            locked_proposal=malicious_approved,
        )

    changed = v3.targeted_patch(
        approved,
        base_hash=v3.semantic_hash(approved),
        path="v3:inputs[orders].text",
        value="Load corrected orders from the monthly export.",
    )
    changed_doc = v3.parse(changed)
    assert changed_doc.frontmatter.status == "proposed"
    assert changed_doc.frontmatter.approved_content_hash is None
    assert changed_doc.frontmatter.approved_proposal_hash is None
    assert changed_doc.frontmatter.prior_approved_proposal_hash == v3.proposal_hash(proposal)
    with pytest.raises(ValueError, match="prior locked proposal evidence"):
        v3.approve(changed_doc, proposal, base_hash=v3.semantic_hash(changed_doc))
    changed_proposal = proposal_for(changed)
    reapproved = v3.parse(
        v3.approve(
            changed_doc,
            changed_proposal,
            base_hash=v3.semantic_hash(changed_doc),
            locked_proposal=proposal,
        )
    )
    assert reapproved.frontmatter.prior_approved_proposal_hash is None

    malicious = proposal_for(changed)
    malicious["proposal"]["decisions"][0]["ruling"] = "Overwrite the prior locked decision."
    assert "v3.decision.locked_evidence_invalid" in {
        issue.code
        for issue in v3.validate_proposal(changed_doc, malicious, locked_proposal=malicious)
    }


def test_approval_rejects_empty_required_sections_and_requires_all_headings():
    empty_transform = sample().replace(
        "## Transform\n\nGroup accepted orders by customer and month and sum their amounts.",
        "## Transform\n\n",
    )
    proposal = proposal_for(empty_transform)
    with pytest.raises(ValueError, match="v3.section.empty"):
        v3.approve(v3.parse(empty_transform), proposal, base_hash=v3.semantic_hash(empty_transform))

    missing_headings = sample()
    missing_headings = missing_headings.replace(
        "## Terms\n\n### Customer\n\nA person or organization responsible for an order.\n\n",
        "",
    )
    missing_headings = missing_headings.replace("## Decisions\n\n### Refund treatment\n\nRefunds are excluded until a timing rule is supplied.\n\n", "")
    missing_headings = missing_headings.replace("## Open Questions\n\n", "")
    assert {issue.code for issue in v3.validate(v3.parse(missing_headings))} == {"v3.section.missing"}


def test_blocking_open_question_prevents_approval_and_locked_decision_cannot_change():
    text = sample()
    parsed = v3.parse(text)
    locked = proposal_for(text)

    changed = proposal_for(text, open_questions=[{
        "id": "refund_timing",
        "question": "When should refunds be applied?",
        "blocking": True,
    }])
    with pytest.raises(ValueError, match="cannot approve"):
        v3.approve(parsed, changed, base_hash=v3.semantic_hash(parsed))

    changed = proposal_for(text)
    changed["proposal"]["decisions"][0]["ruling"] = "Include refunds immediately."
    issues = v3.validate_proposal(parsed, changed, locked_proposal=locked)
    assert "v3.decision.locked_conflict" in {issue.code for issue in issues}
    with pytest.raises(ValueError, match="locked_conflict"):
        v3.approve(parsed, changed, base_hash=v3.semantic_hash(parsed), locked_proposal=locked)


def test_reapproval_requires_prior_locked_proposal_evidence():
    text = sample()
    proposal = proposal_for(text)
    approved = v3.parse(v3.approve(v3.parse(text), proposal, base_hash=v3.semantic_hash(text)))
    with pytest.raises(ValueError, match="prior locked proposal evidence"):
        v3.approve(approved, proposal, base_hash=v3.semantic_hash(approved))

    proposed_decision = proposal_for(text)
    proposed_decision["proposal"]["decisions"][0]["status"] = "proposed"
    with pytest.raises(ValueError, match="v3.decision.unsettled"):
        v3.approve(v3.parse(text), proposed_decision, base_hash=v3.semantic_hash(text))


def test_proposal_hash_excludes_only_derived_hash_fields():
    proposal = proposal_for(sample())
    first = v3.proposal_hash(proposal)
    proposal["proposal_hash"] = "sha256:" + "0" * 64
    proposal["hashes"] = {"terms": "sha256:" + "1" * 64}
    assert v3.proposal_hash(proposal) == first


def test_v3_validator_and_lock_writer_snapshot_the_prose_and_proposal(tmp_path: Path):
    text = sample()
    proposal = proposal_for(text)
    spec = tmp_path / "dp-spec.md"
    proposal_path = tmp_path / "dp-spec.proposal.json"
    closure = tmp_path / "closure"
    proposal_path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    supplied_proposal_bytes = proposal_path.read_bytes()
    spec.write_text(
        v3.approve(v3.parse(text), proposal, base_hash=v3.semantic_hash(text)),
        encoding="utf-8",
    )

    validator = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_dp_spec.py"), str(spec), "--proposal", str(proposal_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validator.returncode == 0, validator.stderr
    assert json.loads(validator.stdout)["schema"] == "nxd-diagnostic-report-v3"

    writer = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "dp_diagnostics.py"),
            "lock", "write", str(spec), str(closure), "--proposal", str(proposal_path), "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert writer.returncode == 0, writer.stderr
    lock = json.loads(writer.stdout)
    assert lock["schema"] == "nxd-dp-spec-lock-v3"
    assert (closure / "dp-spec.approved.md").read_text() == spec.read_text()
    assert (closure / "dp-spec.proposal.approved.json").read_bytes() == supplied_proposal_bytes
    assert lock["terms_hash"]
    assert lock["contract_inventory_hash"]
    assert lock["locked_decisions_hash"]
    assert lock["delivery_profile"] == v3.FIXED_DELIVERY_PROFILE

    verifier = subprocess.run(
        [sys.executable, str(SCRIPTS / "dp_diagnostics.py"), "lock", "verify", str(closure), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verifier.returncode == 0, verifier.stderr
    assert json.loads(verifier.stdout)["ok"] is True

    record_init = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "dp_diagnostics.py"),
            "record", "init", "--record", str(closure / "build-record.json"),
            "--lock", str(closure / "dp-spec.lock.json"), "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert record_init.returncode == 0, record_init.stderr
    assert json.loads(record_init.stdout)["stages"]["s0_spec"]["status"] == "passed"

    tampered_proposal = json.loads((closure / "dp-spec.proposal.approved.json").read_text())
    tampered_proposal["proposal"]["terms"][0]["definition"] = "A changed definition."
    (closure / "dp-spec.proposal.approved.json").write_text(json.dumps(tampered_proposal) + "\n", encoding="utf-8")
    tampered_record_init = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "dp_diagnostics.py"),
            "record", "init", "--record", str(closure / "tampered-record.json"),
            "--lock", str(closure / "dp-spec.lock.json"), "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tampered_record_init.returncode == 2
    assert "typed proposal hash does not match the lock" in tampered_record_init.stderr
    (closure / "dp-spec.proposal.approved.json").write_bytes(supplied_proposal_bytes)

    valid_lock = dict(lock)
    lock["snapshot"] = "../foreign-spec.md"
    (closure / "dp-spec.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    escaping_record_init = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "dp_diagnostics.py"),
            "record", "init", "--record", str(closure / "escaping-record.json"),
            "--lock", str(closure / "dp-spec.lock.json"), "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert escaping_record_init.returncode == 2
    assert "escapes the closure" in escaping_record_init.stderr

    lock = valid_lock
    (closure / "dp-spec.lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    lock["terms_hash"] = "0" * 64
    lock["locked_decisions_hash"] = "0" * 64
    (closure / "dp-spec.lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    tampered = subprocess.run(
        [sys.executable, str(SCRIPTS / "dp_diagnostics.py"), "lock", "verify", str(closure), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tampered.returncode == 1
    assert "closure.terms_hash_mismatch" in {
        diagnostic["code"] for diagnostic in json.loads(tampered.stdout)["diagnostics"]
    }
    assert "closure.decision_inventory_mismatch" in {
        diagnostic["code"] for diagnostic in json.loads(tampered.stdout)["diagnostics"]
    }
    assert "Traceback" not in tampered.stderr


def test_v3_lock_verify_rechecks_contract_inventory_delivery_and_decision_locks(tmp_path: Path):
    text = sample()
    proposal = proposal_for(text)
    spec = tmp_path / "dp-spec.md"
    proposal_path = tmp_path / "proposal.json"
    closure = tmp_path / "closure"
    spec.write_text(v3.approve(v3.parse(text), proposal, base_hash=v3.semantic_hash(text)), encoding="utf-8")
    proposal_path.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")

    writer = subprocess.run(
        [sys.executable, str(SCRIPTS / "dp_diagnostics.py"), "lock", "write", str(spec), str(closure), "--proposal", str(proposal_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert writer.returncode == 0, writer.stderr
    lock = json.loads(writer.stdout)

    lock["contract_inventory_hash"] = "0" * 64
    (closure / "dp-spec.lock.json").write_text(json.dumps(lock) + "\n", encoding="utf-8")
    contract_result = subprocess.run(
        [sys.executable, str(SCRIPTS / "dp_diagnostics.py"), "lock", "verify", str(closure), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert contract_result.returncode == 1
    assert "closure.contract_inventory_hash_mismatch" in {
        item["code"] for item in json.loads(contract_result.stdout)["diagnostics"]
    }

    lock["contract_inventory_hash"] = json.loads(writer.stdout)["contract_inventory_hash"]
    lock["delivery_profile"] = "unsupported"
    (closure / "dp-spec.lock.json").write_text(json.dumps(lock) + "\n", encoding="utf-8")
    delivery_result = subprocess.run(
        [sys.executable, str(SCRIPTS / "dp_diagnostics.py"), "lock", "verify", str(closure), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert delivery_result.returncode == 1
    assert "closure.lock_unparseable" in {
        item["code"] for item in json.loads(delivery_result.stdout)["diagnostics"]
    }

    lock["delivery_profile"] = v3.FIXED_DELIVERY_PROFILE
    proposal["proposal"]["decisions"][0]["status"] = "proposed"
    (closure / "dp-spec.proposal.approved.json").write_text(json.dumps(proposal) + "\n", encoding="utf-8")
    (closure / "dp-spec.lock.json").write_text(json.dumps(lock) + "\n", encoding="utf-8")
    decision_result = subprocess.run(
        [sys.executable, str(SCRIPTS / "dp_diagnostics.py"), "lock", "verify", str(closure), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert decision_result.returncode == 1
    assert "closure.decision_inventory_mismatch" in {
        item["code"] for item in json.loads(decision_result.stdout)["diagnostics"]
    }


def test_malformed_proposal_json_returns_diagnostic_not_traceback(tmp_path: Path):
    spec = tmp_path / "dp-spec.md"
    spec.write_text(sample(), encoding="utf-8")
    proposal = tmp_path / "proposal.json"
    proposal.write_text("[]", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_dp_spec.py"), str(spec), "--proposal", str(proposal), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert report["proposal_hash"] is None
    assert "Traceback" not in result.stderr


def test_validate_cli_without_proposal_returns_json_without_traceback(tmp_path: Path):
    spec = tmp_path / "dp-spec.md"
    spec.write_text(sample(), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_dp_spec.py"), str(spec), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["proposal_hash"] is None
    assert "Traceback" not in result.stderr


def test_diagnostics_accepts_a_valid_failing_v3_report():
    diagnostic = {
        "schema": v3.DIAGNOSTIC_SCHEMA_ID,
        "code": "v3.section.empty",
        "path": "v3:transform",
        "severity": "error",
        "owner": "user",
        "control": "text",
        "stage": "s0_spec",
        "origin": "tool_computed",
        "message": "Transform is empty.",
    }
    report = {
        "schema": "nxd-diagnostic-report-v3",
        "tool": "validate_dp_spec",
        "target": "dp-spec.md",
        "ok": False,
        "counts": {"error": 1, "warning": 0, "info": 0},
        "spec_hash": "sha256:" + "0" * 64,
        "proposal_hash": None,
        "diagnostics": [diagnostic],
    }
    assert dpd.validate_report(report) == []


def test_authoring_validate_cli_without_proposal_returns_json_without_traceback(tmp_path: Path):
    spec = tmp_path / "dp-spec.md"
    spec.write_text(sample(), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "dp_spec_authoring.py"), "validate", str(spec), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["proposal_hash"] is None
    assert "Traceback" not in result.stderr


# --- the v2/v3 cross-generation boundary ------------------------------------
#
# `dp_diagnostics.canonical_object` dispatches on the version it sniffs, so v2
# call sites can now reach the v3 parser. Both tests below fail against the
# implementation that shipped the dispatch: the first with an unhandled
# `dp_spec_authoring.ParseError` in place of a report, the second with
# `ok: true` for a proposal that was never read.

def _v2_lock_closure(tmp_path: Path, snapshot_text: str) -> Path:
    """A v2-schema closure whose snapshot bytes match its lock."""
    closure = tmp_path / "closure"
    closure.mkdir()
    snapshot = closure / "dp-spec.approved.md"
    snapshot.write_text(snapshot_text, encoding="utf-8")
    lock = json.loads((REPO / "evals" / "tests" / "fixtures" / "golden-dp-spec.lock.json").read_text())
    lock["snapshot_sha256"] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    (closure / "dp-spec.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return closure


def test_v2_lock_verify_reports_an_unparseable_v3_snapshot_instead_of_raising(tmp_path: Path):
    closure = _v2_lock_closure(
        tmp_path,
        "---\ndp_spec_version: 3\nname: x\nworkflow: x\nstatus: approved\n---\n\n## Bogus\n",
    )
    report = dpd.verify_lock(closure).to_dict()
    assert report["ok"] is False
    assert "closure.lock_unparseable" in [d["code"] for d in report["diagnostics"]]
    assert dpd.validate_report(report) == []


def test_v2_lock_verify_reports_an_unparseable_v3_live_spec_instead_of_raising(tmp_path: Path):
    v2_source = (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8")
    closure = _v2_lock_closure(tmp_path, v2_source.replace("status: proposed", "status: approved"))
    live = tmp_path / "dp-spec.md"
    live.write_text(
        "---\ndp_spec_version: 3\nname: x\nworkflow: x\nstatus: proposed\n---\n\n## Bogus\n",
        encoding="utf-8",
    )
    report = dpd.verify_lock(closure, live).to_dict()
    assert report["ok"] is False
    assert "closure.live_spec_unparseable" in [d["code"] for d in report["diagnostics"]]
    assert dpd.validate_report(report) == []


def test_v2_lock_verify_still_crashes_on_nothing_for_a_well_formed_closure(tmp_path: Path):
    """The guard must not swallow the genuine hash comparison it wraps."""
    v2_source = (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8")
    closure = _v2_lock_closure(tmp_path, v2_source.replace("status: proposed", "status: approved"))
    report = dpd.verify_lock(closure).to_dict()
    assert "closure.spec_hash_mismatch" in [d["code"] for d in report["diagnostics"]]
    assert "closure.lock_unparseable" not in [d["code"] for d in report["diagnostics"]]


def test_validate_dp_spec_rejects_a_proposal_supplied_against_a_v2_spec(tmp_path: Path):
    spec = tmp_path / "dp-spec.md"
    spec.write_text(
        (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    proposal = tmp_path / "proposal.json"
    proposal.write_text('{"schema": "totally-wrong", "proposal": {}}', encoding="utf-8")
    report = vds.validate(spec, proposal)
    assert report["ok"] is False
    assert [d["code"] for d in report["diagnostics"]] == ["spec.proposal.unsupported"]
    assert dpd.validate_report(report) == []


def test_validate_dp_spec_still_accepts_a_v2_spec_without_a_proposal(tmp_path: Path):
    spec = tmp_path / "dp-spec.md"
    spec.write_text(
        (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    report = vds.validate(spec)
    assert report["ok"] is True
    assert dpd.validate_report(report) == []


def _approved_v2_spec(tmp_path: Path) -> Path:
    raw = (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8")
    parsed = v2.parse(raw)
    spec = tmp_path / "dp-spec.md"
    spec.write_text(v2.approve(parsed, base_hash=v2.semantic_hash(parsed)), encoding="utf-8")
    return spec


def test_lock_write_rejects_a_proposal_supplied_against_a_v2_spec(tmp_path: Path):
    """The mirror of `_write_v3_lock`'s "a v3 lock requires the proposal" guard.

    `lock write` is the command that writes the binding, so accepting a
    `--proposal` it never opens pins a closure the caller believes carries a
    proposal snapshot it does not have.
    """
    spec = _approved_v2_spec(tmp_path)
    proposal = tmp_path / "proposal.json"
    proposal.write_text('{"schema": "totally-wrong"}', encoding="utf-8")
    closure = tmp_path / "closure"
    closure.mkdir()
    lock, report = dpd.write_lock(spec, closure, proposal=proposal)
    assert report.ok is False
    assert [d.code for d in report.errors] == ["spec.proposal.unsupported"]
    assert lock == {}
    assert list(closure.iterdir()) == []


def test_lock_write_still_writes_a_v2_lock_without_a_proposal(tmp_path: Path):
    spec = _approved_v2_spec(tmp_path)
    closure = tmp_path / "closure"
    closure.mkdir()
    lock, report = dpd.write_lock(spec, closure, now_ms=1769904000000)
    assert report.ok is True, report.to_dict()
    assert lock["schema"] == "nxd-dp-spec-lock-v2"
    assert sorted(p.name for p in closure.iterdir()) == ["dp-spec.approved.md", "dp-spec.lock.json"]


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("v1", "---\ndp_spec_version: 1\nname: x\nworkflow: x\nstatus: proposed\n---\n", "spec.frontmatter.unsupported_version"),
        ("no frontmatter", "hello\n", "spec.parse.invalid"),
        ("broken frontmatter", "---\ndp_spec_version: \n", "spec.parse.invalid"),
    ],
)
def test_proposal_rejection_never_masks_the_reason_a_spec_cannot_be_read(
    tmp_path: Path, label: str, source: str, expected: str
):
    spec = tmp_path / "dp-spec.md"
    spec.write_text(source, encoding="utf-8")
    proposal = tmp_path / "proposal.json"
    proposal.write_text('{"schema": "totally-wrong"}', encoding="utf-8")
    report = vds.validate(spec, proposal)
    assert report["ok"] is False
    assert [d["code"] for d in report["diagnostics"]] == [expected], label


def test_the_rejected_proposal_message_names_only_a_parsed_version(tmp_path: Path):
    spec = tmp_path / "dp-spec.md"
    spec.write_text(
        (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    proposal = tmp_path / "proposal.json"
    proposal.write_text('{"schema": "totally-wrong"}', encoding="utf-8")
    message = vds.validate(spec, proposal)["diagnostics"][0]["message"]
    assert "dp_spec_version 2" in message
    assert "None" not in message


def test_canonical_object_raises_only_spec_read_error_for_a_bad_v3_source():
    """`SpecReadError` is the canonicalizer's single failure type.

    A caller that catches it must not also have to know the version dispatch
    can surface `dp_spec_authoring.ParseError` — that gap is what let the two
    verifier sites above escape uncaught.
    """
    bad = b"---\ndp_spec_version: 3\nname: x\nworkflow: x\nstatus: proposed\n---\n\n## Bogus\n"
    with pytest.raises(dpd.SpecReadError) as caught:
        dpd.canonical_object(bad)
    assert caught.value.reason == "unparseable"


def test_one_user_mistake_reports_one_code_across_both_commands(tmp_path: Path):
    """`--proposal` against a v2 spec is the same mistake at either command.

    A consumer keying on `code` should not have to learn a second vocabulary
    because the mistake was made at `lock write` rather than at `validate`.
    """
    spec = _approved_v2_spec(tmp_path)
    proposal = tmp_path / "proposal.json"
    proposal.write_text('{"schema": "totally-wrong"}', encoding="utf-8")
    closure = tmp_path / "closure"
    closure.mkdir()

    _, write_report = dpd.write_lock(spec, closure, proposal=proposal)
    validate_report = vds.validate(spec, proposal)

    assert [d.code for d in write_report.errors] == ["spec.proposal.unsupported"]
    assert [d["code"] for d in validate_report["diagnostics"]] == ["spec.proposal.unsupported"]
    assert [d.stage for d in write_report.errors] == ["s0_spec"]
    # The address must agree too: a form binds findings by `path`, so one code
    # at two paths is still two answers for one mistake.
    assert [d.path for d in write_report.errors] == ["v2:proposal"]
    assert [d["path"] for d in validate_report["diagnostics"]] == ["v2:proposal"]


def test_both_lock_generations_report_one_code_for_an_uncanonicalizable_live_spec(tmp_path: Path):
    """The v2 and v3 verifiers answer the same failure with the same code.

    Both closures are real and internally consistent; only the live spec they
    are verified against is the same unparseable v3 document.
    """
    live = tmp_path / "dp-spec.md"
    live.write_text(
        "---\ndp_spec_version: 3\nname: x\nworkflow: x\nstatus: proposed\n---\n\n## Bogus\n",
        encoding="utf-8",
    )

    v2_source = (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8")
    v2_closure = _v2_lock_closure(tmp_path, v2_source.replace("status: proposed", "status: approved"))
    v2_codes = [d["code"] for d in dpd.verify_lock(v2_closure, live).to_dict()["diagnostics"]]

    text = sample()
    proposal = proposal_for(text)
    v3_spec = tmp_path / "v3-dp-spec.md"
    v3_spec.write_text(v3.approve(v3.parse(text), proposal, base_hash=v3.semantic_hash(text)), encoding="utf-8")
    v3_proposal = tmp_path / "v3-proposal.json"
    v3_proposal.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
    v3_closure = tmp_path / "v3-closure"
    _, write_report = dpd.write_lock(v3_spec, v3_closure, proposal=v3_proposal)
    assert write_report.ok is True, write_report.to_dict()
    v3_report = dpd.verify_lock(v3_closure, live).to_dict()
    v3_codes = [d["code"] for d in v3_report["diagnostics"]]

    assert "closure.live_spec_unparseable" in v2_codes
    assert "closure.live_spec_unparseable" in v3_codes
    assert "closure.spec_snapshot_missing" not in v3_codes
    assert dpd.validate_report(v3_report) == []


def test_both_lock_generations_report_one_code_for_a_missing_live_spec(tmp_path: Path):
    """A missing live spec is the live spec's fault, not the snapshot's.

    The v2 verifier used to answer this with `closure.spec_snapshot_missing`
    addressed at `closure:dp-spec.approved.md` — a file that is present and
    intact — while v3, which has no pre-check, let the read raise and reported
    the live-spec code. Same fault, two answers.
    """
    missing = tmp_path / "does-not-exist.md"

    v2_source = (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8")
    v2_closure = _v2_lock_closure(tmp_path, v2_source.replace("status: proposed", "status: approved"))
    v2_report = dpd.verify_lock(v2_closure, missing).to_dict()

    text = sample()
    proposal = proposal_for(text)
    v3_spec = tmp_path / "v3-dp-spec.md"
    v3_spec.write_text(v3.approve(v3.parse(text), proposal, base_hash=v3.semantic_hash(text)), encoding="utf-8")
    v3_proposal = tmp_path / "v3-proposal.json"
    v3_proposal.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
    v3_closure = tmp_path / "v3-closure"
    dpd.write_lock(v3_spec, v3_closure, proposal=v3_proposal)
    v3_report = dpd.verify_lock(v3_closure, missing).to_dict()

    for report in (v2_report, v3_report):
        live = [d for d in report["diagnostics"] if d["code"] == "closure.live_spec_unparseable"]
        assert live, [d["code"] for d in report["diagnostics"]]
        assert live[0]["path"] == "spec"
        assert "closure.spec_snapshot_missing" not in [d["code"] for d in report["diagnostics"]]
        assert dpd.validate_report(report) == []


def test_validate_dp_spec_emits_only_registered_codes():
    """The direction the `spec.` table's comment used to claim was enforced.

    `Report.error` rejects an unknown code, but `validate_dp_spec.py` hand-builds
    its envelopes and bypasses that check — which is how `spec.parse.invalid` and
    `spec.frontmatter.unsupported_version`, the two most reachable outcomes of
    the validator, shipped unregistered. A consumer resolving `owner`, `control`
    or `summary` from the registry got a `KeyError` on the common failure.
    """
    source = (SCRIPTS / "validate_dp_spec.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'"code":\s*"(spec\.[a-z0-9_.]+)"', source))
    assert emitted, "the scan found no spec.* codes — the pattern has drifted"
    unregistered = sorted(code for code in emitted if code not in dpd.CODES)
    assert unregistered == [], f"validate_dp_spec.py emits unregistered codes: {unregistered}"


def test_registered_rows_agree_with_the_envelopes_that_emit_them():
    """A registry row that contradicts its emitter is worse than no row.

    The registry is where a form resolves the control to render; if the envelope
    says one thing and the row another, a consumer's behavior depends on which
    it happened to read.
    """
    source = (SCRIPTS / "validate_dp_spec.py").read_text(encoding="utf-8")
    blocks = re.findall(
        r'"code":\s*"(spec\.[a-z0-9_.]+)".*?"owner":\s*"([a-z]+)".*?"control":\s*"([a-z]+)"',
        source,
        flags=re.DOTALL,
    )
    assert blocks, "the scan found no emitter blocks — the pattern has drifted"
    for code, owner, control in blocks:
        assert dpd.CODES[code]["owner"] == owner, code
        assert dpd.CODES[code]["control"] == control, code

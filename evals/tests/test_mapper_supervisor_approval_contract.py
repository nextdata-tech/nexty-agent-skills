"""Keep standalone mapper consent distinct from Desktop run admission.

This is intentionally a static, deterministic contract test: it reads only the
shipped skill text and makes no network, provider, LLM, or supervisor call.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPER_CONTRACT = REPO_ROOT / "src" / "nxd-generate-data-product" / "mapper" / "CONTRACT.md"
FIELD_MAPPER = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "field-mapper.md"
PREFLIGHT = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "mapper-preflight.md"
SELF_CHECK = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "self-check.md"
WORKFLOW_V2 = REPO_ROOT / "src" / "nxd-run-job-loop" / "reference" / "workflow-v2.md"
REVIEW_CLOSURE = REPO_ROOT / "src" / "nxd-review-closure" / "SKILL.md"
E2E_RUNNER = REPO_ROOT / "src" / "nxd-generate-data-product" / "mapper" / "examples" / "e2e" / "run_e2e.py"
E2E_TRANSFORM = REPO_ROOT / "src" / "nxd-generate-data-product" / "mapper" / "examples" / "e2e" / "transform_main.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(path: Path) -> str:
    """Ignore Markdown line wrapping while keeping exact contract phrases."""
    return " ".join(_read(path).split())


def test_standalone_harness_still_requires_a_user_authored_grant() -> None:
    contract = _normalized(MAPPER_CONTRACT)
    field_mapper = _normalized(FIELD_MAPPER)

    assert "standalone field-mapper harness" in contract
    assert "user-authored `Grant`" in contract
    assert "`Grant.check` remains the pre-dispatch guard" in contract
    assert "`map_inputs` requires a user-authored `Grant`" in field_mapper


def test_normative_contract_publishes_the_bounded_call_adapter() -> None:
    contract = _normalized(MAPPER_CONTRACT)

    # Pins the signature as the INSTALLED harness has it. The previous pin
    # carried `allow_env=True, provider="anthropic"`, which the harness never
    # had — so this test was holding the defect in place rather than catching
    # it: a closure following the pinned signature omits `allow_env` and dies on
    # `credential_missing` with the key sitting in its environment.
    # `test_field_mapper_contract_drift.py` checks these defaults against the
    # package itself, so a future change fails there rather than being
    # re-pinned wrong here.
    assert (
        '`make_call(*, spec, grant, secrets=None, allow_env=False, '
        'provider=None, provider_model=None, provider_cwd=None) -> callable`'
    ) in contract
    assert "provider construction, credential resolution" in contract
    assert "allowlisted environment fallback" in contract
    assert "The adapter is synchronous" in contract or "`make_call` returns a synchronous callable" in contract
    assert "missing parsed body becomes `error_code = schema_reject`" in contract
    assert "use `make_call`" in contract


def test_desktop_treats_mapper_files_as_scope_proposals_not_authorization() -> None:
    field_mapper = _normalized(FIELD_MAPPER)

    assert "**scope proposal**" in field_mapper
    assert "It is never authorization by itself" in field_mapper
    assert "An agent must never author approval claims" in field_mapper
    for claim in ("`approved`", "`approved_by`", "`approval_id`", "`receipt`", "`signature`"):
        assert claim in field_mapper, f"Desktop contract must forbid {claim} claims"
    assert "not proof of human authorization on Desktop" in field_mapper


def test_desktop_mapper_flow_is_the_shipped_workflow_v2_requirement() -> None:
    field_mapper = _normalized(FIELD_MAPPER)

    # The pre-v2 text described the Desktop mapper as unsupported and a future
    # handler. It must not survive next to the shipped flow.
    for stale in (
        "future handler",
        "until a workflow-v2 mapper handler is shipped",
        "`credential_isolation: not_enforced`",
        "one-time browser capability",
    ):
        assert stale not in field_mapper, f"stale pre-v2 text: {stale}"

    assert "`mapper-confirmation-v1`" in field_mapper
    assert "`start_requirement`" in field_mapper
    assert "native OS dialog" in field_mapper
    assert "the only approval surface" in field_mapper
    assert "It contains no URL, token, capability or key" in field_mapper
    assert "`credential_isolation` reports `brokered`" in field_mapper
    # Both supervisor grant paths, and the refusal of both at once.
    assert "`contracts/mapper_grant.json`" in field_mapper
    assert "`contracts/mapper_spec_grant.json`" in field_mapper
    assert "When both grant files exist it refuses the closure" in field_mapper
    # Strict grant, refused before any prompt.
    assert "`provider` exactly `anthropic`" in field_mapper
    assert "`claude_cli`, `recorded` and `stub` are refused under supervision" in field_mapper
    for code in (
        "`workflow/mapper_scope_invalid`",
        "`workflow/mapper_approval_claims_rejected`",
        "`workflow/mapper_grant_exceeds_policy`",
        "`workflow/mapper_model_unpriced`",
    ):
        assert code in field_mapper, f"missing grant refusal code: {code}"
    assert "These failures never reach the user as a prompt" in field_mapper


def test_declared_data_scope_is_never_described_as_enforced() -> None:
    """D1: fields, document classes and PII are declared, reviewed, not enforced."""
    field_mapper = _normalized(FIELD_MAPPER)
    workflow = _normalized(WORKFLOW_V2)
    review = _normalized(REVIEW_CLOSURE)

    assert "**Declared data scope is not enforced.**" in field_mapper
    assert "Declared by the author (reviewed, not enforced)" in field_mapper
    assert "The supervisor does **not** enforce them" in workflow
    assert "Never tell the user that the declared field list limits what the transform sends" in workflow
    assert "**Declared fields are not enforced.**" in review
    assert "The supervisor does **not** restrict what the transform sends" in review


def test_scratch_contracts_on_mapper_outputs_are_advisory() -> None:
    """D4: stub-backed validation cannot verify mapped values."""
    for text in (_normalized(FIELD_MAPPER), _normalized(WORKFLOW_V2)):
        assert "`validation/mapper_output_unverified`" in text
        assert "Every other contract failure still fails" in text
        assert "proves wiring, not the quality of mapped values" in text


def test_workflow_recovery_table_fails_closed() -> None:
    workflow = _normalized(WORKFLOW_V2)

    for code in (
        "workflow/approval_declined",
        "workflow/approval_expired",
        "workflow/approval_cancelled",
        "workflow/approval_interrupted",
        "workflow/approval_cooldown",
        "workflow/approval_pending",
        "workflow/approval_ceiling_reached",
        "workflow/approval_surface_unavailable",
        "workflow/mapper_subject_changed",
        "workflow/mapper_integrity",
        "validation/mapper_approval_missing",
        "validation/mapper_subject_changed",
        "validation/mapper_ceiling_exceeded_in_scratch",
        "validation/mapper_grant_refused",
        "validation/mapper_provider_unavailable",
        "mapper_ceiling_reached",
        "mapper_request_refused",
    ):
        assert f"`{code}`" in workflow, f"recovery table misses {code}"
    assert "Never retry `start_requirement` in a loop" in workflow
    assert "Never widen a grant yourself" in workflow
    assert "You cannot approve, decline, extend, widen or reset an approval" in workflow
    assert "Never substitute a chat \"yes\" for the dialog" in workflow
    assert "never supply a key, token or base URL yourself" in workflow


def test_mapper_review_publication_has_one_deterministic_outcome_per_review() -> None:
    contract = _normalized(MAPPER_CONTRACT)
    field_mapper = _normalized(FIELD_MAPPER)

    for text in (
        "`ReviewOutcome`",
        "`mapper_review_outcomes`",
        "`applied`",
        "`rejected`",
        "`ignored`",
        "every durable review has exactly one outcome",
        "`.assert_review_audit_completeness()`",
    ):
        assert text in contract or text in field_mapper, f"missing review-audit contract: {text}"
    assert "does not authenticate the reviewer" in contract or "does not authenticate the reviewer" in field_mapper


def test_mapper_status_defines_a_safe_unknown_admission_default() -> None:
    preflight = _normalized(PREFLIGHT)

    assert "`unknown` unless the supervisor returned a structured outcome" in preflight
    assert "otherwise `PASS`, `FAIL`, or `unsupported` verbatim" in preflight


def test_generated_mapper_uses_the_budgeted_call_adapter_and_wire_shape() -> None:
    field_mapper = _normalized(FIELD_MAPPER)

    assert "`make_call` is the only supported provider seam" in field_mapper
    assert "Do not import `anthropic`" in field_mapper
    assert "return a raw SDK response" in field_mapper
    assert '"category": {' in field_mapper
    assert '"evidence"' in field_mapper
    assert "content-derived hash" in field_mapper


def test_public_e2e_example_does_not_bind_sdk_or_private_transport() -> None:
    source = _read(E2E_RUNNER)

    assert "from nxd.experimental.field_mapper import make_call" in source
    assert "return make_call(spec=spec, grant=grant, allow_env=True)" in source
    assert not re.search(r"^\s*(?:import anthropic\b|from anthropic import)\b", source, re.MULTILINE)
    for private_module in ("field_mapper.transport", "field_mapper.ledger"):
        assert private_module not in source


def test_public_e2e_examples_land_and_check_review_outcomes() -> None:
    for path in (E2E_RUNNER, E2E_TRANSFORM):
        source = _read(path)
        assert "mapper_review_outcomes" in source
        assert "assert_review_audit_completeness" in source
        assert "review_outcome_rows" in source

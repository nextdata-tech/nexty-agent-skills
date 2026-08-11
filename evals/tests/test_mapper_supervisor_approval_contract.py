"""Keep standalone mapper consent distinct from Desktop run admission.

This is intentionally a static, deterministic contract test: it reads only the
shipped skill text and makes no network, provider, LLM, or supervisor call.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPER_CONTRACT = REPO_ROOT / "src" / "nxd-generate-data-product" / "mapper" / "CONTRACT.md"
FIELD_MAPPER = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "field-mapper.md"
PREFLIGHT = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "mapper-preflight.md"
SELF_CHECK = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "self-check.md"


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


def test_desktop_treats_mapper_files_as_scope_proposals_not_authorization() -> None:
    field_mapper = _normalized(FIELD_MAPPER)

    assert "**untrusted scope proposals**" in field_mapper
    assert "only component that can turn that subject into an approval" in field_mapper
    for claim in ("`approved`", "`granted_by`", "receipt", "signature", "approval-id"):
        assert claim in field_mapper, f"Desktop contract must forbid {claim} claims"
    assert "not proof of human authorization in Desktop" in field_mapper


def test_preflight_and_phase_g_do_not_claim_desktop_authorization() -> None:
    preflight = _normalized(PREFLIGHT)
    self_check = _normalized(SELF_CHECK)

    assert "execution reachability only, not Desktop authorization" in preflight
    assert "never proves Desktop authorization, human consent, or credential isolation" in preflight
    assert "Desktop supervisor admission: PASS/FAIL/unsupported" in preflight
    assert "not a protected Desktop human-authorization check" in self_check
    assert "does **not** prove a human authorization" in self_check


def test_client_confirmation_is_the_only_surface_with_exact_subject_reuse_and_fail_closed_paths() -> None:
    field_mapper = _normalized(FIELD_MAPPER)

    assert "protected client-mediated" in field_mapper
    assert "protocol `2025-06-18` or newer" in field_mapper
    assert "`authorize_this_exact_subject`" in field_mapper
    assert "there is no OS dialog or secondary approval surface" in field_mapper
    assert "older protocol or without form elicitation" in field_mapper
    assert "`unsupported` is terminal for that client" in field_mapper
    assert "compatibility fallback" not in field_mapper
    assert "supervisor-owned macOS" not in field_mapper
    assert "native dialog" not in field_mapper
    assert "unchanged retry reuses that session approval without another interaction" in field_mapper
    assert "changed spec or proposed scope gets a new subject and must be confirmed again" in field_mapper
    assert "`mapper_subject_changed`" in field_mapper

    for confirmation in (
        "`declined`",
        "`cancelled`",
        "`timed_out`",
        "`failed`",
        "`unsupported`",
    ):
        assert confirmation in field_mapper, f"missing fail-closed confirmation: {confirmation}"
    for diagnostic in (
        "`kind: mapper_approval_required`",
        "`run_admitted: false`",
        "`credential_isolation: not_enforced`",
    ):
        assert diagnostic in field_mapper
    assert "Approval records are session-local" in field_mapper
    assert "do not enforce cumulative call/token/cost budgets across build attempts" in field_mapper


def test_generated_mapper_uses_the_budgeted_call_adapter_and_wire_shape() -> None:
    field_mapper = _normalized(FIELD_MAPPER)

    assert "`make_call` is the only supported provider seam" in field_mapper
    assert "Do not import `anthropic`" in field_mapper
    assert "return a raw SDK response" in field_mapper
    assert '"category": {' in field_mapper
    assert '"evidence"' in field_mapper
    assert "content-derived hash" in field_mapper

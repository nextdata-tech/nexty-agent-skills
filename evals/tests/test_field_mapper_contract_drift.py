"""The field-mapper docs against the installed harness (NEX / Linear closure).

Four claims in `mapper/CONTRACT.md` and `reference/field-mapper.md` did not
match `nxd.experimental.field_mapper` as installed. Each was found by a real
closure that judged Linear tickets inside its transform, and each failed in a
way that pointed away from the doc:

* `Grant.check(spec, inputs)` raises `TypeError` before any dispatch — the real
  signature is keyword-only `input_fields` / `document_classes`.
* `make_call(..., allow_env=True)` is documented as the default; it is `False`.
  A closure that follows the docs gets `credential_missing` for a credential
  that is present in the child's environment.
* `spec-id` prints the id of the BOUND spec, while
  `MapperSpec.load(p).mapper_spec_id` reports a different one. Anything
  comparing a correctly-authored grant against an unbound spec refuses it.
* `target_row_key` is a content hash, and nothing the harness returns carries
  the input identity back — so `target_row_key_for_input` is not optional for a
  caller, despite being absent from the documented public surface.

These tests assert the DOCS, not the harness: the harness is the oracle, so a
future release that changes one of these signatures should fail here and be
re-documented rather than silently drifting again.
"""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "src" / "nxd-generate-data-product"
CONTRACT = SKILL / "mapper" / "CONTRACT.md"
REFERENCE = SKILL / "reference" / "field-mapper.md"

# The DOC assertions below run everywhere and are what carries this change.
# Only the harness-oracle half needs the installed package, which CI has no
# wheel for — so it is skipped there rather than making the whole file vanish.
try:
    import nxd.experimental.field_mapper as fm
except Exception:  # noqa: BLE001 - absence is the only thing that matters
    fm = None

needs_harness = pytest.mark.skipif(
    fm is None, reason="installed nxd package required as the signature oracle"
)


def _normalized(path: Path) -> str:
    """Ignore Markdown line wrapping while keeping exact contract phrases.

    The negative assertions below ("this phrasing must be gone") are the ones
    that need it: against raw text they only fire while the sentence happens to
    sit on one physical line, so restoring the old wording and letting the
    paragraph reflow puts the residue back with a green suite. A reflow makes a
    POSITIVE assertion fail loudly, which is the safe direction; a negative one
    fails open. Same helper, and same reason, as
    `test_mapper_supervisor_approval_contract.py`.
    """
    return " ".join(path.read_text(encoding="utf-8").split())


def _contract() -> str:
    return _normalized(CONTRACT)


def _reference() -> str:
    return _normalized(REFERENCE)


# --- the four corrections -------------------------------------------------


@needs_harness
def test_grant_check_signature_matches_the_installed_harness():
    params = inspect.signature(fm.Grant.check).parameters
    assert "input_fields" in params and "document_classes" in params, (
        "the harness changed; re-document Grant.check rather than adapting to it"
    )


def test_grant_check_is_documented_with_keyword_only_params():
    """Ungated on purpose: CI has no nxd wheel, so an oracle-gated assertion
    would leave this correction uncarried anywhere CI can see."""
    contract = _contract()
    assert "Grant.check(spec, inputs)" not in contract, (
        "the documented form raises TypeError before any dispatch"
    )
    assert "input_fields=(), document_classes=()" in contract


@needs_harness
def test_allow_env_default_matches_the_installed_harness():
    assert inspect.signature(fm.make_call).parameters["allow_env"].default is False, (
        "harness changed; re-document the default"
    )


def test_allow_env_is_documented_as_opt_in():
    contract = _contract()
    # The SIGNATURE must not advertise a True default. Prose saying "only when
    # allow_env=True is passed" is the correction, not the defect.
    assert "secrets=None, allow_env=True" not in contract, (
        "the public-surface signature must not show a True default"
    )
    assert "secrets=None, allow_env=False" in contract
    assert "allow_env` defaults to False" in contract
    assert "credential_missing" in contract, (
        "name the symptom: a credential error for a credential that is present"
    )
    assert "OPT-IN" in _reference()
    # The twin sentence elsewhere in CONTRACT.md said "pass allow_env=False to
    # refuse", which only parses if the default permits — the belief this file
    # exists to correct. Nothing else catches that residue.
    assert "`allow_env=False` when ambient credentials must be refused" not in contract, (
        "that phrasing implies the default permits the environment fallback"
    )


@needs_harness
def test_no_returned_record_carries_identity():
    for record in (fm.MapperProposal, fm.MapperEvidence):
        names = {f.name for f in dataclasses.fields(record)}
        assert "identity" not in names and "input_id" not in names, (
            f"{record.__name__} now carries identity; the doc can be simplified"
        )


def test_row_key_round_trip_is_documented():
    contract = _contract()
    assert "target_row_key_for_input" in contract, (
        "the symbol a caller cannot do without must be in the public surface"
    )
    assert "not** your `input_id`" in contract
    assert "spec.grain.identity_fields" in contract, (
        "take the projection from the spec's grain, never a repeated literal"
    )


def test_ordinal_suffix_caveat_is_documented():
    """The recipe derives one key per input, which `ordinal_suffix` breaks."""
    contract = _contract()
    assert "ordinal_suffix" in contract and "duplicate_policy" in contract
    assert "assumes `duplicate_policy` is `reject`" in contract, (
        "state the policy the recipe assumes, or a caller under ordinal_suffix "
        "follows it verbatim and resolves nothing"
    )


def test_timestamp_columns_use_the_parameterized_nxd_type():
    contract = _contract()
    assert "| `value_timestamp` | `timestamp()` |" not in contract
    assert "| `override_value_timestamp` | `timestamp()` |" not in contract
    assert "timestamp(unit=DurationUnit.Microseconds)" in contract
    assert "import `DurationUnit` from `nxd.core.yaml_schemas`" in contract


def test_provider_default_is_documented_as_grant_resolved():
    contract = _contract()
    assert "bound to the grant" in contract, (
        "provider=None is not a hole — selection is bound to the grant, and a "
        "disagreeing override raises GrantError rather than winning"
    )
    assert "GrantError" in contract
    # Both refusal messages are quoted in the contract, which is what makes the
    # gated oracle's exact-string assertions cross-checkable rather than magic.
    assert "does not match the consented provider" in contract
    assert "does not match the consented model" in contract
    assert "name it." not in contract, "that read as a hard rule and was wrong"


@needs_harness
def test_provider_and_model_are_bound_to_the_grant():
    """The oracle for the binding claim — behavioural, not a source scan.

    An earlier revision asserted an error-message substring inside
    `inspect.getsource(make_call)`, which went green if the guard moved into the
    dispatch closure — and that seam is documented as lazy, so the move is
    plausible. Calling `make_call` with a mismatched override closes that: it
    tests the guarantee rather than where the code for it lives, and needs no
    network, since the pack ships grants and specs to bind against.

    Both assertions below still pin exact message text, so a rewording turns
    them red. That coupling is deliberate rather than residual: both phrases are
    quoted verbatim in `CONTRACT.md`, which makes them documented contract
    phrases a reviewer can cross-check — and a reworded message that the docs
    still quote is itself a drift worth failing on.
    """
    sample = (SKILL / "mapper" / "samples" / "01-row-scores")
    grant = fm.Grant.load(str(sample / "grant.json"))
    spec = fm.MapperSpec.load(str(sample / "spec.json"))

    # Sanity: the fixture must actually declare both, or the asserts below are
    # vacuous against a grant that never had a provider to disagree with.
    assert grant.provider and grant.model

    # Omitting them is the documented, working call.
    fm.make_call(spec=spec, grant=grant, allow_env=True)

    with pytest.raises(Exception) as provider_mismatch:
        fm.make_call(
            spec=spec, grant=grant, allow_env=True, provider=grant.provider + "-other"
        )
    assert "does not match the consented provider" in str(provider_mismatch.value), (
        "an explicit provider that disagrees with the grant must be REFUSED, "
        "not preferred — CONTRACT.md says consent binds it"
    )

    with pytest.raises(Exception) as model_mismatch:
        fm.make_call(
            spec=spec, grant=grant, allow_env=True, provider_model=grant.model + "-other"
        )
    assert "does not match the consented model" in str(model_mismatch.value), (
        "the provider_model half of the claim — previously asserted in the "
        "docs with no carrier at all"
    )


def test_the_spec_id_binding_trap_is_documented():
    reference = _reference()
    assert "BOUND spec" in reference
    assert "spec_mismatch" in reference, (
        "name the error a correctly-authored grant gets"
    )
    assert "harness_version" in reference


@needs_harness
def test_the_helper_actually_derives_the_documented_key():
    """The doc's recipe must work against the installed harness."""
    from nxd.experimental.field_mapper.mapper import target_row_key_for_input

    key = target_row_key_for_input(
        identity={"ticket_identifier": "NEX-873"},
        fields={"ticket_identifier": "NEX-873"},
        identity_fields=("ticket_identifier",),
    )
    assert isinstance(key, str) and key
    # Deterministic, and not simply the identity echoed back.
    again = target_row_key_for_input(
        identity={"ticket_identifier": "NEX-873"},
        fields={"ticket_identifier": "NEX-873"},
        identity_fields=("ticket_identifier",),
    )
    assert key == again
    assert key != "NEX-873", (
        "if the key ever equals the identity, the round-trip problem is gone "
        "and this whole section should be revisited"
    )

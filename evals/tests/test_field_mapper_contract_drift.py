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


def _contract() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _reference() -> str:
    return REFERENCE.read_text(encoding="utf-8")


# --- the four corrections -------------------------------------------------


@needs_harness
def test_grant_check_signature_matches_the_installed_harness():
    params = inspect.signature(fm.Grant.check).parameters
    assert "input_fields" in params and "document_classes" in params, (
        "the harness changed; re-document Grant.check rather than adapting to it"
    )
    assert "Grant.check(spec, inputs)" not in _contract(), (
        "the documented form raises TypeError before any dispatch"
    )
    assert "input_fields=(), document_classes=()" in _contract()


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

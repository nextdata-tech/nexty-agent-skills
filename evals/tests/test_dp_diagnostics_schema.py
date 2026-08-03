"""The diagnostic contract itself — one shape, one registry, three producers.

`validate_dp_spec.py`, `self_check.py` and the loop agent must agree on this
byte-for-byte, so it is pinned here rather than left to review. The registry is
CLOSED: a code is never renamed or repurposed, and a changed meaning is a new
code. The frozen list below is what makes "never renamed" mechanical — a rename
or a silent addition fails this test and has to be argued for in a diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-run-job-loop" / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dp_diagnostics as dpd  # noqa: E402

# The frozen snapshot of the code registry. Regenerating this is a deliberate
# act, not a side effect.
FROZEN_CODES = (
   'blocker.caps_exhausted', 'blocker.credential_required',
  'blocker.forbidden_assert_restates_arithmetic',
  'blocker.forbidden_handwritten_yaml', 'blocker.forbidden_manual_watermark',
  'blocker.forbidden_replace_disposition', 'blocker.open_question',
  'blocker.spec_edit_required', 'closure.build_record_hash_mismatch',
  'closure.build_record_invalid', 'closure.build_record_missing',
  'closure.canonical_hash_deferred', 'closure.contract_duplicate_name',
  'closure.contract_not_wired', 'closure.contract_spec_drift',
  'closure.contract_verifier_inert', 'closure.contract_verifier_malformed',
  'closure.contract_verifier_missing', 'closure.contract_verifier_secret',
  'closure.contract_verifier_unreferenced', 'closure.csv_root_invalid',
  'closure.escaping_reference', 'closure.gitignore_missing',
  'closure.gitignore_not_naming_profile', 'closure.input_service_mismatch',
  'closure.live_spec_diverged', 'closure.lock_missing',
  'closure.lock_snapshot_byte_mismatch', 'closure.lock_status_not_approved',
  'closure.lock_unparseable', 'closure.model_path_unresolved',
  'closure.port_storage_mismatch', 'closure.profile_driver_mismatch',
  'closure.profile_name_mismatch', 'closure.profile_service_missing',
  'closure.readme_missing', 'closure.resolved_ref_missing',
  'closure.sensitive_missing', 'closure.spec_hash_mismatch',
  'closure.spec_snapshot_missing', 'concession.assert_weakened',
  'concession.dependency_repinned', 'concession.derived_model_left_inert',
  'concession.incidental_column_dropped', 'concession.other',
  'concession.readback_uniform_unexplained', 'concession.retry_reduced_scope',
  'concession.sample_capped', 'concession.type_coerced',
  'concession.unverified_construct_accepted', 'env.connection_refused',
  'env.credential_missing', 'env.dependency_install_failed',
  'env.kernel_unavailable', 'env.not_ready_timeout', 'env.provision_failed',
  'env.remote_unreachable', 'env.supervisor_busy', 'heal.attempt_started',
  'heal.blocked', 'heal.caps_exhausted', 'heal.healed',
  'heal.healed_with_concessions', 'heal.retry_environmental',
  'meta.classification_unsettled', 'meta.stage_not_reached',
  'pin.build_failed', 'pin.no_endpoint', 'pin.spec_compile_error',
  'policy.decisions_column_missing', 'policy.decisions_csv_missing',
  'policy.decisions_not_base_model', 'policy.decisions_value_out_of_vocab',
  'policy.literal_duplicates_landed_value', 'publish.artifact_unavailable',
  'publish.release_unreadable', 'publish.resource_not_found',
  'publish.superseded', 'publish.trust_not_verified',
  'publish.workflow_not_found', 'reach.connector_shape_mismatch',
  'reach.connector_undeclared', 'reach.model_sdk_import',
  'reach.undeclared_transport', 'runtime.assert_failed',
  'runtime.base_models_mismatch', 'runtime.import_failed',
  'runtime.model_table_missing', 'runtime.remote_assert_failed',
  'runtime.remote_traceback', 'runtime.row_count',
  'runtime.transform_incomplete', 'runtime.transform_raised',
  'semantic.absent_vocabulary', 'semantic.distribution',
  'semantic.empty_result', 'semantic.query_error', 'semantic.truncated',
  'semantic.uniform_column', 'semantic.wrong_answer',
  'spec.approval.agent_authored_at_approved', 'spec.contract.bad_authority',
  'spec.contract.bad_name', 'spec.contract.bad_phase',
  'spec.contract.duplicate_name', 'spec.contract.inferred_in_spec',
  'spec.contract.no_authority', 'spec.contract.no_guarantee',
  'spec.contract.no_model', 'spec.contract.no_name', 'spec.contract.no_rule',
  'spec.contract.not_mapping', 'spec.contract.unbound_threshold',
  'spec.contract.unknown_model', 'spec.contract.wrong_phase',
  'spec.criteria.anchor_out_of_range', 'spec.criteria.bad_provenance',
  'spec.criteria.bad_scale', 'spec.criteria.bad_weight',
  'spec.criteria.incomplete_scale', 'spec.criteria.no_anchors',
  'spec.criteria.no_entries', 'spec.criteria.no_scale',
  'spec.criteria.no_weight', 'spec.criteria.weights_unbalanced',
  'spec.decision.bad_provenance', 'spec.decision.bad_status',
  'spec.decision.blocked_with_applies_to', 'spec.decision.duplicate_id',
  'spec.decision.missing_for_ruling', 'spec.decision.no_applies_to',
  'spec.decision.no_id', 'spec.decision.no_ruling',
  'spec.decision.ruling_uncovered', 'spec.decision.sample_rule_unrecorded',
  'spec.encoding.not_utf8', 'spec.frontmatter.approved_with_errors',
  'spec.frontmatter.bad_name', 'spec.frontmatter.bad_status',
  'spec.frontmatter.bad_version', 'spec.frontmatter.missing_key',
  'spec.frontmatter.rubric_version_missing', 'spec.frontmatter.unparseable',
  'spec.gate.no_rule', 'spec.gate.no_unknown', 'spec.gate.not_mapping',
  'spec.gate.unknown_is_fail', 'spec.judgment.bad_produced_by',
  'spec.judgment.bad_reruns', 'spec.judgment.evidence_disabled',
  'spec.judgment.no_entries', 'spec.judgment.no_generator_model',
  'spec.judgment.no_model', 'spec.judgment.no_rubric_version',
  'spec.model.bad_kind', 'spec.model.bad_name', 'spec.model.duplicate_name',
  'spec.model.no_description', 'spec.model.no_entries', 'spec.model.no_grain',
  'spec.model.no_key', 'spec.model.no_name', 'spec.model.unmotivated',
  'spec.open_question.answered_without_decision',
  'spec.open_question.bad_disposition', 'spec.open_question.no_question',
  'spec.open_question.not_mapping', 'spec.output.bad_kind',
  'spec.output.no_name', 'spec.output.not_mapping',
  'spec.output.unknown_model', 'spec.population.missing',
  'spec.population.not_mapping', 'spec.population.prose',
  'spec.prefill.empty_required_field', 'spec.question.unanswered',
  'spec.schedule.bad_trigger', 'spec.schedule.no_cron',
  'spec.schedule.no_cursor_field', 'spec.schedule.not_mapping',
  'spec.schedule.regrain_not_append_safe', 'spec.section.empty',
  'spec.section.missing', 'spec.section.unknown', 'spec.section.unparseable',
  'spec.source.bad_type', 'spec.source.credential_key_mapping',
  'spec.source.credential_value', 'spec.source.label_duplicate',
  'spec.source.label_missing', 'spec.source.no_entries',
  'spec.source.no_location', 'spec.source.no_scope',
  'spec.source.not_mapping', 'spec.verdict.band_no_verdict',
  'spec.verdict.band_unknown_verdict', 'spec.verdict.band_unreachable',
  'spec.verdict.missing', 'spec.verdict.no_precedence',
  'spec.verdict.no_values', 'spec.verdict.not_mapping',
  'spec.verdict.value_unreached', 'struct.agg_expression_forbidden',
  'struct.bad_infra_profile', 'struct.bad_kwarg', 'struct.bad_script_path',
  'struct.base_models_vs_data_dirs', 'struct.description_unreachable',
  'struct.import_not_public_dsl', 'struct.join_target_missing',
  'struct.join_to_model_kwarg', 'struct.malformed_service_ref',
  'struct.metric_first_arg_not_agg', 'struct.metric_in_model',
  'struct.metric_of_and_column', 'struct.missing_call',
  'struct.model_name_not_literal', 'struct.model_no_description',
  'struct.naming_invariant_promised_vs_models',
  'struct.naming_invariant_promised_vs_physical', 'struct.no_primary_key',
  'struct.port_no_storage', 'struct.port_not_duckdb',
  'struct.primary_key_takes_no_args', 'struct.promise_of_view',
  'struct.role_no_description', 'struct.semantic_tools_forbidden',
  'struct.unknown_agg', 'struct.unknown_dtype', 'struct.unverified',
  'struct.view_empty_schema', 'struct.view_field_not_metric_field'
)


SCHEMAS = {
    "diagnostic": dpd.DIAGNOSTIC_SCHEMA,
    "report": dpd.REPORT_SCHEMA,
    "record": dpd.BUILD_RECORD_SCHEMA,
    "lock": dpd.LOCK_SCHEMA,
}


def _diag(**overrides) -> dict:
    base = {
        "schema": "nxd-diagnostic-v1",
        "stage": "s0_spec",
        "code": "spec.criteria.incomplete_scale",
        "severity": "error",
        "owner": "agent",
        "origin": "tool_computed",
        "path": "spec:criteria[C1].anchors",
        "message": "scale 1-5 has no anchor for level(s) [2, 3, 4]",
        "evidence": {"expected": [1, 2, 3, 4, 5], "found": [1, 5]},
    }
    base.update(overrides)
    return base


# --- the schemas ------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_schema_is_serializable_and_identified(name):
    schema = SCHEMAS[name]
    json.dumps(schema)  # must round-trip; a set or a tuple key would not
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False, (
        "an unknown key is a producer bug, so every schema closes its object"
    )
    for key in schema["required"]:
        assert key in schema["properties"], f"{name}: required key {key} has no property"


def test_diagnostic_schema_matches_the_frozen_field_list():
    props = dpd.DIAGNOSTIC_SCHEMA["properties"]
    assert set(props) == {
        "schema", "stage", "code", "severity", "owner", "origin", "path",
        "message", "evidence", "fix",
    }
    assert dpd.DIAGNOSTIC_SCHEMA["required"] == [
        "schema", "stage", "code", "severity", "owner", "origin", "path", "message",
    ]
    assert props["stage"]["enum"] == list(dpd.STAGES)
    assert props["severity"]["enum"] == list(dpd.SEVERITIES)
    assert props["owner"]["enum"] == list(dpd.OWNERS)
    assert props["origin"]["enum"] == list(dpd.ORIGINS)


def test_the_nine_stages_and_the_offline_set():
    assert dpd.STAGES == (
        "s0_spec", "s1_structure", "s2_transform", "s3_closure", "s4_pin",
        "s5_serve", "s6_run", "s7_publish", "s8_answer",
    )
    assert sorted(dpd.STAGES) == list(dpd.STAGES), "lexicographic sort must equal pipeline order"
    assert all(int(s[1]) == i for i, s in enumerate(dpd.STAGES))
    assert dpd.OFFLINE_STAGES == {"s0_spec", "s1_structure", "s2_transform", "s3_closure"}


# --- the registry -----------------------------------------------------------

def test_code_list_is_frozen():
    assert sorted(dpd.CODES) == list(FROZEN_CODES), (
        "the code registry moved. A code is never renamed or repurposed — a "
        "changed meaning is a NEW code. Update FROZEN_CODES deliberately."
    )


def test_every_code_carries_a_full_registry_entry():
    for code, entry in dpd.CODES.items():
        assert dpd.CODE_RE.match(code), f"{code} breaks the code grammar"
        assert entry["stage"] in dpd.STAGES
        assert entry["severity"] in dpd.SEVERITIES
        assert entry["owner"] in dpd.OWNERS
        assert entry["control"] in dpd.CONTROLS
        assert isinstance(entry["agent_fillable"], bool)
        assert entry["summary"], f"{code} has no summary"
        assert entry["stage"] in entry["stages"]


def test_domain_invariants():
    """The domains whose owner and severity are absolutes."""
    for code, entry in dpd.CODES.items():
        if code.startswith("blocker."):
            assert entry["owner"] == "user" and entry["severity"] == "error", code
        if code.startswith("concession."):
            assert entry["owner"] == "agent" and entry["severity"] == "warning", code
        if code.startswith("heal.") or code.startswith("meta."):
            assert entry["severity"] == "info", code
        if code.startswith("env.") and code != "env.credential_missing":
            assert entry["owner"] == "environment", code


def test_credential_missing_is_owned_by_the_user_not_the_environment():
    """The remedy is 'supply a credential', so the user must act and must hear it."""
    assert dpd.CODES["env.credential_missing"]["owner"] == "user"


def test_pin_build_failed_is_agent_owned_by_construction():
    """Stage 4 masquerades as environment: Phase A cannot execute the builders,
    so a closure can pass it in full and still fail when the supervisor pins it."""
    assert dpd.CODES["pin.build_failed"]["owner"] == "agent"


def test_credential_codes_are_user_owned():
    """Only the user can decide whether a leaked secret must now be rotated, and
    silently rewriting the file would erase the evidence that it leaked."""
    assert dpd.CODES["spec.source.credential_value"]["owner"] == "user"
    assert dpd.CODES["spec.source.credential_key_mapping"]["owner"] == "user"


# --- construction rules -----------------------------------------------------

def test_owner_is_never_producer_overridable():
    bad = _diag(owner="user")
    problems = dpd.validate_diagnostic(bad)
    assert any("owner" in p for p in problems), problems


def test_severity_may_be_relaxed_downward_but_never_raised():
    relaxed = dpd.diagnostic(
        "spec.criteria.incomplete_scale", message="x", severity="warning"
    )
    assert relaxed.severity == "warning"
    with pytest.raises(dpd.DiagnosticError):
        dpd.diagnostic("spec.section.unknown", message="x", severity="error")


def test_unknown_code_is_rejected():
    with pytest.raises(dpd.DiagnosticError):
        dpd.diagnostic("spec.nope.invented", message="x")
    assert dpd.validate_diagnostic(_diag(code="spec.nope.invented"))


def test_unknown_key_is_a_producer_bug():
    assert dpd.validate_diagnostic(_diag(hint="extra"))


def test_a_code_may_not_be_emitted_at_an_arbitrary_stage():
    with pytest.raises(dpd.DiagnosticError):
        dpd.diagnostic("spec.section.missing", message="x", stage="s6_run")
    # ...but the codes that genuinely span the ladder may move.
    assert dpd.diagnostic(
        "env.connection_refused",
        message="x",
        stage="s6_run",
        origin="supervisor_reported",
        path="tool:build_data_product.error",
        evidence={"supervisor_detail": "ConnectionRefusedError"},
    ).stage == "s6_run"


# --- the relay criterion ----------------------------------------------------

def test_supervisor_reported_needs_the_verbatim_payload():
    """`origin` records who AUTHORED the claim, not who wrote the file."""
    problems = dpd.validate_diagnostic(
        _diag(
            stage="s6_run",
            code="env.connection_refused",
            owner="environment",
            origin="supervisor_reported",
            path="tool:build_data_product.error",
            evidence={},
        )
    )
    assert any("supervisor_detail" in p for p in problems), problems


def test_supervisor_reported_needs_a_tool_path():
    problems = dpd.validate_diagnostic(
        _diag(
            stage="s6_run",
            code="env.connection_refused",
            owner="environment",
            origin="supervisor_reported",
            path="closure:transform/main.py:14",
            evidence={"supervisor_detail": "ConnectionRefusedError"},
        )
    )
    assert any("producing tool" in p for p in problems), problems


def test_a_satisfying_relay_is_accepted():
    assert not dpd.validate_diagnostic(
        _diag(
            stage="s6_run",
            code="env.connection_refused",
            owner="environment",
            origin="supervisor_reported",
            path="tool:build_data_product.error",
            evidence={"supervisor_detail": "ConnectionRefusedError: [Errno 111]"},
        )
    )


# --- the report envelope ----------------------------------------------------

def test_tool_is_a_closed_enum_of_four():
    assert sorted(dpd.REPORT_TOOLS) == [
        "dp_diagnostics", "loop", "self_check", "validate_dp_spec"
    ]
    assert dpd.REPORT_TOOLS["validate_dp_spec"] == ("s0_spec",)
    assert dpd.REPORT_TOOLS["self_check"] == ("s1_structure", "s2_transform", "s3_closure")
    assert dpd.REPORT_TOOLS["loop"] == (
        "s4_pin", "s5_serve", "s6_run", "s7_publish", "s8_answer"
    )
    assert dpd.REPORT_TOOLS["dp_diagnostics"] == dpd.STAGES


def test_a_tool_may_not_carry_a_stage_it_cannot_produce():
    report = dpd.Report("validate_dp_spec", target="dp-spec.md")
    with pytest.raises(dpd.DiagnosticError):
        report.add(dpd.diagnostic("pin.build_failed", message="x"))
    problems = dpd.validate_report(
        {
            "schema": "nxd-diagnostic-report-v1",
            "tool": "self_check",
            "target": None,
            "ok": False,
            "counts": {},
            "spec_hash": None,
            "diagnostics": [_diag()],
        }
    )
    assert any("may not carry stage" in p for p in problems), problems


def test_report_envelope_shape():
    report = dpd.Report("validate_dp_spec", target="dp-spec.md", spec_hash="sha256:" + "0" * 64)
    report.error("no anchor for 2", code="spec.criteria.incomplete_scale", path="spec:criteria[C1].anchors")
    report.warn("prose", code="spec.population.prose", path="spec:population")
    payload = report.to_dict()
    assert payload["schema"] == "nxd-diagnostic-report-v1"
    assert payload["ok"] is False
    assert payload["counts"] == {"error": 1, "warning": 1, "info": 0}
    assert not dpd.validate_report(payload)


# --- redaction --------------------------------------------------------------

def test_redaction_is_applied_to_message_and_evidence():
    """A check that prints the secret it found turns a contained file leak into
    a transcript leak."""
    diag = dpd.diagnostic(
        "spec.source.credential_value",
        message="looks like a credential VALUE (api_key: sk-live-1234567890)",
        path="spec:sources",
        evidence={"found": "password= hunter2"},
    )
    assert "sk-live-1234567890" not in diag.message
    assert "hunter2" not in json.dumps(diag.evidence)
    assert "<redacted>" in diag.message


def test_redaction_leaves_placeholders_alone():
    assert dpd.redact("api_key: null") == "api_key: null"


def test_redaction_is_recursive_and_key_aware():
    redacted = dpd.redact(
        {
            "password": "bare-password",
            "nested": {
                "api_key": "bare-api-key",
                "token": "bare-token",
                "clientSecret": "bare-client-secret",
                "accessToken": "bare-access-token",
                "authToken": "bare-auth-token",
                "Authorization": "Bearer bare-header-token",
                "label": "retain this",
            },
            "items": [{"secret": "bare-secret", "count": 3}],
            "token_count": 7,
        }
    )

    assert redacted["password"] == "<redacted>"
    assert redacted["nested"]["api_key"] == "<redacted>"
    assert redacted["nested"]["token"] == "<redacted>"
    assert redacted["nested"]["clientSecret"] == "<redacted>"
    assert redacted["nested"]["accessToken"] == "<redacted>"
    assert redacted["nested"]["authToken"] == "<redacted>"
    assert redacted["nested"]["Authorization"] == "<redacted>"
    assert redacted["items"][0]["secret"] == "<redacted>"
    assert redacted["nested"]["label"] == "retain this"
    assert redacted["items"][0]["count"] == 3
    assert redacted["token_count"] == 7


# --- the path grammar -------------------------------------------------------

def test_identity_beats_index():
    assert dpd.entry_identity({"id": "C1", "name": "fit"}, 3) == "C1"
    assert dpd.entry_identity({"name": "scored_candidates"}, 3) == "scored_candidates"
    assert dpd.entry_identity({"decision_id": "verdict_bands"}, 3) == "verdict_bands"
    assert dpd.entry_identity({"model": "scored"}, 3) == "scored"
    assert dpd.entry_identity({"label": "ashby"}, 0) == "#0"


def test_spec_path_grammar():
    assert dpd.spec_path("criteria", "C1", "anchors") == "spec:criteria[C1].anchors"
    assert dpd.spec_path("frontmatter", None, "status") == "spec:frontmatter.status"
    assert dpd.spec_path("sources", "#0", "location") == "spec:sources[#0].location"

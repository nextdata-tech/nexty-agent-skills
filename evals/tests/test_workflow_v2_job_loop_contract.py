"""Pin the v2 supervisor construction contract in the shipped skills.

The supervisor owns admission and publication.  These tests intentionally read
the skills as text so an accidental return to the legacy build path or a
reordered policy/review step fails before a live scenario is run.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
JOB_LOOP = REPO_ROOT / "src" / "nxd-run-job-loop"
JOB_SKILL = JOB_LOOP / "SKILL.md"
GENERATOR_SKILL = REPO_ROOT / "src" / "nxd-generate-data-product" / "SKILL.md"
SEMANTIC_SKILL = REPO_ROOT / "src" / "nxd-build-semantic-data-product" / "SKILL.md"
LOCAL_INFERENCE = (
    REPO_ROOT
    / "src"
    / "nxd-build-semantic-data-product"
    / "reference"
    / "local-inference-handoff.md"
)
REVIEW_SKILL = REPO_ROOT / "src" / "nxd-review-closure" / "SKILL.md"
WORKFLOW_V2 = JOB_LOOP / "reference" / "workflow-v2.md"
PRE_CAPTURE_AUDIT = (
    REPO_ROOT
    / "src"
    / "nxd-generate-data-product"
    / "reference"
    / "pre-capture-audit.md"
)
SCHEDULING = JOB_LOOP / "reference" / "scheduling.md"
BUILD_RECORD = JOB_LOOP / "reference" / "build-record.md"
SOURCE_MATERIALIZATION = JOB_LOOP / "reference" / "source-materialization.md"
FAILURE_HANDLING = JOB_LOOP / "reference" / "failure-handling.md"


def _reachable_installed_docs() -> set[Path]:
    """Follow local Markdown links from the installed construction skills."""
    pending = [JOB_SKILL, GENERATOR_SKILL]
    seen: set[Path] = set()
    link_pattern = re.compile(r"\]\(([^)\s]+)")
    while pending:
        path = pending.pop()
        path = path.resolve()
        if path in seen or not path.is_file() or path.suffix != ".md":
            continue
        try:
            path.relative_to(SRC.resolve())
        except ValueError:
            continue
        seen.add(path)
        for raw_target in link_pattern.findall(path.read_text(encoding="utf-8")):
            target_name = raw_target.split("#", 1)[0].split("?", 1)[0]
            if not target_name or target_name.startswith(("http:", "https:", "mailto:")):
                continue
            target = (path.parent / target_name).resolve()
            if target.suffix == ".md":
                pending.append(target)
    return seen


def test_main_skills_stay_within_loader_limit_and_point_to_v2_reference():
    for skill in (JOB_SKILL, GENERATOR_SKILL):
        text = skill.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 500
    assert "reference/workflow-v2.md" in JOB_SKILL.read_text(encoding="utf-8")
    assert "reference/workflow-v2.md" in GENERATOR_SKILL.read_text(encoding="utf-8")


def test_source_discovery_inspects_declared_inputs_before_asking_for_a_path():
    job = JOB_SKILL.read_text(encoding="utf-8")
    materialization = SOURCE_MATERIALIZATION.read_text(encoding="utf-8")
    for text in (job, materialization):
        assert "supplied attachments" in text
        assert "declared workspace artifacts" in text
        assert "source profiles" in text
        assert "reference files" in text
        assert "Before asking" in text
    assert "NXD_EVAL_FIXTURE_DIR" not in job
    assert "NXD_EVAL_FIXTURE_DIR" not in materialization


def test_v2_construction_order_is_explicit():
    text = " ".join(WORKFLOW_V2.read_text(encoding="utf-8").split())
    ordered_markers = (
        "call `get_workflow_capabilities`",
        "call `prepare_workflow`",
        "call `advance_workflow` with `session_decision`",
        "Generate the closure only after this action succeeds",
        "call the indicated `capture` action",
        "exactly one built-in `Agent` or `Task` dispatch",
        "through `report_requirement`",
        "returned `start_requirement` action",
        "returned `start_run` action",
    )
    positions = [text.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions), "v2 actions must remain in dependency order"


def test_executable_job_loop_matches_v2_order_and_has_one_mandatory_review():
    text = " ".join(JOB_SKILL.read_text(encoding="utf-8").split())
    ordered_markers = (
        "call `get_workflow_capabilities`",
        "call `prepare_workflow`",
        "returned `session_decision` action",
        "Invoke **nxd-generate-data-product** after that gate succeeds",
        "returned `capture` action",
        "Run **exactly one mandatory review per capture generation**",
        "returned `report_requirement` action",
        "returned `start_requirement`",
        "returned `start_run`",
    )
    positions = [text.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions), "the executable skill must follow v2 dependency order"
    checkpoint = text[text.index("### Step 3b") : text.index("### Step 4")]
    assert "There is no skip" in checkpoint
    assert "mutable closure" in checkpoint
    assert "review-record.json" in checkpoint
    assert "reset, local correction, optional evidence if available, recapture" in checkpoint


def test_prepare_uses_exact_kind_and_supervisor_owned_approval_lifecycle():
    text = " ".join(JOB_SKILL.read_text(encoding="utf-8").split())
    step = text[text.index("### Step 3") : text.index("### Step 3b")]
    for marker in (
        '`kind: "generated-data-product"`',
        '`status: proposed`',
        "Never set `status: approved` or invent approval hashes",
        "write and validate `dp-blueprint.proposal.json`",
        "Omit `source_hash` from the caller-authored file and inline object",
        "the prepare request must carry the complete typed proposal object",
        "approval remains only through the returned `session_decision` consent action",
        "`session_decision` consent action",
        "every Decision is included in the exact echo-back",
        "may remain `status: proposed` until the user approves",
        "trusted materializer projects those Decisions to `locked` only after the subject-bound `session_decision`",
        "`locked` is an approval-derived snapshot state, not authorization by itself",
    ):
        assert marker in step
    assert step.index("call `prepare_workflow`") < step.index("returned `session_decision` consent action")


def test_prepare_wire_shape_binds_the_real_typed_proposal_before_consent():
    text = " ".join(WORKFLOW_V2.read_text(encoding="utf-8").split())
    prepare = text[text.index("## Prepare the prose blueprint") : text.index("## Relay consent and capture")]
    for marker in (
        "exact, real typed proposal JSON",
        "`dp-blueprint.proposal.json`",
        '"blueprint_path": "/host-visible/nxd-jobs/<workflow>/dp-blueprint.md"',
        '"typed_proposal": {',
        "Parse that complete object",
        "Parse that complete object and validate/bind it to the blueprint before consent",
        "Source spans are exact coordinates from the trusted parser",
        "the `.text` span covers the subsection body only",
        "Copy all four integers",
        "may include separator blank lines",
        "Do not trim or widen that range",
        "prepare_recovery_id",
        "inspect_prepare_recovery",
        "complete `source_spans` map",
        "regenerate the entire typed proposal",
        "legacy `validation_issue.expected_source_span`",
        "source_map_code",
        "v3.provenance.source_map_unavailable",
        "v3.provenance.source_map_oversized",
        "reparse the final blueprint",
        "replace the complete proposal file",
        "Do not claim generic filesystem atomicity",
        "Never guess, split, trim, widen, or alter typed values",
        "may remain `status: proposed` during prepare",
        "trusted materializer projects proposed Decisions to `locked` in the approved closure snapshot",
        "`locked` is an approval-derived snapshot state",
        "round-trip the complete JSON",
        "re-run strict proposal validation",
        "new globally unique `request_id` because the payload changed",
    ):
        assert marker in prepare, f"typed proposal prepare contract lost: {marker}"
    assert "typed_proposal_path" not in prepare
    assert "replace only that path's coordinates" not in prepare

    job = JOB_SKILL.read_text(encoding="utf-8")
    for marker in (
        "bounded `prepare_recovery_id`",
        "`inspect_prepare_recovery`",
        "regenerate the entire proposal",
        "v1-compatible location hint",
        "source_map_code",
        "reparse the final blueprint",
        "replace the complete proposal file",
        "Do not claim generic filesystem atomicity",
        "Never guess, split, trim, widen, or alter typed values",
    ):
        assert marker in job, f"live span-repair fallback lost: {marker}"
    assert "replace only that path's coordinates" not in job

    capture = text[text.index("## Relay consent and capture") : text.index("## Run and report the review")]
    assert capture.index("approval authorizes") < capture.index('"type": "capture"')
    for marker in (
        "dp-blueprint.approved.md",
        "dp-blueprint.proposal.approved.json",
        "dp-blueprint.lock.json",
        "trusted `self_check.py`",
        "agent-authored copies",
    ):
        assert marker in capture


def test_workflow_v2_contract_inventory_is_executable_and_exact():
    """The live B1 omission must be caught by the shipped instructions."""
    workflow = " ".join(WORKFLOW_V2.read_text(encoding="utf-8").split())
    job = " ".join(JOB_SKILL.read_text(encoding="utf-8").split())
    generator = " ".join(GENERATOR_SKILL.read_text(encoding="utf-8").split())

    workflow_markers = (
        "typed-v3 proposal's contract inventory is part of generation",
        "every `proposal.inputs[*].expectations[*]` and `proposal.outputs[*].promises[*]` entry",
        "exactly one verifier script",
        "exactly one matching `custom(...)` chain at its declared attachment and phase",
        "Carry the contract `id`, attachment, model, phase, guarantee, rule, and fields unchanged",
        "ordinary `.promise(model)` is only the schema/model promise",
        "capture/preflight reject a missing or extra inventory",
        "custom input expectation cannot execute on the CSV-first runtime",
        "never emit it as decorative unwired code",
        "do not invent contracts from inferred schema facts",
    )
    for marker in workflow_markers:
        assert marker in workflow, f"workflow-v2 contract inventory rule lost: {marker}"

    generation_step = job[job.index("### Step 3") : job.index("### Step 3b")]
    for marker in (
        "typed v3 contract inventory is executable handoff, not optional metadata",
        "every Input expectation and Output promise must become exactly one closure verifier",
        "matching `custom(...)` wiring at its declared attachment and phase",
        "ordinary `.promise(model)` never satisfies a custom contract",
    ):
        assert marker in generation_step, f"job-loop handoff contract lost: {marker}"

    generator_workflow = generator[generator.index("## Workflow") : generator.index("### Step 1")]
    for marker in (
        "Workflow-v2 contract inventory is a hard generation invariant.",
        "exactly one verifier script under `contracts/`",
        "matching `custom(...)` wiring at its declared attachment and phase",
        "supervisor capture and preflight reject both missing and extra inventory",
        "custom input expectation is unsupported on the CSV-first runtime",
        "Wire each output promise when its runtime is supported",
        "do not invent contracts from inferred schema facts",
    ):
        assert marker in generator_workflow, f"generator contract invariant lost: {marker}"

    invariants = generator[generator.index("## Invariants") :]
    assert "never optional decoration" in invariants
    assert "Capture/preflight reject missing, extra, placeholder, or unwired contracts" in invariants


def test_contract_inventory_mismatch_has_one_semantics_preserving_repair():
    text = " ".join(FAILURE_HANDLING.read_text(encoding="utf-8").split())
    for marker in (
        "closure.contract_inventory_mismatch",
        "one bounded mechanical repair",
        "approved proposal's semantics are unchanged",
        "Preserve the approval",
        "anchors",
        "changes semantics, Terms, contracts, delivery, or any typed proposal content",
        "fresh user approval",
        "ambiguous operator reply is not approval",
        "no unbounded repair loop",
    ):
        assert marker in text, f"bounded inventory repair rule lost: {marker}"


def test_generator_invariants_separate_authored_and_capture_owned_files():
    """Workflow-v2 must not ask the agent to create supervisor-owned records."""
    text = " ".join(GENERATOR_SKILL.read_text(encoding="utf-8").split())
    invariants = text[text.index("## Invariants") :]
    for marker in (
        "After supervisor capture, the retained closure contains the complete file set",
        "This is the captured result, not the pre-capture authored-tree requirement",
        "under workflow-v2, emit only",
        "Do not emit, initialize, verify, or require",
        "the supervisor materializes and validates those files during capture",
    ):
        assert marker in invariants, f"workflow-v2 ownership boundary lost: {marker}"

    authored = invariants[
        invariants.index("under workflow-v2, emit only") : invariants.index("Do not emit")
    ]
    assert "dp-blueprint.approved.md" not in authored
    assert "dp-blueprint.lock.json" not in authored
    assert "build-record.json" not in authored


def test_job_helper_is_bound_to_the_exact_staged_skill_release():
    text = " ".join(JOB_SKILL.read_text(encoding="utf-8").split())
    step = text[text.index("### Step 3") : text.index("### Step 3b")]
    for marker in (
        "exact staged skill pack",
        "metadata version must match",
        "missing or mismatched helper path stops the workflow",
        "never fall back to another cached plugin release",
    ):
        assert marker in step


def test_generator_distinguishes_optional_tables_and_physical_pii_exposure():
    text = " ".join(GENERATOR_SKILL.read_text(encoding="utf-8").split())
    for marker in (
        "valid header-only CSV is still an optional physical base model",
        "include it in both `PHYSICAL_MODELS` and `OPTIONAL_EMPTY_MODELS`",
        "Never change it to `.promise(...)` or omit the model",
        "do not mask a column in the physical DuckDB table or direct SQL",
        "project every sensitive column out before any dlt resource is yielded",
    ):
        assert marker in text


def test_pre_capture_audit_pins_output_privacy_and_decision_projection():
    """Keep the final closure audit explicit and reachable from both flows."""
    audit = " ".join(PRE_CAPTURE_AUDIT.read_text(encoding="utf-8").split())
    generator = GENERATOR_SKILL.read_text(encoding="utf-8")
    workflow = WORKFLOW_V2.read_text(encoding="utf-8")

    assert "reference/pre-capture-audit.md" in generator
    assert "../../nxd-generate-data-product/reference/pre-capture-audit.md" in workflow
    for marker in (
        "blueprint `Model`",
        "explicit blueprint `Output`",
        "ordinary DSL `.promise(model)`",
        "required physical materialization",
        "non-privacy",
        "share the DuckDB output",
        "before yielding",
        "closure README",
        "typed-v3",
        "`locked` | `confirmed`",
        "`proposed` | `proposed`",
        "ledger `blocked`",
        "`provenance = deferred`",
        "`user_confirmed`",
        "`agent_authored`",
        "`source_derived`",
        "`deferred`",
        "`approved`, `settled`",
        "`operator_accepted`, or `user_approved`",
        "external `review-record.json`",
        "session-only decisions",
        "blueprint amendment and fresh user reapproval",
        "one ledger row per approved typed Decision",
    ):
        assert marker in audit, f"pre-capture audit marker lost: {marker}"
    assert "Batch same-round mechanical" in workflow
    assert "typed `locked` becomes ledger `confirmed`" in generator


def test_reviewer_checks_semantic_and_direct_store_disclosure_early():
    text = " ".join(REVIEW_SKILL.read_text(encoding="utf-8").split())
    output = text[text.index("### 3. An output promise") : text.index("### 4. A metric")]
    for marker in (
        "promised output",
        "exposed port",
        "physical table",
        "governed semantic discovery",
        "direct DuckDB/raw-table access",
        "Judge the captured code and schemas",
    ):
        assert marker in output


def test_local_inference_is_data_only_until_supervisor_consent():
    """The shared semantic skill must not turn inference into early codegen."""
    semantic = " ".join(SEMANTIC_SKILL.read_text(encoding="utf-8").split())
    assert "reference/local-inference-handoff.md" in semantic
    local_flow = " ".join(LOCAL_INFERENCE.read_text(encoding="utf-8").split())
    for marker in (
        "`schema.json`",
        "`semantic-model-plan.json`",
        "never under `closure/`",
        "Stop after returning those two inference artifacts",
        "Do not create or edit `models.py`, `spec.py`, `transform/`, `requirements.txt`",
        "successful supervisor `session_decision`",
    ):
        assert marker in local_flow, f"local inference boundary lost: {marker}"

    job_loop = " ".join(JOB_SKILL.read_text(encoding="utf-8").split())
    inference = job_loop[job_loop.index("### Step 2") : job_loop.index("### Step 3")]
    for marker in (
        "`semantic-model-plan.json`",
        "outside `closure/`",
        "must not create or edit `models.py`, `spec.py`",
        "must not invoke the generator",
    ):
        assert marker in inference, f"job-loop inference boundary lost: {marker}"


def test_generator_is_dispatched_only_after_successful_session_decision():
    text = " ".join(JOB_SKILL.read_text(encoding="utf-8").split())
    prepared = text.index("Do not present an approval prompt or ask for approval until `prepare_workflow` succeeds")
    consent = text.index("successful returned `session_decision` action is the generation gate", prepared)
    generation = text.index("Invoke **nxd-generate-data-product**", consent)
    capture = text.index("returned `capture` action", generation)
    assert prepared < consent < generation < capture


def test_v2_path_has_no_legacy_construction_fallback():
    text = " ".join(WORKFLOW_V2.read_text(encoding="utf-8").split())
    gate = text[text.index("## Gate on the connected capability") : text.index("## Prepare the prose blueprint")]
    assert "execution_enabled: true" in gate
    assert "build_data_product" not in gate
    assert "validate_data_product" not in gate
    assert "local substitute" in gate
    assert "blocker" in gate
    assert "direct supervisor CLI" in gate


def test_removed_construction_tools_are_absent_from_reachable_installed_docs():
    """Installed construction references must not teach removed MCP tools."""
    reachable = _reachable_installed_docs()
    expected = {
        WORKFLOW_V2.resolve(),
        JOB_LOOP.joinpath("reference", "catalog-resources.md").resolve(),
        JOB_LOOP.joinpath("reference", "context-and-resume.md").resolve(),
        JOB_LOOP.joinpath("reference", "failure-handling.md").resolve(),
        JOB_LOOP.joinpath("reference", "handoff-export.md").resolve(),
        JOB_LOOP.joinpath("reference", "source-materialization.md").resolve(),
        REPO_ROOT.joinpath(
            "src", "nxd-generate-data-product", "reference", "closure-record.md"
        ).resolve(),
    }
    assert expected <= reachable, "the construction references must remain reachable from installed skills"

    removed_tools = (
        "build_data_product",
        "validate_data_product",
        "get_mapper_approval_status",
    )
    violations: list[str] = []
    for path in sorted(reachable):
        lowered = path.read_text(encoding="utf-8").lower()
        mentioned = [term for term in removed_tools if term in lowered]
        if mentioned:
            violations.append(f"{path}: {', '.join(mentioned)}")
    assert not violations, "removed construction tools remain in installed docs: " + "; ".join(violations)


def test_review_relay_preserves_ledger_and_supervisor_boundary():
    text = " ".join(WORKFLOW_V2.read_text(encoding="utf-8").split())
    review = text[text.index("## Run and report the review") : text.index("## Follow returned actions through admission")]
    for marker in (
        "review_input",
        "several `RequirementView` entries",
        "whose `requirement_id` is the requirement id of the returned review action",
        "matching view",
        "retained blueprint path",
        "retained capture root",
        "nxd-review-closure",
        "nxd-conversation-review-v1",
        "rich review ledger",
        "review-record.json",
        "HIGH",
        "MEDIUM",
        "LOW",
        'severity: "blocking"',
        'severity: "advisory"',
        "Rejected, indeterminate, and findings reports remain unsatisfied",
        "never turn them into `clear`",
    ):
        assert marker in review, f"review relay contract lost: {marker}"


def test_review_dispatch_is_one_conversation_child_with_the_canonical_marker():
    """Capture must cause a real Agent/Task handoff, not an inline Skill call."""
    text = " ".join(WORKFLOW_V2.read_text(encoding="utf-8").split())
    review = text[text.index("## Run and report the review") : text.index("## Follow returned actions through admission")]
    for marker in (
        "exactly one built-in `Agent` or `Task` dispatch",
        "`general-purpose` subagent is acceptable",
        "conversation child, not a supervisor/MCP operation",
        "load and follow `nxd-review-closure`",
        "retained_capture_root: <exact retained_capture_root from review_input>",
        "retained_blueprint_path: <exact retained_blueprint_path from review_input>",
        "Sanitized original request: <complete request with credentials replaced>",
        "Load and follow nxd-review-closure.",
        "main thread must not invoke `Skill(nxd-review-closure)`",
        "canonical marker line",
        'NXD_REVIEW_DISPATCH {"closure_path":"closure","request_contract":"sanitized_original_request","return":"claims_only","review_round_index":0}',
        "`run_in_background: false`",
        "timeout or partial child result does not justify dispatching a second reviewer",
        "Reporting is the main thread's relay step",
    ):
        assert marker in review, f"explicit review-dispatch boundary lost: {marker}"
    assert review.count("NXD_REVIEW_DISPATCH") == 1


def test_review_role_and_job_loop_ban_inline_or_supervisor_launched_review():
    """The role boundary must survive both the orchestrator and reviewer docs."""
    job = " ".join(JOB_SKILL.read_text(encoding="utf-8").split())
    reviewer = " ".join(REVIEW_SKILL.read_text(encoding="utf-8").split())
    checkpoint = job[job.index("### Step 3b") : job.index("### Step 4")]
    for text in (checkpoint, reviewer):
        lowered = text.casefold()
        assert "must not" in lowered
        assert "inline" in lowered
        assert "supervisor" in lowered
        assert "conversation" in lowered
    assert "Skill(nxd-review-closure)" in checkpoint
    assert "report_requirement" in reviewer


def test_advance_wire_shapes_are_pinned_exactly():
    text = WORKFLOW_V2.read_text(encoding="utf-8")
    for marker in (
        '"expected_revision"',
        '"action": {',
        '"type": "session_decision"',
        '"type": "capture"',
        '"type": "report_requirement"',
        '"type": "start_requirement"',
        '"type": "start_run"',
        '"expected_invalidation_epoch"',
        '"dependency_evidence_sha256"',
        '"message_ref": null',
        'exactly `{ "id", "severity", "description" }`',
    ):
        assert marker in text, f"strict workflow wire field lost: {marker}"
    assert "globally unique" in text


def test_admission_and_reset_never_use_local_completion_or_undo_claims():
    text = " ".join(WORKFLOW_V2.read_text(encoding="utf-8").split())
    admission = text[text.index("## Follow returned actions through admission") :]
    assert "current `revision` and `invalidation_epoch`" in admission
    assert "Do not claim completion from closure files" in admission
    reset = text[text.index("## Reset after behavior changes") :]
    assert "reset_workflow" in reset
    assert "does not undo" in reset


def test_capture_is_immutable_and_remediation_creates_a_new_review_generation():
    text = " ".join(WORKFLOW_V2.read_text(encoding="utf-8").split())
    assert text.index("approval authorizes") < text.index('"type": "capture"')
    for marker in (
        "dp-blueprint.proposal.approved.json",
        "the trusted `self_check.py`",
        "Agent-authored copies of those reserved surfaces are rejected",
        "agent-side self-check and lock verification are optional evidence only",
    ):
        assert marker in text
    assert "Do not mutate that authoring tree" in text
    assert "one retained-input review per capture generation" in text
    assert "reset the returned capture requirement" in text
    assert "recapture it, and run a fresh review" in text
    assert "Never write a review result into the captured closure" in text


def test_harness_attestations_use_the_exact_sidecar_path_and_schema():
    text = " ".join(WORKFLOW_V2.read_text(encoding="utf-8").split())
    for marker in (
        "persist the short construction attestations before `start_run`",
        "exact path in `NXD_EVAL_ATTESTATIONS_PATH`",
        "`agent-attestations.json` at the agent workspace root",
        "root JSON array",
        '"action_kind":"self_check"',
        '"evidence_ref":"nxd-jobs/<workflow>/closure/build-record.json#self_check"',
        '"action_kind":"adversarial_review"',
        '"evidence_ref":"nxd-jobs/<workflow>/review-record.json#review_rounds/<index>"',
        '"review_round_index":<index>',
        "Replace only `<workflow>` and `<index>`",
        "relative to the agent workspace root",
        "one indexed review attestation for every external `review_rounds[]` entry",
        "Do not place it under `closure/`, `artifacts/`, or the review ledger",
    ):
        assert marker in text, f"harness attestation contract lost: {marker}"
    assert "no other keys" in text


def test_scheduling_reference_uses_the_same_mandatory_immutable_review_contract():
    text = " ".join(SCHEDULING.read_text(encoding="utf-8").split())
    checkpoint = text[text.index("## Main-thread review checkpoint") :]
    for obsolete in (
        "Verify these three skip predicates",
        "build-record.json#review_rounds",
        "Step 4 must refuse check_data_product and build_data_product",
    ):
        assert obsolete not in checkpoint
    assert "Finish the generator handoff before capture" in checkpoint
    assert "external `review-record.json` ledger" in checkpoint
    assert "exactly one built-in read-only `Agent` or `Task` review per capture generation" in checkpoint
    assert "reset, local correction, optional" in checkpoint


def test_build_record_never_places_post_capture_review_inside_the_closure():
    text = " ".join(BUILD_RECORD.read_text(encoding="utf-8").split())
    for marker in (
        "`…/nxd-jobs/<workflow>/review-record.json`, outside every captured closure",
        "required, reserved empty array",
        "Workflow v2 must not append review data to it",
        "exactly one round per capture generation",
        "`build-record.json` remains unchanged",
    ):
        assert marker in text, f"immutable review-record boundary lost: {marker}"
    assert "Every adversarial review appends one `review_rounds[]`" not in text


def test_build_record_diagnostics_use_only_v2_supervisor_operations():
    text = BUILD_RECORD.read_text(encoding="utf-8")
    assert "build_data_product" not in text
    assert "tool:inspect_workflow.operation" in text
    assert "returned `start_requirement` action" in text
    assert "workflow/validation_failed" in text


def test_reviewer_skill_runs_only_on_supervisor_retained_post_check_inputs():
    text = " ".join(REVIEW_SKILL.read_text(encoding="utf-8").split())
    for marker in (
        "Supervisor capture materialized and verified the reserved metadata and trusted `self_check.py`",
        "exactly one review is required for a capture generation after supervisor capture",
        "`review_input.retained_capture_root`",
        "`review_input.retained_blueprint_path`",
        "Never substitute the mutable authoring root",
        "reset, correct locally, optionally check, recapture",
    ):
        assert marker in text, f"reviewer retained-input contract lost: {marker}"
    assert "before nxd-generate-data-product runs its Step 7 self-check" not in text

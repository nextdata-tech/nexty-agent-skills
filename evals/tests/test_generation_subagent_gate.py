"""Pin the workflow-v2 ownership and review-child boundaries.

The owning conversation must keep inference, generation, capture, and every
workflow MCP action together. The only allowed construction child is the
mandatory retained-capture reviewer. A live end-to-end run needs a real
supervisor (`ci_skip`), so this plain-pytest gate pins the guidance itself.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _closure_files import FILE_LIST, collapse

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

JOB_LOOP = SRC / "nxd-run-job-loop"
SKILL = JOB_LOOP / "SKILL.md"
SCHEDULING = JOB_LOOP / "reference" / "scheduling.md"
GENERATE_DP = SRC / "nxd-generate-data-product" / "SKILL.md"
ADVERSARIAL_REVIEW = SRC / "nxd-generate-data-product" / "reference" / "adversarial-review.md"
POLICY_GATE = SRC / "nxd-generate-data-product" / "reference" / "policy-gate.md"
BUILD_RECORD = JOB_LOOP / "reference" / "build-record.md"
SCRIPTS = JOB_LOOP / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from dp_diagnostics import validate_review_round  # noqa: E402


def _strip_markdown(text: str) -> str:
    # Drop emphasis/code markers so a rule written **bold** or `code` still
    # matches the plain phrase.
    return re.sub(r"[*`_]", "", text).lower()


def test_scheduling_keeps_inference_and_generation_on_the_main_thread():
    text = re.sub(r"\s+", " ", _strip_markdown(SCHEDULING.read_text()))
    assert "main-thread workflow-v2 scheduling" in text
    assert "main thread: inference" in text
    assert "main thread: generation" in text
    assert "do not fan out steps 2–3" in text or "do not delegate or fan out steps 2–3" in text
    assert "no child may perform a workflow mcp action" in text


def test_scheduling_keeps_build_single_flight_and_review_as_the_only_child():
    text = _strip_markdown(SCHEDULING.read_text())
    # Build/serve stays single-flight main-thread — never fanned out.
    assert "single-flight" in text
    assert "never fan out a build" in text
    assert "only permitted conversation child" in text
    assert "single retained-capture review" in text


def test_scheduling_pins_gate_on_main_thread_and_bounce():
    raw = SCHEDULING.read_text()
    text = re.sub(r"\s+", " ", _strip_markdown(raw))
    # The policy read-back is a MAIN-THREAD user turn; the subagent never opens
    # one and bounces on a new gap.
    assert "user turn is the orchestrator" in text or (
        "read-back" in text and "main thread" in text and "never happens inside a subagent" in text
    ), "scheduling.md must keep the policy read-back a main-thread user turn"
    # Assert on RAW text: _strip_markdown drops the underscore in gap_found.
    assert "gap_found" in raw, "scheduling.md must name the gap_found bounce return"


def test_scheduling_pins_credential_boundary():
    text = re.sub(r"\s+", " ", _strip_markdown(SCHEDULING.read_text()))
    # A live credential never enters a conversation child; the main thread
    # performs the host-side injection after authoring.
    assert "credential" in text and "never enters a conversation child" in text
    assert "main thread writes the real credential" in text
    assert "host-side" in text and "before capture" in text


def test_scheduling_pins_host_side_path_verification():
    text = _strip_markdown(SCHEDULING.read_text())
    # The main thread verifies the returned path resolves host-side before build.
    assert "host" in text and "verif" in text, (
        "scheduling.md must require host-side verification of the returned path"
    )
    assert "handoff failure" in text or "not a build input" in text, (
        "an unresolved host path must be a handoff failure, not a build input"
    )


def test_scheduling_pins_main_thread_workflow_ownership():
    text = re.sub(r"\s+", " ", _strip_markdown(SCHEDULING.read_text()))
    assert "owning main conversation" in text
    assert "no child may perform a workflow mcp action" in text
    assert "do not delegate steps 2–3" in text or "do not delegate or fan out steps 2–3" in text


def test_skill_wires_main_thread_generation_and_verify_before_capture():
    text = re.sub(r"\s+", " ", _strip_markdown(SKILL.read_text()))
    # SKILL.md keeps generation in the owning thread and verifies its path before
    # the supervisor captures the immutable review/validation input.
    collapsed = text
    assert "stay on the main thread for an activated workflow-v2 session" in collapsed, (
        "SKILL.md must keep workflow-v2 generation on the main thread"
    )
    assert "verify" in text and "host" in text and "before capture" in text, (
        "SKILL.md must verify the returned path host-side before v2 capture"
    )
    # The review child remains the only child and receives no credential.
    assert "only conversation child is the mandatory retained-capture review" in collapsed, (
        "SKILL.md must keep the review child boundary"
    )


def test_job_loop_declares_reviewer_tools_and_orders_review_before_admission():
    raw = SKILL.read_text()
    text = _strip_markdown(raw)
    assert "  - Agent" in raw and "  - Task" in raw
    assert raw.index("### Step 3b — Capture, review") < raw.index("### Step 4 — Build")
    checkpoint = text[text.index("### step 3b") : text.index("### step 4")]
    assert "exactly one" in checkpoint and "mandatory" in checkpoint
    assert "there is no skip" in checkpoint
    assert "retained" in checkpoint and "reviewinput" in checkpoint
    assert "reportrequirement" in checkpoint


def test_main_thread_generation_returns_to_supervisor_capture_before_review():
    raw = SCHEDULING.read_text()
    generation = raw.index("3. **Main thread: generation")
    optional_checks = raw.index("Step 7 checks are optional", generation)
    capture = raw.index("verification and capture", generation)
    review = raw.index("## Main-thread review checkpoint")
    assert generation < optional_checks < capture < review
    assert "supervisor materializes trusted metadata and checks during capture" in re.sub(
        r"\s+", " ", raw[generation:review]
    )
    assert "do not delegate" in raw[generation:review]


def test_build_record_review_round_example_is_strict_json_and_validated():
    section = BUILD_RECORD.read_text().split(
        "## Where conversation review lives", 1
    )[1].split("## `attempts[]` — the part that makes claims checkable", 1)[0]
    match = re.search(
        r"```json\n(?P<payload>\{\n  \"schema\": \"nxd-conversation-review-ledger-v1\",\n"
        r"  \"workflow\": .*?\n  \"review_rounds\": \[\n.*?\n  \]\n\}\n)```",
        section,
        flags=re.DOTALL,
    )
    assert match, "build-record.md must contain the anchored strict JSON example"
    document = json.loads(match.group("payload"))
    assert set(document) == {"schema", "workflow", "review_rounds"}
    assert len(document["review_rounds"]) == 1
    assert validate_review_round(document["review_rounds"][0]) == []


def test_generate_dp_teaches_subagent_gate_contract():
    raw = GENERATE_DP.read_text()
    text = _strip_markdown(raw)
    # The generator, when run as a subagent, never opens a user turn and bounces.
    assert "invoked as a generation subagent" in text, (
        "nxd-generate-data-product must address the generation-subagent invocation"
    )
    assert "you never open one" in text or "never open a user turn" in text or (
        "user turn is the orchestrator" in text
    ), "the generator subagent must never open a user turn"
    # Assert on RAW text: _strip_markdown drops the underscore in gap_found.
    assert "gap_found" in raw, "the generator subagent must bounce with gap_found"
    # It must not treat approval as a rubber stamp (the H1 unsoundness fix).
    assert "not a rubber stamp" in text, (
        "the gate must not be a rubber stamp when pre-approved — re-run the self-check"
    )


def test_generate_dp_direct_invocation_returns_to_job_loop():
    generator = GENERATE_DP.read_text()
    generator_direct = generator[
        generator.index("**Invoked directly**"):generator.index("**Invoked as a generation subagent**")
    ]
    policy = POLICY_GATE.read_text()
    policy_direct = policy[policy.index("## Invoked directly"):policy.index("## Invoked as a generation subagent")]
    for direct in (generator_direct, policy_direct):
        text = _strip_markdown(direct)
        assert "return to" in text and "nxd-run-job-loop" in text
        assert "immediately" in text
        assert "do not run" in text and "read-back" in text
        assert "run the read-back here" not in text


def test_generate_dp_declares_job_loop_dependency_for_selective_install():
    text = _strip_markdown(GENERATE_DP.read_text())
    assert "selective-install dependency" in text
    assert "selective install must include both skills" in text
    assert "nxd-run-job-loop" in text


# --- Meaning-pinning tests: a reworded-but-broken doc must FAIL these. ---

def test_bounce_covers_both_categories_not_just_absence():
    # H1: the bounce must fire on BOTH (a) a policy element absent from the
    # approved enumeration AND (b) a profiling finding that makes an approved
    # element ambiguous/conditional. Narrowing to absence-only is the exact H1
    # regression — so pin category (b) explicitly in both docs.
    for doc in (SCHEDULING, GENERATE_DP):
        text = _strip_markdown(doc.read_text())
        assert "ambiguous or conditional" in text, (
            f"{doc.name} must keep the category-(b) ambiguity bounce, not just absence"
        )
        collapsed = re.sub(r"\s+", " ", text)
        assert "absent from the enumeration" in collapsed or "element the enumeration never covered" in collapsed, (
            f"{doc.name} must keep the category-(a) absence bounce"
        )


def test_main_thread_verification_names_the_required_closure_files():
    raw = SCHEDULING.read_text()
    collapsed = collapse(raw)
    assert "The main thread verifies the handoff path before capture" in raw
    assert collapse(FILE_LIST) in collapsed
    assert "handoff failure" in raw


def test_credential_slots_are_key_names_only():
    text = _strip_markdown(SCHEDULING.read_text())
    assert "credential" in text and "never enters a conversation child" in text
    assert "main thread writes the real credential" in text
    assert "host-side" in text and "before capture" in text
    gen = _strip_markdown(GENERATE_DP.read_text())
    assert "hold no credential" in gen and "placeholder" in gen


def test_verify_list_enumerates_the_required_files():
    # H2/finding-5: the host-side verify must name the files, and MUST include
    # infra-profile.yaml (the file credential injection writes into) and the
    # three generated record files that replaced the retired prose doc.
    collapsed = collapse(SCHEDULING.read_text())
    assert collapse(FILE_LIST) in collapsed, (
        "scheduling.md must carry the frozen verify-before-build closure file "
        "list verbatim — an agent that verifies a different set ships a closure "
        "missing a file the other skill files name"
    )


def test_skill_keeps_steps_two_and_three_on_the_main_thread():
    collapsed = re.sub(r"\s+", " ", _strip_markdown(SKILL.read_text()))
    assert "stay on the main thread for an activated workflow-v2 session" in collapsed
    assert "do not delegate semantic inference, closure generation, or any workflow mcp action" in collapsed
    assert "only conversation child is the single retained-capture review" in collapsed


def test_file_profile_stays_in_the_main_thread():
    text = _strip_markdown(SCHEDULING.read_text())
    collapsed = re.sub(r"\s+", " ", text)
    assert "main thread: inference" in text
    assert "do not write the runnable closure" in collapsed
    assert "do not delegate profiling" in collapsed


def test_multi_question_dispatch_never_transfers_runtime_credentials():
    text = _strip_markdown(SCHEDULING.read_text())
    collapsed = re.sub(r"\s+", " ", text)
    # A child may query only through governed MCP tools that it already has; a
    # lead must not proxy the endpoint/bearer through prompt or result text.
    assert "describemodels" in text and "runsemanticquery" in text
    assert "available directly to that child" in collapsed
    assert "do not pass an endpoint or bearer" in text
    assert "main thread runs the governed queries sequentially" in collapsed
    assert "never falls back to raw sql, pandas, or shell aggregation" in collapsed


def test_adversarial_review_is_builtin_claims_only_dispatch():
    skill = _strip_markdown(GENERATE_DP.read_text())
    reference_raw = ADVERSARIAL_REVIEW.read_text()
    reference = _strip_markdown(reference_raw)
    # Step 6b is the entry contract; the reference supplies the full handoff.
    assert "dispatches exactly one built-in read-only reviewer" in skill
    assert "supervisor-provided retained capture" in skill
    assert "reportrequirement" in skill
    assert "reference/adversarial-review.md" in skill
    assert "one built-in read-only subagent" in reference
    assert "the closure path" in reference and "original request, verbatim" in reference
    assert "retained_capture_root: <exact retained_capture_root from review_input>" in reference_raw
    assert "retained_blueprint_path: <exact retained_blueprint_path from review_input>" in reference_raw
    assert "Sanitized original request: <complete request with credentials replaced>" in reference_raw
    assert "return claims only" in reference
    assert all(word in reference for word in ("never edits", "builds", "serves", "runs the transform", "user conversation"))


def test_adversarial_reference_does_not_invent_runner_timeout_records():
    reference = _strip_markdown(ADVERSARIAL_REVIEW.read_text())
    collapsed = re.sub(r"\s+", " ", reference)
    assert "do not invent a timeout record" in collapsed
    assert "workflow pending" in collapsed
    assert "120000 ms elapsed-time deadline" not in reference
    assert "budgetms: 120000" not in reference
    assert "no complexity-based skip" in collapsed

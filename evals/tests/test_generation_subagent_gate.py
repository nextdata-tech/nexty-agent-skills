"""Offloading generation to a subagent must be TAUGHT with its safety boundaries.

The job loop's heaviest context cost is source profiling + code generation
(Steps 2-3). Moving that into an isolated subagent keeps it out of the main
conversation — but only safely if the skill text pins four properties that a
naive "just fan out generation" would violate:

1. The policy read-back stays a MAIN-THREAD user turn; a subagent never opens
   one. On a new gap the subagent RETURNS `gap_found` instead of guessing.
2. A live credential never enters a subagent (prompt / return / narration); the
   subagent writes a placeholder and the real value is injected host-side.
3. The subagent-returned closure path is VERIFIED host-side before build — a
   subagent writes to its own surface and cannot guarantee host-visibility.
4. Offloading is PERMITTED, not required (a trivial 1-source loop authors inline),
   and build/serve stays single-flight on the main thread.

A live end-to-end run needs a real supervisor (`ci_skip`), so this plain-pytest
gate pins the guidance itself — the only thing that makes the agent behave.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

JOB_LOOP = SRC / "nxd-run-job-loop"
SKILL = JOB_LOOP / "SKILL.md"
SCHEDULING = JOB_LOOP / "reference" / "scheduling.md"
GENERATE_DP = SRC / "nxd-generate-data-product" / "SKILL.md"
ADVERSARIAL_REVIEW = SRC / "nxd-generate-data-product" / "reference" / "adversarial-review.md"
POLICY_GATE = SRC / "nxd-generate-data-product" / "reference" / "policy-gate.md"
BUILD_RECORD = JOB_LOOP / "reference" / "build-record.md"


def _strip_markdown(text: str) -> str:
    # Drop emphasis/code markers so a rule written **bold** or `code` still
    # matches the plain phrase.
    return re.sub(r"[*`_]", "", text).lower()


def test_scheduling_teaches_profile_generate_split():
    text = _strip_markdown(SCHEDULING.read_text())
    # The dispatch is split at the inference/authoring seam, not one Steps-2-3
    # unit — otherwise a bounce re-runs the expensive profiling.
    assert "profile subagent" in text, "scheduling.md must name a profile subagent"
    assert "generate subagent" in text, "scheduling.md must name a generate subagent"
    # And the reason for the split is stated: re-dispatch generation only.
    assert "never re-profiles" in text or "re-dispatches generation only" in text or (
        "re-dispatches" in text and "generation only" in text
    ), "scheduling.md must say a generation bounce re-dispatches generation only, not re-profile"


def test_scheduling_keeps_build_single_flight_and_offload_permitted():
    text = _strip_markdown(SCHEDULING.read_text())
    # Build/serve stays single-flight main-thread — never fanned out.
    assert "single-flight" in text
    assert "never fan out a build" in text
    # Offloading generation is permitted, not mandatory.
    assert "permitted, not required" in text, (
        "offloading generation must be permitted, not required"
    )


def test_scheduling_pins_gate_on_main_thread_and_bounce():
    raw = SCHEDULING.read_text()
    text = _strip_markdown(raw)
    # The policy read-back is a MAIN-THREAD user turn; the subagent never opens
    # one and bounces on a new gap.
    assert "user turn is the orchestrator" in text or (
        "read-back" in text and "main thread" in text and "never happens inside a subagent" in text
    ), "scheduling.md must keep the policy read-back a main-thread user turn"
    # Assert on RAW text: _strip_markdown drops the underscore in gap_found.
    assert "gap_found" in raw, "scheduling.md must name the gap_found bounce return"


def test_scheduling_pins_credential_boundary():
    text = _strip_markdown(SCHEDULING.read_text())
    # A live credential never enters a subagent; placeholder + host-side inject.
    assert "credential" in text and "placeholder" in text, (
        "scheduling.md must state the placeholder credential boundary"
    )
    assert "never receive" in text or "never enters a subagent" in text or (
        "host-side" in text and "before the build" in text
    ), "scheduling.md must forbid a live credential in a subagent and inject host-side"


def test_scheduling_pins_host_side_path_verification():
    text = _strip_markdown(SCHEDULING.read_text())
    # The main thread verifies the returned path resolves host-side before build.
    assert "host" in text and "verif" in text, (
        "scheduling.md must require host-side verification of the returned path"
    )
    assert "handoff failure" in text or "not a build input" in text, (
        "an unresolved host path must be a handoff failure, not a build input"
    )


def test_scheduling_pins_reference_scoping():
    text = _strip_markdown(SCHEDULING.read_text())
    # The subagent loads only the connector references it needs — the point of
    # offloading is that heavy references never touch the main thread.
    assert "loads only the matching" in text or (
        "connector type" in text and "loads only" in text
    ), "scheduling.md must scope each subagent's loaded references to the work at hand"


def test_skill_wires_subagent_and_verify_before_build():
    text = _strip_markdown(SKILL.read_text())
    # SKILL.md Step 3 offers the generation subagent and Step 4 verifies host-side.
    # Collapse whitespace so a line-wrapped "generation\nsubagent" still matches.
    collapsed = re.sub(r"\s+", " ", text)
    assert "generation subagent" in collapsed, (
        "SKILL.md must offer the generation subagent in Step 3"
    )
    assert "verify" in text and "host" in text and "before build" in text, (
        "SKILL.md Step 4 must verify the returned path host-side before building"
    )
    # The safety invariant is present: subagent never owns the policy turn / holds a credential.
    assert "never owns the policy turn and never holds a credential" in text, (
        "SKILL.md must carry the subagent policy-turn / credential invariant"
    )


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
        assert "absent from the enumeration" in text or "element the enumeration never covered" in text, (
            f"{doc.name} must keep the category-(a) absence bounce"
        )


def test_structured_return_contract_names_its_fields():
    # H2: the return must be structured and carry the fields the main thread
    # needs to narrate + build WITHOUT re-reading the closure. Pin each field by
    # name (raw text — _strip_markdown eats the underscores).
    raw = SCHEDULING.read_text()
    for field in ("closure_path", "promised_models", "policy_fingerprint",
                  "self_check", "credential_slots", "gap_found"):
        assert field in raw, f"scheduling.md return contract must name `{field}`"
    # The surface-tag distinction (a subagent cannot guarantee host-visibility).
    assert "host_absolute" in raw and "workspace_relative" in raw, (
        "the return must carry a surface tag distinguishing host vs workspace paths"
    )


def test_credential_slots_are_key_names_only():
    # H3: credential_slots must be key NAMES, never a value.
    text = _strip_markdown(SCHEDULING.read_text())
    assert "key names only" in text, (
        "scheduling.md must state credential_slots are key names only, never a value"
    )
    # A live credential is never given to a subagent; injected host-side instead.
    assert "never enters a subagent" in text or "never receive" in text, (
        "scheduling.md must forbid a live credential entering a subagent"
    )
    assert "host-side" in text and ("after the hand-back" in text or "before the build" in text), (
        "scheduling.md must inject the real credential host-side after hand-back"
    )
    # And the generator's own doc must restate it inline (reference-scoping steers
    # the subagent away from scheduling.md).
    gen = _strip_markdown(GENERATE_DP.read_text())
    assert "hold no credential" in gen and "placeholder" in gen, (
        "nxd-generate-data-product's subagent block must restate the placeholder credential rule inline"
    )


# §9 frozen verify-before-build closure file list. Line wrapping may differ, so
# compare whitespace-collapsed; wording may not differ at all.
VERIFY_LIST = (
    "`spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`, "
    "`requirements.txt`, `dp-spec.approved.md`, `dp-spec.lock.json`, "
    "`build-record.json`, `README.md`, the connector companion artifact — and, "
    "for a credentialed source, `SENSITIVE` and `.gitignore`"
)


def test_verify_list_enumerates_the_required_files():
    # H2/finding-5: the host-side verify must name the files, and MUST include
    # infra-profile.yaml (the file credential injection writes into) and the
    # three generated record files that replaced the retired prose doc.
    collapsed = re.sub(r"\s+", " ", SCHEDULING.read_text())
    assert re.sub(r"\s+", " ", VERIFY_LIST) in collapsed, (
        "scheduling.md must carry the frozen verify-before-build closure file "
        "list verbatim — an agent that verifies a different set ships a closure "
        "missing a file the other skill files name"
    )


def test_skill_offloads_two_subagents_not_one_unit():
    # Finding 4: SKILL.md must describe the profile/generate SPLIT, not one
    # combined Steps-2-3 subagent (which would re-profile on every bounce).
    collapsed = re.sub(r"\s+", " ", _strip_markdown(SKILL.read_text()))
    assert "profile subagent and a separate generate subagent" in collapsed or (
        "profile subagent" in collapsed and "generate subagent" in collapsed
        and "never one combined unit" in collapsed
    ), "SKILL.md must offload Steps 2-3 as two subagents split at the seam, not one unit"


def test_file_profile_dispatch_is_builtin_read_only_and_non_mutating():
    # The Desktop experiment proved that explicit skill prose can dispatch a
    # built-in agent. Keep file profiling on that narrow surface rather than
    # smuggling a custom plugin agent or a writer into the source-profile step.
    text = _strip_markdown(SCHEDULING.read_text())
    collapsed = re.sub(r"\s+", " ", text)
    assert "built-in read-only" in text
    assert "file source (csv/json/jsonl/parquet)" in text
    assert "source path" in text and "inference instructions" in text
    assert "writes no closure" in collapsed and "does not transform the source" in collapsed
    assert "asks the user nothing" in text


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
    reference = _strip_markdown(ADVERSARIAL_REVIEW.read_text())
    # Step 6b is the entry contract; the reference supplies the full handoff.
    assert "explicitly dispatch one built-in read-only reviewer" in skill
    assert "never a custom/plugin agent definition" in skill
    assert "closure path and verbatim request" in skill
    assert "return claims only" in skill
    assert all(word in skill for word in ("never edits", "builds", "serves", "transforms", "talks to the user"))
    assert "one built-in read-only subagent" in reference
    assert "the closure path" in reference and "original request, verbatim" in reference
    assert "return claims only" in reference
    assert all(word in reference for word in ("never edits", "builds", "serves", "runs the transform", "user conversation"))


def test_adversarial_deadline_records_partial_claims_without_a_finding_cap():
    reference = _strip_markdown(ADVERSARIAL_REVIEW.read_text())
    record = _strip_markdown(BUILD_RECORD.read_text())
    collapsed = re.sub(r"\s+", " ", reference)
    assert "120000 ms elapsed-time deadline" in reference
    assert "status: timedout" in reference and "budgetms: 120000" in reference
    assert "every partial claim received by then" in collapsed
    assert "no finding-count cap" in collapsed
    assert "client cannot cancel or collect" in collapsed and "stop the workflow as needsuser" in collapsed
    # `skipped` was never a legal review round status. Non-eligibility is no
    # dispatch, while a dispatched entry is complete/timed_out/needs_user.
    assert "skipped is not a review status" in collapsed
    assert "complete, timedout, or needsuser" in record
    assert "never skipped" in record

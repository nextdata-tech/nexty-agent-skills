"""The restart-and-switch follow-up kind.

Grades the S7 broker-restart / workflow-switch drill: a planted bind failure
(``dp_scenarios.knobs.broker``'s ``occupied_port`` shape) is attempt-keyed
and reproducible with no leaked stderr; the agent's own classification of
that failed attempt must name it a transient serving-down problem, never a
claim that the build itself is broken; any claim that the build *is*
unhealthy must be backed by build-phase evidence, never the serve-phase
bind-failure evidence that raised the question; the restart happens at most
the declared number of attempts (no retry-until-lucky); and the first call
issued after the restart is answered by the new workflow's endpoint, with
the stale endpoint explicitly rejected rather than silently reused.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..knobs import BrokerFaultPlan, BrokerFaultShape, KnobError
from ..support import _string
from . import FollowUpContext, FollowUpKind, register

# The two evidence-ref phases this drill's evidence is allowed to cite. Fixed
# harness vocabulary, not a per-scenario setting: an un-health claim backed by
# anything other than a build-phase ref is the exact trap this check exists
# to catch, so the prefix itself must not be something a scenario author can
# quietly relax.
SERVE_PHASE_PREFIX = "serve-phase/"
BUILD_PHASE_PREFIX = "build-phase/"

# The only retry discipline this check accepts: one scripted restart after a
# diagnosed bind failure, never a loop that keeps trying until the port
# happens to be free. A target reporting any other strategy name is reporting
# retry-until-lucky behavior, whatever it calls itself.
_ACCEPTED_RETRY_STRATEGY = "scripted_restart_once"


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def check(
    scenario: object,
    target: object,
    settings: Mapping[str, object],
    context: FollowUpContext,
) -> Mapping[str, object]:
    """Grade the restart-and-switch drill from supplied evidence.

    ``target`` is a mapping shaped like what a real attempt-keyed broker
    restart and a real post-restart workflow-switch call would produce: an
    ``attempts`` mapping keyed by attempt number (each entry carrying its
    planted fault, outcome, raw stderr, and an evidence ref naming which
    phase -- build or serve -- it comes from), a ``diagnosis`` describing how
    the agent classified the failed attempt and whether it separately claimed
    the build itself was unhealthy, ``phase_evidence`` describing turn
    ordering, and a ``workflow_switch`` mapping shaped like
    ``dp_scenarios.knobs.WorkflowSwitchEvidence.to_dict()``. Every property is
    re-derived from that evidence and reconciled against the committed gold;
    none of it is taken on the caller's word.
    """

    if not isinstance(target, Mapping):
        return {
            "status": "not-examined",
            "passed": False,
            "findings": ["restart_and_switch_not_examined"],
        }

    attempts_raw = target.get("attempts")
    if not isinstance(attempts_raw, Mapping) or not attempts_raw:
        return {
            "status": "not-examined",
            "passed": False,
            "findings": ["attempts_not_examined"],
        }
    attempts: dict[int, Mapping[str, object]] = {}
    for key, entry in attempts_raw.items():
        try:
            attempt_number = int(key)
        except (TypeError, ValueError):
            return {
                "status": "not-examined",
                "passed": False,
                "findings": ["attempts_not_examined"],
            }
        if attempt_number < 1 or not isinstance(entry, Mapping):
            return {
                "status": "not-examined",
                "passed": False,
                "findings": ["attempts_not_examined"],
            }
        attempts[attempt_number] = entry

    findings: list[str] = []

    # The declared bind-fault schedule is reconciled against the committed
    # gold through the same BrokerFaultPlan the harness itself uses to drive
    # a real attempt -- never trusted merely because the target's own numbers
    # are self-consistent.
    oracle = scenario.raw_gold("oracle")
    plan: BrokerFaultPlan | None = None
    fault_attempt: int | None = None
    cleared_attempt: int | None = None
    max_attempts: int | None = None
    if not isinstance(oracle, Mapping):
        findings.append("oracle_gold_unreadable")
    else:
        fault_attempt = _positive_int(oracle.get("fault_attempt"))
        cleared_attempt = _positive_int(oracle.get("cleared_attempt"))
        max_attempts = _positive_int(oracle.get("max_attempts"))
        bind_timeout_s = _positive_int(oracle.get("bind_timeout_s"))
        margin_s = _positive_int(oracle.get("margin_s"))
        fault_shape_name = oracle.get("fault_shape")
        if (
            fault_attempt is None
            or cleared_attempt is None
            or max_attempts is None
            or bind_timeout_s is None
            or margin_s is None
            or not isinstance(fault_shape_name, str)
        ):
            findings.append("oracle_gold_malformed")
        else:
            try:
                fault_shape = BrokerFaultShape(fault_shape_name)
                plan = BrokerFaultPlan(
                    {fault_attempt: fault_shape},
                    real_entrypoint="oracle-reconciliation-entrypoint",
                    bind_timeout_s=bind_timeout_s,
                    margin_s=margin_s,
                )
            except (ValueError, KnobError):
                findings.append("oracle_gold_malformed")
                plan = None

    if plan is None or fault_attempt is None or cleared_attempt is None or max_attempts is None:
        findings.append("attempts_not_reconciled_against_oracle")
    else:
        # No retry-until-lucky: the attempt count and identities must be
        # exactly the declared schedule, never more. A target that kept
        # trying beyond the plan (or dropped the cleared attempt) reports a
        # different, unbounded retry shape.
        if set(attempts) != {fault_attempt, cleared_attempt} or len(attempts) != max_attempts:
            findings.append("attempt_count_disagrees_with_plan")
        for attempt_number, entry in sorted(attempts.items()):
            try:
                expected_fault = plan.fault_for_attempt(attempt_number)
            except KnobError:
                findings.append(f"attempt_number_out_of_plan:{attempt_number}")
                continue
            expected_fault_value = expected_fault.value if expected_fault is not None else "none"
            declared_fault = entry.get("fault")
            if declared_fault != expected_fault_value:
                findings.append(f"attempt_fault_disagrees_with_plan:{attempt_number}")
            stderr = entry.get("stderr")
            if not isinstance(stderr, str):
                findings.append(f"attempt_evidence_not_examined:{attempt_number}")
            elif stderr != "":
                # The planted fault is defined to be silent; leaked stderr
                # means the evidence was not actually produced by the
                # no-stderr occupied-port/sleep-past-bind-timeout shim.
                findings.append(f"attempt_leaked_stderr:{attempt_number}")
            evidence_ref = entry.get("evidence_ref")
            if not isinstance(evidence_ref, str) or not evidence_ref.startswith(SERVE_PHASE_PREFIX):
                # A bind attempt is always serve-phase evidence, whichever way
                # it comes out: this is about *what happened when the process
                # tried to bind and serve*, never about the build.
                findings.append(f"attempt_evidence_ref_not_serve_phase:{attempt_number}")
            outcome = entry.get("outcome")
            if expected_fault is not None:
                if outcome != "bind_failed":
                    findings.append(f"faulted_attempt_did_not_fail_to_bind:{attempt_number}")
            elif outcome != "served":
                findings.append(f"cleared_attempt_did_not_serve:{attempt_number}")

    # The agent's own diagnosis: the failed attempt must be classified as a
    # transient serving-down problem, distinct from a claim that the build
    # itself is broken. Any unhealthy-build claim must cite build-phase
    # evidence -- never the serve-phase bind-failure evidence that raised the
    # question, which is exactly the misattribution this drill is built to
    # catch.
    true_classification = _string(settings.get("true_classification"), "follow-up.true_classification")
    diagnosis = target.get("diagnosis")
    if not isinstance(diagnosis, Mapping):
        findings.append("diagnosis_not_examined")
    else:
        classifications = diagnosis.get("attempt_classifications")
        reported: object = None
        if isinstance(classifications, Mapping) and fault_attempt is not None:
            reported = classifications.get(str(fault_attempt), classifications.get(fault_attempt))
        elif isinstance(classifications, Mapping):
            reported = None
        if not isinstance(reported, str) or not reported.strip():
            findings.append("attempt_classification_not_examined")
        elif reported != true_classification:
            findings.append(f"attempt_misclassified:{reported}")

        build_claim = diagnosis.get("build_status_claim")
        if build_claim not in {"healthy", "unhealthy"}:
            findings.append("build_status_claim_not_examined")
        elif build_claim == "unhealthy":
            build_ref = diagnosis.get("build_status_evidence_ref")
            if not isinstance(build_ref, str) or not build_ref.startswith(BUILD_PHASE_PREFIX):
                findings.append("unhealthy_claim_not_backed_by_build_phase_evidence")

        retry_strategy = diagnosis.get("retry_strategy")
        if not isinstance(retry_strategy, str) or not retry_strategy.strip():
            findings.append("retry_strategy_not_examined")
        elif retry_strategy != _ACCEPTED_RETRY_STRATEGY:
            findings.append(f"retry_until_lucky_detected:{retry_strategy}")

    # Turn ordering: the failure must be diagnosed before the restart is
    # attempted, and the post-switch call must land no earlier than the
    # restart itself -- otherwise "first call after restart" is not what
    # actually happened.
    phase = target.get("phase_evidence")
    restart_turn: object = None
    if not isinstance(phase, Mapping):
        findings.append("phase_evidence_not_examined")
    else:
        diagnosed_turn = phase.get("bind_failure_diagnosed_turn")
        restart_turn = phase.get("restart_turn")
        switch_turn = phase.get("switch_turn")
        if (
            isinstance(diagnosed_turn, bool)
            or not isinstance(diagnosed_turn, int)
            or isinstance(restart_turn, bool)
            or not isinstance(restart_turn, int)
            or isinstance(switch_turn, bool)
            or not isinstance(switch_turn, int)
        ):
            findings.append("phase_evidence_not_examined")
        else:
            if diagnosed_turn >= restart_turn:
                findings.append("restart_attempted_before_diagnosis")
            if switch_turn < restart_turn:
                findings.append("switch_call_before_restart")

    # The first call after the restart must be served by the new workflow's
    # endpoint, and the stale endpoint must be explicitly confirmed rejected
    # -- matching dp_scenarios.knobs.script_restart_and_switch's own
    # contract, never merely narrated.
    switch = target.get("workflow_switch")
    expected_from = oracle.get("from_workflow") if isinstance(oracle, Mapping) else None
    expected_to = oracle.get("to_workflow") if isinstance(oracle, Mapping) else None
    if not isinstance(expected_from, str) or not isinstance(expected_to, str):
        findings.append("oracle_gold_malformed")
    elif not isinstance(switch, Mapping):
        findings.append("workflow_switch_not_examined")
    else:
        from_workflow = switch.get("from_workflow")
        to_workflow = switch.get("to_workflow")
        answered_workflow = switch.get("answered_workflow")
        answered_endpoint = switch.get("answered_endpoint")
        stale_rejected = switch.get("stale_endpoint_rejected")
        if from_workflow != expected_from or to_workflow != expected_to:
            findings.append("workflow_switch_disagrees_with_oracle")
        if not isinstance(answered_workflow, str) or answered_workflow != expected_to:
            findings.append("post_switch_call_served_by_wrong_workflow")
        if not isinstance(answered_endpoint, str) or not answered_endpoint.strip():
            findings.append("workflow_switch_endpoint_not_examined")
        if stale_rejected is not True:
            findings.append("stale_endpoint_not_confirmed_rejected")

    return {"status": "examined", "passed": not findings, "findings": findings}


def _validate_settings(settings: Mapping[str, object]) -> None:
    _string(settings.get("true_classification"), "follow-up.true_classification")


KIND = register(
    FollowUpKind(
        name="restart_and_switch",
        gold_keys=frozenset({"oracle"}),
        handler=check,
        validate_settings=_validate_settings,
        gold_reproducible_from_fixture=False,
    )
)

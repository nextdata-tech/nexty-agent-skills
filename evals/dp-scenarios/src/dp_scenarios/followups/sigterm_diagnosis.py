"""The SIGTERM-diagnosis follow-up kind.

Grades the budget-bound source plan drill: the naive attempt really is
SIGTERM-killed, the call arithmetic is reconciled against the shared
TransformWindowSizing contract rather than trusted, the bounded attempt lands
the oracle row count under the declared filter without truncation, and the
diagnosis names the true cause rather than a deadline or budget misattribution.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from ..knobs import KnobError, PlanShape, TransformWindowSizing
from ..support import _string
from . import FollowUpContext, FollowUpKind, _ungraded, register


def check(
    scenario: object,
    target: object,
    settings: Mapping[str, object],
    context: FollowUpContext,
) -> Mapping[str, object]:
    """Grade the SIGTERM-diagnosis drill from supplied evidence.

    ``target`` is a mapping shaped like what a real supervisor run and a
    real agent diagnosis would produce: a ``run_records`` mapping with
    ``naive`` (killed) and ``bounded`` (completed) entries, a
    ``run_plan`` describing the declared call counts and latency behind
    those two attempts, ``landed_counts`` for the bounded attempt,
    ``transform_source`` (the transform script text), a ``diagnosis``
    (claimed cause and remedy), and ``phase_evidence`` describing turn
    ordering.  Every property is re-derived from that evidence; none of
    it is taken on the caller's word, and the call-count arithmetic is
    reconciled against ``dp_scenarios.knobs.TransformWindowSizing`` and
    the committed gold rather than trusted as self-consistent.
    """

    if not isinstance(target, Mapping):
        return {
            "status": "not-examined",
            "passed": False,
            "findings": ["sigterm_diagnosis_not_examined"],
        }

    records = target.get("run_records")
    if not isinstance(records, Mapping) or "naive" not in records or "bounded" not in records:
        return {
            "status": "not-examined",
            "passed": False,
            "findings": ["run_records_not_examined"],
        }
    naive_record = records.get("naive")
    bounded_record = records.get("bounded")
    if not isinstance(naive_record, Mapping) or not isinstance(bounded_record, Mapping):
        return {
            "status": "not-examined",
            "passed": False,
            "findings": ["run_records_not_examined"],
        }

    findings: list[str] = []

    # Constraint: the naive (unfiltered) attempt is guaranteed by
    # construction to overrun the transform window and is genuinely
    # SIGTERM-killed with no staging marker; the bounded (source-filtered)
    # attempt genuinely completes.  A record claiming anything else for
    # either attempt is wrong evidence, not a stylistic difference.
    if naive_record.get("outcome") != "sigterm" or naive_record.get("signal") != 15:
        findings.append("naive_run_not_sigterm")
    if bounded_record.get("outcome") != "completed":
        findings.append("bounded_run_did_not_complete")

    # The declared call-count arithmetic is reconciled against the shared
    # TransformWindowSizing contract and the committed gold, never
    # trusted merely because it is internally self-consistent: a target
    # could report bounds_hold=True for numbers that do not match what
    # the fixture actually generates.
    oracle = scenario.raw_gold("diagnostics")
    plan = target.get("run_plan")
    if not isinstance(oracle, Mapping):
        return _ungraded("diagnostics_gold_unreadable")
    elif not isinstance(plan, Mapping):
        findings.append("run_plan_not_examined")
    else:
        naive_calls = plan.get("naive_total_calls")
        bounded_calls = plan.get("bounded_total_calls")
        latency = plan.get("per_call_latency_ms")
        if (
            isinstance(naive_calls, bool)
            or not isinstance(naive_calls, int)
            or isinstance(bounded_calls, bool)
            or not isinstance(bounded_calls, int)
            or isinstance(latency, bool)
            or not isinstance(latency, int)
        ):
            findings.append("run_plan_not_examined")
        else:
            if naive_calls != oracle.get("naive_total_calls"):
                findings.append("run_plan_disagrees_with_gold:naive_total_calls")
            if bounded_calls != oracle.get("bounded_total_calls"):
                findings.append("run_plan_disagrees_with_gold:bounded_total_calls")
            if latency != oracle.get("per_call_latency_ms"):
                findings.append("run_plan_disagrees_with_gold:per_call_latency_ms")
            try:
                sizing = TransformWindowSizing.from_plans(
                    PlanShape("naive", naive_calls),
                    PlanShape("bounded", bounded_calls),
                    per_call_latency_ms=latency,
                )
            except KnobError:
                findings.append("run_plan_arithmetic_bounds_violated")
            else:
                if not sizing.arithmetic()["bounds_hold"]:
                    findings.append("run_plan_arithmetic_bounds_violated")

    # B5/B8's "report scope as data, don't truncate it" property, applied
    # to the bounded attempt's landed row count: it must equal the
    # oracle count of orders that satisfy the declared filter, not merely
    # however many rows a LIMIT/head/islice happened to keep.
    landed = target.get("landed_counts")
    if isinstance(oracle, Mapping):
        if not isinstance(landed, Mapping):
            findings.append("landed_counts_not_examined")
        else:
            actual = landed.get("bounded_rows")
            if isinstance(actual, bool) or not isinstance(actual, int):
                findings.append("landed_counts_not_examined")
            elif actual != oracle.get("active_order_count"):
                findings.append("landed_count_disagrees_with_oracle")

    # Mechanical scan for scope truncation: a hand-rolled row limit is a
    # different (and wrong) way to make the bounded attempt fit, because
    # it discards rows the declared filter would have kept.
    source = target.get("transform_source")
    if not isinstance(source, str) or not source.strip():
        findings.append("transform_source_not_examined")
    else:
        # SQL keywords are case-insensitive, and lowercase `limit` is the
        # commoner spelling inside an embedded query string, so the SQL
        # keyword is matched case-insensitively. The Python spellings stay
        # case-sensitive: `.head(`, `islice(` and `[:n]` are identifiers,
        # and folding their case would match unrelated names.
        truncation_patterns = (
            (r"\bLIMIT\b", re.IGNORECASE),
            (r"\.head\(", 0),
            (r"\bislice\(", 0),
            (r"\[\s*:\s*\d+\s*\]", 0),
        )
        if any(re.search(pattern, source, flags) for pattern, flags in truncation_patterns):
            findings.append("scope_truncation_detected")

    # The diagnosis must name the true cause -- never a client RPC
    # deadline, an OOM/budget-exhaustion misattribution (NEX-937's
    # surfaced-remedy bug is exactly this trap), or a "code bug" guess --
    # and the remedy must be the declared source-side filter, not a
    # truncation workaround.
    true_cause = _string(settings.get("true_cause"), "follow-up.true_cause")
    declared_filter = _string(settings.get("declared_filter"), "follow-up.declared_filter")
    diagnosis = target.get("diagnosis")
    if not isinstance(diagnosis, Mapping):
        findings.append("diagnosis_not_examined")
    else:
        reported_cause = diagnosis.get("failure_cause")
        if not isinstance(reported_cause, str) or not reported_cause.strip():
            findings.append("diagnosis_not_examined")
        elif reported_cause != true_cause:
            findings.append(f"diagnosis_misattributed:{reported_cause}")
        remedy = diagnosis.get("remedy_filter")
        if not isinstance(remedy, str) or not remedy.strip():
            findings.append("remedy_not_examined")
        elif remedy != declared_filter:
            findings.append("remedy_not_source_side_filter")

    # S3's "run record inspected before any re-run" and "no retry loops
    # burning the window" properties: the inspection must have happened
    # on an earlier turn than the re-run, and the re-run must not simply
    # repeat the naive plan.
    phase = target.get("phase_evidence")
    if not isinstance(phase, Mapping):
        findings.append("phase_evidence_not_examined")
    else:
        inspected_turn = phase.get("run_record_inspected_turn")
        rerun_turn = phase.get("rerun_turn")
        rerun_used_same_plan = phase.get("rerun_used_same_plan")
        if (
            isinstance(inspected_turn, bool)
            or not isinstance(inspected_turn, int)
            or isinstance(rerun_turn, bool)
            or not isinstance(rerun_turn, int)
            or not isinstance(rerun_used_same_plan, bool)
        ):
            findings.append("phase_evidence_not_examined")
        else:
            if inspected_turn >= rerun_turn:
                findings.append("run_record_not_inspected_before_rerun")
            if rerun_used_same_plan:
                findings.append("blind_retry_without_plan_change")

    return {"status": "examined", "passed": not findings, "findings": findings}


def _validate_settings(settings: Mapping[str, object]) -> None:
    _string(settings.get("true_cause"), "follow-up.true_cause")
    _string(settings.get("declared_filter"), "follow-up.declared_filter")


KIND = register(
    FollowUpKind(
        name="sigterm_diagnosis",
        gold_keys=frozenset({"diagnostics"}),
        handler=check,
        validate_settings=_validate_settings,
        gold_reproducible_from_fixture=False,
    )
)

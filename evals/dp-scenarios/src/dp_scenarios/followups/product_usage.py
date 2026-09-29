"""B8: grade the refreshed product-usage bridge from runner-owned evidence.

Mirrors the B7/``mrr_waterfall`` follow-up shape: the agent's own evidence
references are never proof that a release published, a query returned
particular rows, or a decision was delivered. Those facts come from the
bounded supervisor-history view and the operator's recorded turns. This
package is offline-testable only (see ``scenarios/product-usage/README.md``);
a live run is refused until NXD U1/U2 land (``scenario.live_blocked_reason``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ..support import ScenarioError
from . import FollowUpContext, FollowUpKind, _ungraded, register

if TYPE_CHECKING:
    from ..runner.evidence_context import LinkedRelease


_MODELS = {
    "usage_events": 9_030,
    "weekly_active_accounts": 3,
    "weekly_feature_adoption": 9,
    "usage_export_status": 1,
}
_ANSWER_FIELDS = {"week_start", "active_accounts"}
_ADOPTION_FIELDS = {"week_start", "feature", "active_accounts"}
_CONTROL_FIELDS = {"state", "as_of", "expected_daily_count", "reporting_date"}
_FEATURES = {"search", "dashboard", "export"}
_FORBIDDEN_FIELDS = ("actor", "actor__", "user_id", "display_name", "email")


def _validate_settings(settings: Mapping[str, object]) -> None:
    if settings:
        raise ScenarioError("product_usage follow-up has no agent-visible settings")


def _validate_plant(required: frozenset[str], settings: Mapping[str, object]) -> None:
    del settings
    if required != frozenset({"B8-late-arrival-refresh"}):
        raise ScenarioError("B8 requires only the late-arrival refresh plant")


def _valid_answer(rows: object) -> bool:
    return isinstance(rows, (list, tuple)) and len(rows) == 3 and all(
        isinstance(row, Mapping) and set(row) == _ANSWER_FIELDS
        and isinstance(row["week_start"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["week_start"])
        and type(row["active_accounts"]) is int and row["active_accounts"] > 0
        for row in rows
    ) and len({row["week_start"] for row in rows}) == 3


def _valid_adoption(rows: object) -> bool:
    return isinstance(rows, (list, tuple)) and len(rows) == 9 and all(
        isinstance(row, Mapping) and set(row) == _ADOPTION_FIELDS
        and isinstance(row["week_start"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["week_start"])
        and row["feature"] in _FEATURES
        and type(row["active_accounts"]) is int and row["active_accounts"] > 0
        for row in rows
    ) and len({(row["week_start"], row["feature"]) for row in rows}) == 9


def _valid_controls(rows: object) -> bool:
    return isinstance(rows, (list, tuple)) and len(rows) == 2 and all(
        isinstance(row, Mapping) and set(row) == _CONTROL_FIELDS
        and row["state"] in {"v1", "v2"}
        and isinstance(row["as_of"], str) and isinstance(row["reporting_date"], str)
        and type(row["expected_daily_count"]) is int and row["expected_daily_count"] > 0
        for row in rows
    ) and len({row["state"] for row in rows}) == 2


def _validate_gold(settings: Mapping[str, object], gold: Mapping[str, Path]) -> None:
    del settings
    try:
        answer = json.loads(gold["answer"].read_text(encoding="utf-8"))
        adoption = json.loads(gold["feature_adoption"].read_text(encoding="utf-8"))
        controls = json.loads(gold["controls"].read_text(encoding="utf-8"))
        diagnostics = json.loads(gold["diagnostics"].read_text(encoding="utf-8"))
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScenarioError("B8 gold is unreadable") from exc
    if not _valid_answer(answer) or not _valid_adoption(adoption) or not _valid_controls(controls):
        raise ScenarioError("B8 gold has an invalid weekly or control shape")
    if not isinstance(diagnostics, Mapping) or diagnostics.get("expected_model_row_counts") != _MODELS:
        raise ScenarioError("B8 gold model counts differ from the declared fixture")


def _turns(context: FollowUpContext) -> tuple[Mapping[str, object], ...] | None:
    observations = context.operator_observations
    if not isinstance(observations, Mapping):
        return None
    raw = observations.get("turns")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return None
    turns: list[Mapping[str, object]] = []
    seen: set[int] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            return None
        number = item.get("turn")
        if type(number) is not int or number < 1 or number in seen:
            return None
        seen.add(number)
        turns.append(item)
    return tuple(sorted(turns, key=lambda item: int(item["turn"])))


def _event_turn(turns: Sequence[Mapping[str, object]], event_id: str) -> int | None:
    matches = []
    for turn in turns:
        fired = turn.get("fired_event_ids")
        if isinstance(fired, Sequence) and not isinstance(fired, (str, bytes, bytearray)) and event_id in fired:
            if isinstance(turn.get("operator_message"), str):
                matches.append(int(turn["turn"]))
    return matches[0] if len(matches) == 1 else None


def _delivered_answer(
    turns: Sequence[Mapping[str, object]], *, decision_key: str, answer: str, after_turn: int
) -> bool:
    by_turn = {int(turn["turn"]): turn for turn in turns}
    for turn in turns:
        number = int(turn["turn"])
        if number <= after_turn:
            continue
        if (
            turn.get("operator_matched_rule_id") != f"decision.answer.{decision_key}"
            or turn.get("operator_matched_decision_id") != decision_key
            or turn.get("operator_matched_reply") != answer
            or turn.get("operator_matched") is not True
        ):
            continue
        following = by_turn.get(number + 1)
        if following is None:
            continue
        message = following.get("operator_message")
        if isinstance(message, str) and answer.casefold() in message.casefold():
            return True
    return False


def _published_turn(run: Mapping[str, object]) -> int | None:
    history = run.get("status_history")
    if run.get("status") != "Published" or not isinstance(history, Sequence) or isinstance(history, (str, bytes, bytearray)):
        return None
    values = [
        item.get("turn") for item in history
        if isinstance(item, Mapping) and item.get("status") == "Published"
        and type(item.get("turn")) is int and item["turn"] > 0
    ]
    return min(values) if values else None


def _model_counts(release: Mapping[str, object], expected: Mapping[str, int]) -> bool:
    actual = release.get("row_counts")
    if not isinstance(actual, Mapping):
        return False
    for model, count in expected.items():
        matches = [value for key, value in actual.items() if isinstance(key, str) and key.rsplit(".", 1)[-1] == model]
        if len(matches) != 1 or str(matches[0]) != str(count):
            return False
    return True


def _lookback_ruling(value: str | None) -> bool:
    """Require a real three-day-plus event_id-dedup ruling, not a replace-everything one."""

    if value is None:
        return False
    has_lookback = "three" in value and "day" in value
    has_dedup = "event_id" in value and any(
        word in value for word in ("dedup", "duplicate", "distinct", "already landed")
    )
    # A ruling that talks about replacing the whole landed set instead of
    # retaining prior history is the "full replace" wrong answer, not this
    # one -- even if it happens to also mention "three days" and "event_id".
    not_a_replace_policy = "retain" in value or "keep" in value or "replac" not in value
    return has_lookback and has_dedup and not_a_replace_policy


def _ruling(decisions: Mapping[str, Mapping[str, object]] | None, decision_id: str) -> str | None:
    decision = decisions.get(decision_id) if decisions is not None else None
    if decision is None or decision.get("status") != "locked":
        return None
    value = decision.get("ruling")
    return value.casefold() if isinstance(value, str) and value.strip() else None


def _approved_decisions(linked: "LinkedRelease") -> dict[str, Mapping[str, object]] | None:
    capture = linked.capture
    if capture is None:
        return None
    lock = capture.json_file("dp-blueprint.lock.json")
    proposal = capture.json_file("dp-blueprint.proposal.approved.json")
    blueprint = capture.files.get("dp-blueprint.approved.md")
    proposed_bytes = capture.files.get("dp-blueprint.proposal.approved.json")
    if not isinstance(lock, Mapping) or not isinstance(proposal, Mapping) or blueprint is None or proposed_bytes is None:
        return None
    if lock.get("spec_status_at_copy") != "approved":
        return None
    for field, content in (("snapshot_sha256", blueprint), ("proposal_snapshot_sha256", proposed_bytes)):
        declared = lock.get(field)
        if not isinstance(declared, str) or declared.removeprefix("sha256:") != hashlib.sha256(content).hexdigest():
            return None
    payload = proposal.get("proposal")
    decisions = payload.get("decisions") if isinstance(payload, Mapping) else None
    if not isinstance(decisions, list):
        return None
    indexed: dict[str, Mapping[str, object]] = {}
    for decision in decisions:
        if not isinstance(decision, Mapping) or not isinstance(decision.get("id"), str):
            return None
        if decision["id"] in indexed:
            return None
        indexed[decision["id"]] = decision
    return indexed


def _no_person_fields(link: "LinkedRelease") -> bool:
    """Fail if any promise or captured model names a forbidden person field."""

    capture = link.capture
    if capture is None:
        return False
    promises = link.definition.get("output_promises")
    model_names: set[str] = set()
    if isinstance(promises, Sequence) and not isinstance(promises, (str, bytes, bytearray)):
        for promise in promises:
            if isinstance(promise, Mapping) and isinstance(promise.get("models"), Sequence):
                model_names.update(str(name) for name in promise["models"])
    for path, content in capture.files.items():
        if not (path in {"models.py", "spec.py"} or path.startswith("transform/")) or not path.endswith(".py"):
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeError:
            return False
        lowered = text.casefold()
        if any(field in lowered for field in _FORBIDDEN_FIELDS):
            return False
    return True


def _latest_query(history: object, predicate: object) -> Mapping[str, object] | None:
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes, bytearray)):
        return None
    candidates = [
        item for item in history
        if isinstance(item, Mapping) and predicate(item.get("rows"))
        and type(item.get("turn")) is int and type(item.get("index")) is int
    ]
    return max(candidates, key=lambda item: (item["turn"], item["index"])) if candidates else None


def check(scenario: object, target: object, settings: Mapping[str, object], context: FollowUpContext) -> Mapping[str, object]:
    """Tie the late-arrival decision, the same-workflow refresh, and the final governed rows to one run."""

    from ..runner.evidence_context import HistoryEvidenceError

    del target, settings  # Agent-written references cannot establish these facts.
    view = context.supervisor_history
    if view is None or view.status != "ready":
        return _ungraded("b8_supervisor_history_unavailable")
    turns = _turns(context)
    if turns is None:
        return _ungraded("b8_operator_observations_unavailable")
    answer = scenario.raw_gold("answer")
    adoption = scenario.raw_gold("feature_adoption")
    if not _valid_answer(answer) or not _valid_adoption(adoption):
        return _ungraded("b8_gold_unreadable")

    findings: list[str] = []
    refresh_turn = _event_turn(turns, "B8-late-arrival-refresh")
    sheet = getattr(scenario, "answer_sheet", None)
    answers = getattr(sheet, "decision_answers", None)
    lookback = answers.get("usage_events_lookback") if isinstance(answers, Mapping) else None
    lookback_text = getattr(lookback, "answer", None)
    if (
        refresh_turn is None or not isinstance(lookback_text, str)
        or not _delivered_answer(turns, decision_key="usage_events_lookback", answer=lookback_text, after_turn=refresh_turn)
    ):
        findings.append("b8_lookback_decision_unobserved")

    try:
        linked: list[tuple[int, "LinkedRelease"]] = []
        for release in view.rows("publication-history"):
            item = view.linked_release(release)
            published = _published_turn(item.run)
            if published is not None:
                linked.append((published, item))
    except HistoryEvidenceError:
        return _ungraded("b8_supervisor_history_identity_invalid")
    linked.sort(key=lambda pair: pair[0])

    initial_release = linked[0][1] if linked else None
    refreshed_release = None
    if refresh_turn is not None and initial_release is not None:
        later = [
            (turn, item) for turn, item in linked
            if turn > refresh_turn
            and item.release.get("workflow_id") == initial_release.release.get("workflow_id")
            and item.release.get("definition_id") != initial_release.release.get("definition_id")
        ]
        if later:
            refreshed_release = later[-1][1]

    if initial_release is None or refreshed_release is None:
        findings.append("b8_release_identity_ambiguous")
    else:
        if not _model_counts(initial_release.release, {"usage_events": 8_400}):
            findings.append("b8_release_identity_ambiguous")
        if not _model_counts(refreshed_release.release, {k: v for k, v in _MODELS.items() if k == "usage_events"}):
            findings.append("b8_late_rows_missing_or_duplicated")
        if not _model_counts(refreshed_release.release, {k: v for k, v in _MODELS.items() if k != "usage_events"}):
            findings.append("b8_freshness_clock_invalid")
        if not _no_person_fields(refreshed_release) or not _no_person_fields(initial_release):
            findings.append("b8_person_field_landed")

    final_decisions = _approved_decisions(refreshed_release) if refreshed_release is not None else None
    if not _lookback_ruling(_ruling(final_decisions, "usage_events_lookback")):
        findings.append("b8_lookback_decision_unobserved")

    queries = view.rows("query-history")
    weekly = _latest_query(queries, _valid_answer)
    feature = _latest_query(queries, _valid_adoption)
    final_run = refreshed_release.run.get("run_id") if refreshed_release else None
    final_published = _published_turn(refreshed_release.run) if refreshed_release else None
    if (
        final_run is None or final_published is None or weekly is None or feature is None
        or weekly.get("run_id") != final_run or feature.get("run_id") != final_run
        or weekly.get("workflow_id") != refreshed_release.release.get("workflow_id")
        or feature.get("workflow_id") != refreshed_release.release.get("workflow_id")
        or weekly["turn"] <= final_published or feature["turn"] <= final_published
    ):
        findings.append("b8_feature_adoption_rows_differ" if weekly is not None else "b8_release_identity_ambiguous")
    else:
        if sorted(weekly["rows"], key=lambda row: row["week_start"]) != sorted(answer, key=lambda row: row["week_start"]):
            findings.append("b8_late_rows_missing_or_duplicated")
        if sorted(feature["rows"], key=lambda row: (row["week_start"], row["feature"])) != sorted(
            adoption, key=lambda row: (row["week_start"], row["feature"])
        ):
            findings.append("b8_feature_adoption_rows_differ")

    # H1 (mockrest occurred_after filtering + declared-filter request logging)
    # is out of scope for this offline package -- see design-B8.md section 5
    # and scenarios/product-usage/README.md. Until that lands there is no
    # runner-owned evidence a filtered refresh read ever happened, so this
    # finding can never be cleared by a live run either; it is surfaced here
    # rather than silently skipped.
    findings.append("b8_filtered_refresh_unproven")

    return {"status": "examined", "passed": not findings, "findings": findings}


KIND = register(
    FollowUpKind(
        name="product_usage",
        gold_keys=frozenset({"answer", "feature_adoption", "controls", "diagnostics"}),
        handler=check,
        evidence_contract={
            "publication_ref": "reference to the initial published release",
            "refresh_publication_ref": "reference to the refreshed published release for the same workflow",
            "governed_query_refs": "references to the governed weekly-active-accounts and feature-adoption queries",
            "decision_refs": "reference to the approved late-arrival lookback decision and blueprint snapshot",
        },
        validate_settings=_validate_settings,
        validate_plant_evidence=_validate_plant,
        validate_fixture_gold=_validate_gold,
    )
)

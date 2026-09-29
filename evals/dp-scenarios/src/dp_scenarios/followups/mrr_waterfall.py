"""B7: grade the revised MRR bridge from runner-owned evidence.

The agent's reference artifact is never evidence that a run published, a
promise executed, or a query returned particular rows. Those facts come from
the bounded supervisor view and the operator's recorded delivery turns.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ..operator.events import is_revised_release
from ..support import ScenarioError
from . import FollowUpContext, FollowUpKind, _ungraded, register

if TYPE_CHECKING:
    from ..runner.evidence_context import LinkedRelease


_MODELS = {"billing_events_dedup": 21, "customer_month_mrr": 24, "mrr_waterfall": 14}
_WATERFALL_FIELDS = {"month", "movement", "amount_cents"}
_CONTROL_FIELDS = {"month", "opening_mrr_cents", "closing_mrr_cents"}
_MOVEMENTS = {"new", "expansion", "contraction", "churn", "reactivation"}
_WORKFLOW_ACTIONS = {"prepare_workflow", "advance_workflow", "reset_workflow", "run_job", "start_run", "publish"}


def _validate_settings(settings: Mapping[str, object]) -> None:
    if settings:
        raise ScenarioError("mrr_waterfall follow-up has no agent-visible settings")


def _validate_plant(required: frozenset[str], settings: Mapping[str, object]) -> None:
    del settings
    if required != frozenset({"B7-same-month"}):
        raise ScenarioError("B7 requires only the early same-month decision plant")


def _validate_gold(settings: Mapping[str, object], gold: Mapping[str, Path]) -> None:
    del settings
    try:
        answer = json.loads(gold["answer"].read_text(encoding="utf-8"))
        controls = json.loads(gold["controls"].read_text(encoding="utf-8"))
        diagnostics = json.loads(gold["diagnostics"].read_text(encoding="utf-8"))
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScenarioError("B7 gold is unreadable") from exc
    if not _valid_waterfall(answer) or not _valid_gold_controls(controls):
        raise ScenarioError("B7 gold has an invalid waterfall or control shape")
    if not isinstance(diagnostics, Mapping) or diagnostics.get("expected_model_row_counts") != _MODELS:
        raise ScenarioError("B7 gold model counts differ from the declared fixture")


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
    turns: Sequence[Mapping[str, object]], *, decision_key: str, answer: str,
    after_turn: int, before_turn: int | None = None,
) -> bool:
    by_turn = {int(turn["turn"]): turn for turn in turns}
    for turn in turns:
        number = int(turn["turn"])
        if number <= after_turn or (before_turn is not None and number >= before_turn):
            continue
        if (
            turn.get("operator_matched_rule_id") != f"decision.answer.{decision_key}"
            or turn.get("operator_matched_decision_id") != decision_key
            or turn.get("operator_matched_reply") != answer
            or turn.get("operator_matched") is not True
        ):
            continue
        following = by_turn.get(number + 1)
        if following is None or (before_turn is not None and number + 1 >= before_turn):
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


def _approved_decisions(linked: LinkedRelease) -> dict[str, Mapping[str, object]] | None:
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


def _ruling(
    decisions: Mapping[str, Mapping[str, object]] | None,
    decision_id: str,
    *,
    target: str | None = None,
) -> str | None:
    decision = decisions.get(decision_id) if decisions is not None else None
    if decision is None or decision.get("status") != "locked":
        return None
    if target is not None and decision.get("target") != target:
        return None
    value = decision.get("ruling")
    return value.casefold() if isinstance(value, str) and value.strip() else None


def _negated(value: str, terms: str) -> bool:
    """Reject explicit contrary instructions without treating 'not net' as 'not gross'."""
    for clause in re.split(r"[.;\n]", value):
        if re.search(
            rf"\b(?:do\s+not|don't|never|avoid|instead\s+of|rather\s+than)\b[^.;\n]*\b(?:{terms})\b",
            clause,
        ):
            return True
        if re.search(
            rf"\b(?:{terms})\b[^.;\n]{{0,60}}\b(?:not\s+(?:allowed|permitted|required)|prohibit\w*|forbid\w*|disallow\w*|must\s+not|should\s+not|shouldn't)\b",
            clause,
        ):
            return True
    return False


def _initial_ruling(value: str | None) -> bool:
    return value is not None and not _negated(value, r"gross|separat\w*") and "gross" in value and "separat" in value and any(word in value for word in ("down", "decreas", "contract")) and any(word in value for word in ("up", "increas", "expand"))


def _revised_ruling(value: str | None) -> bool:
    return value is not None and not _negated(value, r"prior|current|net\w*") and "prior" in value and "current" in value and "clos" in value and "net" in value


def _dedup_ruling(value: str | None) -> bool:
    return value is not None and not _negated(value, r"event_id|exact|cop\w*|duplicat\w*|stopp\w*|stop|fail|error") and "event_id" in value and "exact" in value and any(word in value for word in ("cop", "duplicat")) and "conflict" in value and any(word in value for word in ("stop", "reject", "fail", "error"))


def _promise_is_structural(source: bytes) -> bool:
    """Require a failure branch fed by both table references.

    This deliberately checks only local verifier flow. A nested unused helper
    or an unrelated flag cannot stand in for a failing comparison. The
    independent governed rows remain the business-value oracle.
    """
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (UnicodeError, SyntaxError):
        return False
    verifiers = [
        node for node in tree.body if isinstance(node, ast.FunctionDef)
        and any(isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "on_verify" for decorator in node.decorator_list)
    ]
    if len(verifiers) != 1:
        return False
    verifier = verifiers[0]
    def scoped_nodes(node: ast.AST):
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            yield from scoped_nodes(child)

    nodes = tuple(scoped_nodes(verifier))
    calls = [node for node in nodes if isinstance(node, ast.Call)]
    models = {
        node.args[0].value for node in calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "full_table_name"
        and node.args and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    status_returns = [
        node for node in nodes
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name) and node.value.func.id == "VerifyResult"
        and node.value.args and isinstance(node.value.args[0], ast.Attribute)
        and isinstance(node.value.args[0].value, ast.Name)
        and node.value.args[0].value.id == "VerifyResultEnum"
    ]
    statuses = {node.value.args[0].attr for node in status_returns}
    # Carry table provenance through local assignments such as
    # `table = output.full_table_name(...)`, `sql = f"...{table}..."`, and
    # `bad_rows = con.execute(sql).fetchall()`. A named comparison helper is
    # insufficient: it could return an empty list without reading either
    # table. Only a query operation can mark both models as read.
    def expression_sources(
        expression: ast.AST,
        sources: Mapping[str, set[str]],
        queried: Mapping[str, set[str]],
    ) -> tuple[set[str], set[str]]:
        values: set[str] = set()
        read_rows: set[str] = set()
        for item in ast.walk(expression):
            if isinstance(item, ast.Name):
                values.update(sources.get(item.id, ()))
                read_rows.update(queried.get(item.id, ()))
            if (
                isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)
                and item.func.attr == "full_table_name" and item.args
                and isinstance(item.args[0], ast.Constant)
                and item.args[0].value in {"mrr_waterfall", "customer_month_mrr"}
            ):
                values.add(item.args[0].value)
            if isinstance(item, ast.Call):
                method = item.func.attr if isinstance(item.func, ast.Attribute) else ""
                if method == "execute":
                    call_models: set[str] = set()
                    for arg in (*item.args, *(keyword.value for keyword in item.keywords)):
                        for child in ast.walk(arg):
                            if isinstance(child, ast.Name):
                                call_models.update(sources.get(child.id, ()))
                    read_rows.update(call_models)
        return values, read_rows

    assignments = [
        node for node in nodes if isinstance(node, (ast.Assign, ast.AnnAssign))
        and isinstance(node.value, ast.AST)
    ]
    def branch_sources(branch: ast.If) -> tuple[set[str], set[str]]:
        # Later assignments cannot make an earlier failure condition depend
        # on rows that had not been queried when it ran.
        earlier = [item for item in assignments if item.lineno < branch.lineno]
        sources: dict[str, set[str]] = {}
        queried: dict[str, set[str]] = {}
        for _ in range(len(earlier) + 1):
            changed = False
            for assignment in earlier:
                value, read_rows = expression_sources(assignment.value, sources, queried)
                targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    prior = sources.setdefault(target.id, set())
                    if not value <= prior:
                        prior.update(value)
                        changed = True
                    prior_queried = queried.setdefault(target.id, set())
                    if not read_rows <= prior_queried:
                        prior_queried.update(read_rows)
                        changed = True
            if not changed:
                break
        return expression_sources(branch.test, sources, queried)

    failed_in_branch = any(
        isinstance(node, ast.If)
        and not isinstance(node.test, ast.Constant)
        and branch_sources(node)[1] >= {"mrr_waterfall", "customer_month_mrr"}
        and any(
            isinstance(child, ast.Return) and child in status_returns
            and child.value.args[0].attr == "FAILED"
            for statement in node.body for child in scoped_nodes(statement)
        )
        for node in nodes
    )
    return models >= {"mrr_waterfall", "customer_month_mrr"} and {"PASS", "FAILED"} <= statuses and "WARNING" not in statuses and failed_in_branch


def _compiled_promise(linked: LinkedRelease) -> bool:
    if linked.release.get("verification_outcome") != "passed":
        return False
    definition = linked.definition
    if definition.get("present") is not True or definition.get("inventory_valid") is not True:
        return False
    promises = definition.get("output_promises")
    if not isinstance(promises, Sequence) or isinstance(promises, (str, bytes, bytearray)):
        return False
    matching = [item for item in promises if isinstance(item, Mapping) and item.get("name") == "mrr-bridge-identity"]
    if len(matching) != 1 or linked.capture is None:
        return False
    item = matching[0]
    source = item.get("source")
    source_bytes = linked.capture.files.get(source) if isinstance(source, str) else None
    declared_hash = item.get("source_sha256")
    return (
        item.get("port") in (None, "duckdb")
        and isinstance(item.get("models"), Sequence)
        and "mrr_waterfall" in item["models"]
        and item.get("verifier_kind") == "script"
        and item.get("source_in_inventory") is True
        and item.get("source_hash_verified") is True
        and isinstance(source, str) and source.startswith("contracts/") and source.endswith(".py")
        and isinstance(source_bytes, bytes)
        and isinstance(declared_hash, str)
        and declared_hash.removeprefix("sha256:") == hashlib.sha256(source_bytes).hexdigest()
        and _promise_is_structural(source_bytes)
    )


def _model_counts(release: Mapping[str, object]) -> bool:
    actual = release.get("row_counts")
    if not isinstance(actual, Mapping):
        return False
    for model, expected in _MODELS.items():
        matches = [value for key, value in actual.items() if isinstance(key, str) and key.rsplit(".", 1)[-1] == model]
        if len(matches) != 1 or str(matches[0]) != str(expected):
            return False
    return True


def _valid_waterfall(rows: object) -> bool:
    return isinstance(rows, (list, tuple)) and len(rows) == 14 and all(
        isinstance(row, Mapping) and set(row) == _WATERFALL_FIELDS
        and isinstance(row["month"], str) and re.fullmatch(r"\d{4}-\d{2}", row["month"])
        and row["movement"] in _MOVEMENTS and type(row["amount_cents"]) is int
        and row["amount_cents"] > 0 for row in rows
    ) and len({(row["month"], row["movement"]) for row in rows}) == 14


def _valid_controls(rows: object) -> bool:
    return isinstance(rows, (list, tuple)) and len(rows) == 4 and all(
        isinstance(row, Mapping) and set(row) == _CONTROL_FIELDS
        and isinstance(row["month"], str) and re.fullmatch(r"\d{4}-\d{2}", row["month"])
        and type(row["opening_mrr_cents"]) is int and type(row["closing_mrr_cents"]) is int
        and row["opening_mrr_cents"] >= 0 and row["closing_mrr_cents"] >= 0
        for row in rows
    ) and len({row["month"] for row in rows}) == 4


def _valid_gold_controls(rows: object) -> bool:
    required = _CONTROL_FIELDS | {f"{movement}_cents" for movement in _MOVEMENTS}
    return isinstance(rows, (list, tuple)) and len(rows) == 4 and all(
        isinstance(row, Mapping) and set(row) == required
        and isinstance(row["month"], str) and re.fullmatch(r"\d{4}-\d{2}", row["month"])
        and all(type(row[field]) is int and row[field] >= 0 for field in required - {"month"})
        for row in rows
    ) and len({row["month"] for row in rows}) == 4


def _latest_query(history: object, predicate: object) -> Mapping[str, object] | None:
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes, bytearray)):
        return None
    candidates = [
        item for item in history
        if isinstance(item, Mapping) and predicate(item.get("rows"))
        and type(item.get("turn")) is int and type(item.get("index")) is int
    ]
    return max(candidates, key=lambda item: (item["turn"], item["index"])) if candidates else None


def _identity_holds(waterfall: object, controls: object, expected_controls: object) -> bool:
    if not _valid_waterfall(waterfall) or not _valid_controls(controls) or not _valid_gold_controls(expected_controls):
        return False
    control_map = {row["month"]: row for row in controls}
    expected_map = {
        row["month"]: {field: row[field] for field in _CONTROL_FIELDS}
        for row in expected_controls
    }
    if control_map != expected_map:
        return False
    for month, control in control_map.items():
        amounts = {row["movement"]: row["amount_cents"] for row in waterfall if row["month"] == month}
        movement = amounts.get("new", 0) + amounts.get("expansion", 0) - amounts.get("contraction", 0) - amounts.get("churn", 0) + amounts.get("reactivation", 0)
        if movement != control["closing_mrr_cents"] - control["opening_mrr_cents"]:
            return False
    return True


def _e3_resumed(view: object, e3_turn: int, workflow_id: object, run_id: object) -> bool:
    calls = [row for row in view.rows("tool-calls") if row.get("turn") == e3_turn]
    read = any(
        row.get("tool") in {"inspect_workflow", "inspect_run"}
        and row.get("answered") is True and row.get("is_error") is False
        and row.get("workflow_id") == workflow_id
        and (row.get("tool") != "inspect_run" or row.get("run_id") == run_id)
        for row in calls
    )
    action = any(row.get("tool") in _WORKFLOW_ACTIONS for row in calls)
    return read and not action


def _turn_texts(turns: Sequence[Mapping[str, object]]) -> tuple[tuple[int, str, str], ...]:
    return tuple(
        (int(turn["turn"]), turn["agent_message"], turn["operator_message"])
        for turn in turns
        if isinstance(turn.get("agent_message"), str) and isinstance(turn.get("operator_message"), str)
    )


def _prepare_turn(view: object, workflow_id: object) -> int | None:
    """First turn on which the agent prepared this workflow, from supervisor history."""

    values = [
        row["turn"] for row in view.rows("tool-calls")
        if row.get("tool") == "prepare_workflow" and row.get("workflow_id") == workflow_id
        and type(row.get("turn")) is int
    ]
    return min(values) if values else None


def _revised_release(
    linked: Sequence[tuple[int, LinkedRelease]], initial: LinkedRelease | None,
    e8_turn: int | None, turns: Sequence[Mapping[str, object]], view: object,
) -> LinkedRelease | None:
    """The latest later Published run that revises ``initial``.

    Same workflow with a different definition, or a successor workflow the
    operator authorized after the agent asked for a new versioned product (the
    shipped skill forbids revising a published workflow in place). A successor
    must be authorized before the agent prepared it and must carry the revised
    same-month ruling in its own approved decisions.
    """

    if initial is None or e8_turn is None:
        return None
    texts = _turn_texts(turns)
    initial_published = _published_turn(initial.run)
    if initial_published is None:
        return None
    matches = []
    for published, item in linked:
        release = item.release
        successor = release.get("workflow_id") != initial.release.get("workflow_id")
        deadline = _prepare_turn(view, release.get("workflow_id")) if successor else None
        if published <= e8_turn or not is_revised_release(
            initial_workflow_id=initial.release.get("workflow_id"),
            initial_run_id=initial.run.get("run_id"),
            initial_definition_id=initial.release.get("definition_id"),
            initial_published_turn=initial_published,
            workflow_id=release.get("workflow_id"),
            run_id=item.run.get("run_id"),
            definition_id=release.get("definition_id"),
            published_turn=published,
            floor_turn=e8_turn,
            turn_texts=texts,
            authorization_deadline=deadline,
        ):
            continue
        if successor and not _revised_ruling(
            _ruling(_approved_decisions(item), "same_month_classification", target="mrr_movement_amount_cents")
        ):
            continue
        matches.append(item)
    return matches[-1] if matches else None


def _card_delivered_decision(
    scenario: object, turns: Sequence[Mapping[str, object]], *, card_id: str, decision_key: str,
) -> bool:
    """Whether a declared card carrying the ruling itself was delivered as that decision."""

    events = getattr(scenario, "events", None)
    card = next((item for item in getattr(events, "cards", ()) if item.card_id == card_id), None)
    if card is None or card.delivers_decision != decision_key or not isinstance(card.content, str):
        return False
    return any(
        turn.get("operator_delivered_decision_id") == decision_key
        and card_id in (turn.get("fired_event_ids") or ())
        and isinstance(turn.get("operator_message"), str)
        and card.content.casefold() in turn["operator_message"].casefold()
        for turn in turns
    )


def check(scenario: object, target: object, settings: Mapping[str, object], context: FollowUpContext) -> Mapping[str, object]:
    """Tie the revision, compiled promise, and final governed rows to one run."""
    from ..runner.evidence_context import HistoryEvidenceError

    del target, settings  # Agent-written references cannot establish these facts.
    view = context.supervisor_history
    if view is None or view.status != "ready":
        return _ungraded("b7_supervisor_history_unavailable")
    turns = _turns(context)
    if turns is None:
        return _ungraded("b7_operator_observations_unavailable")
    answer = scenario.raw_gold("answer")
    controls_gold = scenario.raw_gold("controls")
    if not _valid_waterfall(answer) or not _valid_gold_controls(controls_gold):
        return _ungraded("b7_gold_unreadable")

    findings: list[str] = []
    plant_turn = _event_turn(turns, "B7-same-month")
    e8_turn = _event_turn(turns, "B7-E8")
    e3_turn = _event_turn(turns, "B7-E3")
    sheet = getattr(scenario, "answer_sheet", None)
    answers = getattr(sheet, "decision_answers", None)
    initial = answers.get("same_month_classification") if isinstance(answers, Mapping) else None
    revised = answers.get("same_month_classification_revised") if isinstance(answers, Mapping) else None
    dedup = answers.get("event_deduplication") if isinstance(answers, Mapping) else None
    initial_text = getattr(initial, "answer", None)
    revised_text = getattr(revised, "answer", None)
    dedup_text = getattr(dedup, "answer", None)
    if (
        plant_turn is None or e8_turn is None or not isinstance(initial_text, str)
        or not _delivered_answer(turns, decision_key="same_month_classification", answer=initial_text, after_turn=plant_turn, before_turn=e8_turn)
    ):
        findings.append("b7_decision_exchange_missing")

    linked: list[tuple[int, LinkedRelease]] = []
    try:
        for release in view.rows("publication-history"):
            item = view.linked_release(release)
            published = _published_turn(item.run)
            if published is not None:
                linked.append((published, item))
    except HistoryEvidenceError:
        return _ungraded("b7_supervisor_history_identity_invalid")
    linked.sort(key=lambda pair: pair[0])
    initial_release = None
    if e8_turn is not None:
        before = [(turn, item) for turn, item in linked if turn < e8_turn]
        if before:
            initial_release = before[-1][1]
    revised_release = _revised_release(linked, initial_release, e8_turn, turns, view)
    if revised_release is None:
        findings.append("b7_revised_release_missing")
    if (
        plant_turn is None or e8_turn is None or not isinstance(dedup_text, str)
        or not _delivered_answer(turns, decision_key="event_deduplication", answer=dedup_text, after_turn=plant_turn, before_turn=e8_turn)
        or e8_turn is None or not isinstance(revised_text, str)
        or not (
            # The E8 card states the revised ruling itself and is linked to
            # this decision; a compliant agent has no reason to ask again.
            _card_delivered_decision(
                scenario, turns, card_id="B7-E8", decision_key="same_month_classification_revised",
            )
            or _delivered_answer(
                turns, decision_key="same_month_classification_revised",
                answer=revised_text, after_turn=e8_turn,
                before_turn=_published_turn(revised_release.run) if revised_release else None,
            )
        )
    ):
        if "b7_decision_exchange_missing" not in findings:
            findings.append("b7_decision_exchange_missing")

    first_decisions = _approved_decisions(initial_release) if initial_release else None
    final_decisions = _approved_decisions(revised_release) if revised_release else None
    if not _initial_ruling(_ruling(first_decisions, "same_month_classification", target="mrr_movement_amount_cents")) or not _revised_ruling(_ruling(final_decisions, "same_month_classification", target="mrr_movement_amount_cents")):
        findings.append("b7_decision_record_missing")
    if not _dedup_ruling(_ruling(final_decisions, "event_deduplication")):
        findings.append("b7_dedup_rule_missing")

    if revised_release is not None:
        if not _compiled_promise(revised_release):
            findings.append("b7_identity_promise_missing")
        if not _model_counts(revised_release.release):
            findings.append("b7_model_row_count_mismatch")
    queries = view.rows("query-history")
    waterfall = _latest_query(queries, _valid_waterfall)
    control = _latest_query(queries, _valid_controls)
    final_run = revised_release.run.get("run_id") if revised_release else None
    final_published = _published_turn(revised_release.run) if revised_release else None
    if (
        final_run is None or final_published is None or waterfall is None or control is None
        or waterfall.get("run_id") != final_run or control.get("run_id") != final_run
        or waterfall.get("workflow_id") != revised_release.release.get("workflow_id")
        or control.get("workflow_id") != revised_release.release.get("workflow_id")
        or waterfall["turn"] <= final_published or control["turn"] <= final_published
    ):
        findings.append("b7_final_query_run_mismatch")
    elif not _identity_holds(waterfall["rows"], control["rows"], controls_gold):
        findings.append("b7_identity_rows_differ")

    if (
        e3_turn is None or revised_release is None
        or _published_turn(revised_release.run) is None
        or e3_turn <= _published_turn(revised_release.run)
        or not _e3_resumed(
            view, e3_turn, revised_release.release.get("workflow_id"),
            revised_release.run.get("run_id"),
        )
    ):
        findings.append("b7_e3_resume_missing")
    return {"status": "examined", "passed": not findings, "findings": findings}


KIND = register(
    FollowUpKind(
        name="mrr_waterfall",
        gold_keys=frozenset({"answer", "controls", "diagnostics"}),
        handler=check,
        evidence_contract={
            "publication_ref": "reference to the published release you used for the final answer",
            "governed_query_refs": "references to the governed waterfall and monthly balance queries",
            "decision_refs": "references to the approved decision and blueprint snapshots for each release",
        },
        validate_settings=_validate_settings,
        validate_plant_evidence=_validate_plant,
        validate_fixture_gold=_validate_gold,
    )
)

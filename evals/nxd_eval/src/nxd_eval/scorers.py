"""Deterministic scorers — Inspect ``@scorer`` bodies, NO model call.

Each scorer reads what the agent actually did with the semantic tools out of the
``TaskState`` (via ``transcript.extract``) and returns a ``Score`` with
``CORRECT`` / ``INCORRECT`` (plus rich ``metadata`` for the report). None of
them call a model — the deterministic lane is fully offline.

The lane, scorer by scorer:

* ``rows_equal`` — deterministic execution-accuracy for ``answer`` cases. Wraps
  the cross-DP ``score.py`` core (``score_one`` / ``rows_equal_name_aware`` via
  ``nxd_eval.scoring``), so the swapped-two-measure guard and set/multiset modes
  are the PoC's, never re-implemented here.
* ``sql_contains`` / ``sql_excludes`` — substring assertions on the returned
  ``compiled_sql`` (e.g. must / must-not join a fan-out table).
* ``error_nonempty`` — fan-out / infeasible rejection: the tool returned an
  ``error`` (a compile refusal or execution failure), which for some cases is
  the CORRECT behaviour.
* ``slot_match`` — per-slot F1 (metric / dimensions / filters / grain) over the
  ``run_semantic_query`` args, EMA-combined across the agent's queries. A wrong
  dimension drops the score even when the rows coincide.
* ``expect_abstain`` — the feasible/abstain discriminator: an ``abstain`` case
  is CORRECT iff the agent refused/declined (no fabricated rows); a feasible
  (``answer`` / ``clarify``) case is CORRECT iff it did NOT spuriously abstain.

Stable slot names kept for the task wiring + report/certify: ``deterministic_ex``
(the ``rows_equal`` body for ``answer`` cases), ``abstain_infeasible`` (the
``expect_abstain`` body for ``clarify`` / ``abstain`` cases), ``slot_match``, and
the model-graded ``judge`` slot.
"""

from __future__ import annotations

import json
from typing import Any

from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    NOANSWER,
    PARTIAL,
    Score,
    Scorer,
    Target,
    accuracy,
    mean,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState

from . import scoring
from .metrics import applicable_accuracy
from .slots import Selection, ema, overall_f1, selection_of, slot_f1s
from .transcript import Transcript, extract

# Stable scorer names — the log keys report.py / certify.py read.
DETERMINISTIC_EX = "deterministic_ex"
ABSTAIN_INFEASIBLE = "abstain_infeasible"
SLOT_MATCH = "slot_match"
JUDGE = "judge"


# --------------------------------------------------------------------------- #
# Helpers shared across scorers
# --------------------------------------------------------------------------- #


def _gold_rows_from_target(target: Target) -> list[dict] | None:
    """Decode the JSON-encoded gold row-set out of the Sample target.

    The task layer JSON-encodes gold rows into the string target for ``answer``
    cases; ``clarify`` / ``abstain`` cases carry an empty target. Returns None
    when there is no decodable row-set (empty target or a non-row payload).
    """
    text = (target.text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, list) else None


def _gold_record(state: TaskState, gold_rows: list[dict] | None) -> dict[str, Any]:
    """Assemble the ``score.py`` gold-record dict for the EX core.

    ``equality_mode`` rides in Sample metadata when the suite pins multiset
    semantics; defaults to set-equality (the EX core's default).
    """
    meta = state.metadata or {}
    return {
        "question_id": state.sample_id,
        "rows": gold_rows,
        "equality_mode": meta.get("equality_mode", "set"),
    }


def _gold_selection(state: TaskState) -> Selection:
    """Gold slot selection for slot-F1, read from Sample metadata.

    A suite author pins the intended slots on the gold record
    (``measures`` / ``group_by`` / ``filters``); the task threads them into
    Sample metadata under ``gold_selection`` (or the bare keys). Absent ⇒ an
    empty selection, so an agent that queries nothing scores 1.0 only when gold
    is also empty.
    """
    meta = state.metadata or {}
    sel = meta.get("gold_selection") or {}
    return selection_of(
        measures=sel.get("measures") or meta.get("measures"),
        dimensions=sel.get("dimensions") or sel.get("group_by") or meta.get("group_by"),
        filters=sel.get("filters") or meta.get("filters"),
    )


# --------------------------------------------------------------------------- #
# rows_equal — deterministic execution-accuracy (answer cases)
# --------------------------------------------------------------------------- #


def _rows_equal_score(state: TaskState, target: Target) -> Score:
    # Deterministic-EX only applies to `answer` cases (rows to compare against
    # gold). For `clarify` / `abstain` cases there are no gold rows — the abstain
    # discriminator owns those. Skip (NOANSWER) so a mixed suite's raw scorer
    # summary is not dragged down by inapplicable cases; report.py already routes
    # per bucket, but this keeps the raw log honest too.
    bucket = (state.metadata or {}).get("bucket", "answer")
    if bucket != "answer":
        return Score(value=NOANSWER, metadata={"reason": f"deterministic-EX N/A for bucket={bucket}"})

    tx = extract(state)
    gold_rows = _gold_rows_from_target(target)
    call = tx.last_answered_call()
    actual_rows = call.rows if call is not None else None

    verdict = scoring.score_one(
        {
            "rows": actual_rows,
            "abstained": not tx.made_query or call is None,
            "errored": False,
        },
        _gold_record(state, gold_rows),
    )
    value = CORRECT if verdict == "PASS" else INCORRECT
    return Score(
        value=value,
        answer=json.dumps(actual_rows) if actual_rows is not None else "",
        metadata={
            "verdict": verdict,
            "made_query": tx.made_query,
            "n_queries": len(tx.calls),
            "compiled_sql": call.compiled_sql if call else None,
        },
    )


@scorer(name=DETERMINISTIC_EX, metrics=[applicable_accuracy(), stderr()])
def rows_equal() -> Scorer:
    """Deterministic-EX: agent's returned rows set/multiset-equal the gold rows.

    Delegates the verdict to the cross-DP ``score.py`` core, so two numeric
    measures SWAPPED is a FAIL (the name-aware guard) without re-implementing EX.
    """

    async def score(state: TaskState, target: Target) -> Score:
        return _rows_equal_score(state, target)

    return score


# Back-compat name kept for the existing task wiring / P1 tests.
deterministic_ex = rows_equal


# --------------------------------------------------------------------------- #
# sql_contains / sql_excludes — substring assertions on the compiled SQL
# --------------------------------------------------------------------------- #


def _compiled_sql(tx: Transcript) -> str | None:
    call = tx.last_answered_call()
    if call and call.compiled_sql:
        return call.compiled_sql
    # Fall back to the last call that carried any compiled_sql (even if errored).
    for c in reversed(tx.calls):
        if c.compiled_sql:
            return c.compiled_sql
    return None


@scorer(name="sql_contains", metrics=[accuracy(), stderr()])
def sql_contains(*needles: str, case_sensitive: bool = False) -> Scorer:
    """CORRECT iff every ``needle`` is a substring of the returned compiled SQL."""

    async def score(state: TaskState, target: Target) -> Score:
        sql = _compiled_sql(extract(state))
        if sql is None:
            return Score(value=INCORRECT, metadata={"reason": "no compiled_sql"})
        hay = sql if case_sensitive else sql.lower()
        want = list(needles) if case_sensitive else [n.lower() for n in needles]
        missing = [n for n in want if n not in hay]
        return Score(
            value=CORRECT if not missing else INCORRECT,
            answer=sql,
            metadata={"missing": missing},
        )

    return score


@scorer(name="sql_excludes", metrics=[accuracy(), stderr()])
def sql_excludes(*needles: str, case_sensitive: bool = False) -> Scorer:
    """CORRECT iff NONE of ``needles`` appear in the returned compiled SQL."""

    async def score(state: TaskState, target: Target) -> Score:
        sql = _compiled_sql(extract(state))
        if sql is None:
            # No SQL emitted ⇒ vacuously excludes everything.
            return Score(value=CORRECT, metadata={"reason": "no compiled_sql"})
        hay = sql if case_sensitive else sql.lower()
        want = list(needles) if case_sensitive else [n.lower() for n in needles]
        present = [n for n in want if n in hay]
        return Score(
            value=CORRECT if not present else INCORRECT,
            answer=sql,
            metadata={"present": present},
        )

    return score


# --------------------------------------------------------------------------- #
# error_nonempty — fan-out / infeasible rejection
# --------------------------------------------------------------------------- #


@scorer(name="error_nonempty", metrics=[accuracy(), stderr()])
def error_nonempty() -> Scorer:
    """CORRECT iff the tool returned a non-empty ``error`` (a refusal/failure).

    Used for cases where the RIGHT behaviour is the compiler refusing — a
    fan-out-unsafe join, an incompatible dimension. An agent that got rows back
    (no error) FAILs this scorer.
    """

    async def score(state: TaskState, target: Target) -> Score:
        tx = extract(state)
        errored = tx.any_error()
        err_text = next((c.error for c in reversed(tx.calls) if c.error), None)
        return Score(
            value=CORRECT if errored else INCORRECT,
            answer=err_text or "",
            metadata={"errored": errored, "n_queries": len(tx.calls)},
        )

    return score


# --------------------------------------------------------------------------- #
# slot_match — per-slot F1 + EMA over the agent's queries
# --------------------------------------------------------------------------- #


def _slot_match_score(state: TaskState, target: Target, *, threshold: float) -> Score:
    tx = extract(state)
    gold = _gold_selection(state)
    if not tx.calls:
        # No query at all — perfect only if gold selected nothing either.
        empty = selection_of()
        f1 = overall_f1(empty, gold)
        return Score(
            value=CORRECT if f1 >= threshold else INCORRECT,
            answer="",
            metadata={"slot_f1": f1, "per_slot": slot_f1s(empty, gold), "n_queries": 0},
        )

    per_query_f1: list[float] = []
    per_query_slots: list[dict[str, float]] = []
    for c in tx.calls:
        pred = selection_of(
            measures=c.measures, dimensions=c.dimensions, filters=c.filters
        )
        per_query_f1.append(overall_f1(pred, gold))
        per_query_slots.append(slot_f1s(pred, gold))

    combined = ema(per_query_f1)
    # Report the FINAL query's per-slot breakdown (the one it stands behind).
    return Score(
        value=CORRECT if combined >= threshold else INCORRECT,
        answer=f"{combined:.3f}",
        metadata={
            "slot_f1": combined,
            "per_slot": per_query_slots[-1],
            "per_query_f1": per_query_f1,
            "n_queries": len(tx.calls),
        },
    )


@scorer(name=SLOT_MATCH, metrics=[mean(), stderr()])
def slot_match(*, threshold: float = 0.999) -> Scorer:
    """Per-slot F1 (metric/dimensions/filters/grain) EMA-combined over queries.

    A wrong dimension drops the score (partial ``dimensions`` F1 + zero
    ``grain``). CORRECT iff the combined slot-F1 meets ``threshold`` (default
    near-exact); the continuous ``slot_f1`` metadata is the graded signal the
    report surfaces via the ``mean`` metric.
    """

    async def score(state: TaskState, target: Target) -> Score:
        return _slot_match_score(state, target, threshold=threshold)

    return score


# --------------------------------------------------------------------------- #
# expect_abstain — feasible / abstain discriminator
# --------------------------------------------------------------------------- #

# Surface markers of a refusal / clarify in the agent's final answer.
# Deliberately broad — the agent prompt tells it to "say so and ask or decline".
_ABSTAIN_MARKERS = (
    "cannot",
    "can't",
    "can not",
    "unable",
    "no such",
    "does not exist",
    "doesn't exist",
    "not available",
    "not possible",
    "not supported",
    "decline",
    "there is no",
    "do not have",
    "don't have",
    "not a valid",
    "invalid",
    "incompatible",
    "different grain",
    "ambiguous",
    "clarif",
    "which ",
    "do you mean",
    "rather than fabricate",
    "cannot combine",
    "can't combine",
)


def _looks_like_abstain(tx: Transcript) -> bool:
    """Heuristic: did the agent refuse/ask rather than return fabricated rows?

    Abstain evidence = it produced NO answered query (every query errored or it
    never queried) OR its final answer carries a refusal/clarify marker. A run
    that returned rows and asserted them with no refusal marker is NOT an
    abstain.
    """
    answered = tx.last_answered_call() is not None
    text = tx.final_answer.lower()
    marker = any(m in text for m in _ABSTAIN_MARKERS)
    if not answered:
        return True
    return marker


def _expect_abstain_score(state: TaskState, target: Target) -> Score:
    tx = extract(state)
    meta = state.metadata or {}
    feasible = bool(meta.get("feasible", True))
    abstained = _looks_like_abstain(tx)

    if feasible:
        # Feasible question: correct = did NOT spuriously abstain.
        value = INCORRECT if abstained else CORRECT
    else:
        # Infeasible (abstain) question: correct = refused, no fabrication.
        value = CORRECT if abstained else INCORRECT

    return Score(
        value=value,
        answer=tx.final_answer,
        metadata={
            "feasible": feasible,
            "abstained": abstained,
            "made_query": tx.made_query,
            "any_error": tx.any_error(),
        },
    )


@scorer(name=ABSTAIN_INFEASIBLE, metrics=[accuracy(), stderr()])
def expect_abstain() -> Scorer:
    """Feasible/abstain discriminator for ``clarify`` / ``abstain`` cases.

    An ``abstain`` (infeasible) case is CORRECT iff the agent refused without
    fabricating rows; a feasible case is CORRECT iff it did NOT spuriously
    abstain. Reads the routing flag from Sample metadata (``feasible``).
    """

    async def score(state: TaskState, target: Target) -> Score:
        return _expect_abstain_score(state, target)

    return score


# Back-compat name kept for the existing task wiring / P1 tests.
abstain_infeasible = expect_abstain


# --------------------------------------------------------------------------- #
# judge — model-graded slot (body lands with the judged-scoring layer)
# --------------------------------------------------------------------------- #


_JUDGE_SYSTEM = (
    "You are a rigorous grader for a governed data-product query agent. You are "
    "given the analyst's QUESTION, a summary of what the agent DID (its tool "
    "calls and whether they returned rows or errored), the agent's final ANSWER, "
    "and a list of CRITERIA the answer must satisfy. Grade whether the answer "
    "satisfies ALL criteria. Reply with your reasoning, then on the last line "
    "exactly one of: GRADE: C (all criteria met), GRADE: P (some met), or "
    "GRADE: I (criteria not met). Judge only against the criteria — do not "
    "invent requirements."
)


def _judge_prompt(question: str, tx: "Transcript", checks: list[str]) -> str:
    trail = []
    for c in tx.calls:
        status = "errored" if c.errored else (f"{len(c.rows)} rows" if c.rows is not None else "no rows")
        trail.append(f"- run_semantic_query → {status}")
    did = "\n".join(trail) if trail else "- (no run_semantic_query calls)"
    criteria = "\n".join(f"{i}. {c}" for i, c in enumerate(checks, 1))
    return (
        f"QUESTION:\n{question}\n\n"
        f"WHAT THE AGENT DID:\n{did}\n\n"
        f"AGENT'S FINAL ANSWER:\n{tx.final_answer}\n\n"
        f"CRITERIA:\n{criteria}\n\n"
        "Grade now. End with GRADE: C, GRADE: P, or GRADE: I."
    )


def _parse_grade(text: str) -> str:
    import re

    m = re.findall(r"GRADE:\s*([CPI])", text.upper())
    if not m:
        return NOANSWER
    g = m[-1]
    return {"C": CORRECT, "P": PARTIAL, "I": INCORRECT}[g]


@scorer(name=JUDGE, metrics=[mean(), stderr()])
def judge() -> Scorer:
    """Model-graded checks slot: grades the agent's answer against the sample's
    bucket check list (``judge_checks`` in Sample metadata, from the suite's
    ``checks()`` / ``checks.json``) using the ``grader`` model role.

    Returns NOANSWER when the sample carries no checks (nothing to grade), so a
    suite without a check for a bucket does not penalise it. The mean metric then
    reflects only graded samples.
    """
    from inspect_ai.model import ChatMessageSystem, ChatMessageUser, get_model

    async def score(state: TaskState, target: Target) -> Score:
        meta = state.metadata or {}
        checks = list(meta.get("judge_checks", []) or [])
        if not checks:
            return Score(value=NOANSWER, metadata={"reason": "no checks for bucket"})

        tx = extract(state)
        model = get_model(role="grader", default=None) or get_model()
        prompt = _judge_prompt(str(state.input), tx, checks)
        result = await model.generate(
            [
                ChatMessageSystem(content=_JUDGE_SYSTEM),
                ChatMessageUser(content=prompt),
            ]
        )
        grade = _parse_grade(result.completion)
        return Score(
            value=grade,
            answer=tx.final_answer,
            explanation=result.completion[:2000],
            metadata={"n_checks": len(checks)},
        )

    return score


# --------------------------------------------------------------------------- #
# Check-set → scorer resolution (checks.* from the authoring layer)
# --------------------------------------------------------------------------- #


def scorers_for(suite) -> list[Scorer]:  # noqa: ANN001 - Suite, avoid import cycle
    """The scorer slot list a suite attaches, resolved from its check buckets.

    Always attaches the deterministic-EX (``rows_equal``) and abstain/infeasible
    (``expect_abstain``) discriminators plus ``slot_match`` — the deterministic
    lane every suite runs. The model-graded ``judge`` slot is added only when the
    suite carries checks (typed or back-compat), matching the prior contract.
    Order is stable: deterministic-EX is the primary axis certify() gates on.
    """
    out: list[Scorer] = [rows_equal(), expect_abstain(), slot_match()]
    if getattr(suite, "checks", None):
        out.append(judge())
    return out

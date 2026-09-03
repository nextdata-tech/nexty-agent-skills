"""Tests for the read-only adversarial-review rig and construction oracle."""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.reviewer import (
    AdjudicationState,
    RecordedClaims,
    ReviewDispatchError,
    ReviewLedger,
    SeededDefect,
    adjudicate_review,
    closure_content_digest,
    coerce_review_ledger,
    dispatch_review,
    gate_construction_claims,
    score_review,
)
from dp_scenarios.grading.oracles import OracleState


def _closure(tmp_path: Path, text: str = "grain: order\n") -> Path:
    root = tmp_path / "closure"
    root.mkdir()
    (root / "semantic.py").write_text(text, encoding="utf-8")
    return root


def _claim(claim_id: str, statement: str = "the closure has a defect") -> dict[str, object]:
    return {
        "id": claim_id,
        "severity": "HIGH",
        "claim": statement,
        "evidence": "semantic.py:1",
        "why_it_matters": "a consumer can receive a wrong answer",
    }


def test_dispatch_uses_read_only_snapshot_and_keeps_identity_out_of_prose(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    observed: list[tuple[Path, str]] = []

    def reviewer(snapshot: Path, request: str) -> object:
        observed.append((snapshot, request))
        assert snapshot != closure
        with pytest.raises(PermissionError):
            (snapshot / "should-not-write").write_text("no", encoding="utf-8")
        return {"claims": [_claim("wrong-grain", "first wording")]}

    before = (closure / "semantic.py").read_bytes()
    first = dispatch_review(closure, "  verbatim request\n", reviewer=reviewer)
    second = dispatch_review(
        closure,
        "  verbatim request\n",
        reviewer=lambda _snapshot, _request: {"claims": [_claim("wrong-grain", "rephrased wording")]},
    )

    assert first.examined and second.examined
    assert first.claims[0].identity == second.claims[0].identity
    assert first.claims[0].claim != second.claims[0].claim
    assert observed[0][1] == "  verbatim request\n"
    assert (closure / "semantic.py").read_bytes() == before


def test_recorded_claims_are_selected_by_closure_content_digest(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    digest = closure_content_digest(closure)
    run = dispatch_review(
        closure,
        "original",
        recorded_claims=RecordedClaims({digest: {"claims": [_claim("null-handling")]}}),
    )
    assert run.examined
    assert run.mode == "recorded"
    assert run.claims[0].claim_id == "null-handling"


def test_construction_is_not_examined_when_reviewer_fails(tmp_path: Path) -> None:
    closure = _closure(tmp_path)

    def failing_reviewer(_snapshot: Path, _request: str) -> object:
        raise RuntimeError("review provider unavailable")

    run = dispatch_review(closure, "request", reviewer=failing_reviewer)
    result = gate_construction_claims(ReviewLedger.from_run(run), [SeededDefect("wrong-grain")])

    assert not run.examined
    assert result.state is OracleState.NOT_EXAMINED
    assert result.outcome == "not-examined"
    assert not result.passed
    assert "construction_reviewer_failed" in {finding.code for finding in result.findings}


def test_uncited_rejection_is_unadjudicated_and_not_a_pass(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": [_claim("x")]})
    claim_identity = run.claims[0].identity

    ledger = adjudicate_review(
        run,
        {claim_identity: {"status": "rejected-with-citation"}},
    )
    assert ledger.entries[0].status is AdjudicationState.UNADJUDICATED
    assert ledger.entries[0].adjudication.citation is None
    score = score_review(ledger, ["x"])
    assert score.unadjudicated_claims == 1
    assert score.claims_about_nothing_planted == 0
    assert score.precision_ratio.fraction == "0/0"
    assert gate_construction_claims(ledger, ["x"]).state is OracleState.NOT_EXAMINED


def test_citation_backed_rejection_counts_as_a_false_positive(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": [_claim("x")]})
    ledger = adjudicate_review(
        run,
        {run.claims[0].identity: {"status": "rejected-with-citation", "citation": "semantic.py:1"}},
    )

    assert ledger.entries[0].status is AdjudicationState.REJECTED_WITH_CITATION
    score = score_review(ledger, ["x"])
    assert score.claims_about_nothing_planted == 1
    assert score.unadjudicated_claims == 0
    assert score.precision_ratio.fraction == "0/1"
    assert gate_construction_claims(ledger, ["x"]).state is OracleState.VIOLATED


def test_score_reports_recall_precision_counts_and_one_attempt_qualification(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(
        closure,
        "request",
        reviewer=lambda _path, _request: {
            "claims": [_claim("grain"), _claim("extra")],
        },
    )
    ledger = adjudicate_review(
        run,
        {
            run.claims[0].identity: {"status": "upheld", "defect_ids": ["grain"]},
            run.claims[1].identity: {"status": "rejected-with-citation", "citation": "semantic.py:1"},
        },
    )

    score = score_review(ledger, ["grain", "nulls"])
    assert score.found_defects == ("grain",)
    assert score.missed_defects == ("nulls",)
    assert score.true_positive_claims == 1
    assert score.claims_about_nothing_planted == 1
    assert score.recall_ratio.fraction == "1/2"
    assert score.precision_ratio.fraction == "1/2"
    assert score.qualification == "demonstrated-once"
    assert score.as_dict()["recall"] == {"numerator": 1, "denominator": 2, "ratio": "1/2"}


def test_zero_claims_from_a_healthy_review_do_not_hide_seeded_misses(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": []})
    result = gate_construction_claims(run, ["wrong-grain"])

    assert result.state is OracleState.VIOLATED
    assert "construction_seeded_defect_missed" in {finding.code for finding in result.findings}


def test_serialized_ledger_normalizes_uncited_and_nonexistent_rejections(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": [_claim("x")]})
    base = {
        "closure_path": str(closure),
        "closure_digest": run.closure_digest,
        "reviewer_ran": True,
        "rows": [],
    }

    for adjudication in (
        {"status": "rejected-with-citation", "citation": None},
        {"status": "rejected-with-citation", "citation": "does-not-exist.py:99999"},
    ):
        payload = {
            **base,
            "rows": [{"claim": run.claims[0].as_dict(), "adjudication": adjudication}],
        }
        ledger = coerce_review_ledger(payload)
        assert ledger.entries[0].status is AdjudicationState.UNADJUDICATED
        assert gate_construction_claims(ledger, []).state is OracleState.NOT_EXAMINED


def test_serialized_reviewer_status_cannot_adjudicate_its_own_claim(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": [_claim("self")]})
    payload = run.as_dict()
    payload["claims"] = [{**run.claims[0].as_dict(), "status": "rejected-with-citation"}]

    ledger = coerce_review_ledger(payload)

    assert ledger.entries[0].status is AdjudicationState.UNADJUDICATED
    assert gate_construction_claims(ledger, []).state is OracleState.NOT_EXAMINED


def test_serialized_and_typed_ledgers_have_the_same_verdict(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": [_claim("x")]})
    typed = adjudicate_review(
        run,
        {run.claims[0].identity: {"status": "rejected-with-citation"}},
    )
    serialized = typed.as_dict()
    serialized["rows"] = typed.to_rows()

    typed_result = gate_construction_claims(typed, [])
    serialized_result = gate_construction_claims(serialized, [])

    assert typed_result.state is OracleState.NOT_EXAMINED
    assert serialized_result.state is typed_result.state


def test_unreadable_closure_is_not_examined(tmp_path: Path) -> None:
    missing = tmp_path / "unreadable-closure"
    ledger = ReviewLedger(missing, "not-a-real-digest", True, "reviewer")

    result = gate_construction_claims(ledger, [])

    assert result.state is OracleState.NOT_EXAMINED
    assert "construction_closure_not_examined" in result.codes


def test_claim_identity_is_stable_when_claim_order_changes(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    first = dispatch_review(
        closure,
        "request",
        reviewer=lambda _path, _request: {"claims": [_claim("grain"), _claim("nulls")]},
    )
    second = dispatch_review(
        closure,
        "request",
        reviewer=lambda _path, _request: {"claims": [_claim("nulls"), _claim("grain")]},
    )

    first_by_id = {claim.claim_id: claim.identity for claim in first.claims}
    second_by_id = {claim.claim_id: claim.identity for claim in second.claims}
    assert first_by_id == second_by_id


def test_idless_claim_is_malformed_reviewer_output(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(
        closure,
        "request",
        reviewer=lambda _path, _request: {"claims": [{"claim": "missing identity", "evidence": "semantic.py:1"}]},
    )

    assert not run.examined
    assert "no id" in (run.error or "")


def test_missing_declaration_is_not_a_zero_defect_declaration(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": []})

    score = score_review(run, {"planted_defects": ["grain"]})
    result = gate_construction_claims(run, {"planted_defects": ["grain"]})

    assert not score.declaration_examined
    assert not score.examined
    assert score.qualification == "not-claimed"
    assert result.state is OracleState.NOT_EXAMINED
    assert "construction_seeded_defects_not_declared" in result.codes


def test_explicit_empty_declaration_remains_examined(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": []})

    score = score_review(run, [])

    assert score.declaration_examined
    assert score.examined
    assert score.qualification == "demonstrated-once"


def test_one_attempt_ratio_value_is_not_a_rate(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": []})
    score = score_review(run, [])

    with pytest.raises(ValueError, match="demonstrated-once observations cannot be represented as rates"):
        _ = score.recall.value


def test_configuring_reviewer_and_recorded_claims_is_loud(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    digest = closure_content_digest(closure)

    with pytest.raises(ReviewDispatchError, match="either reviewer or recorded_claims"):
        dispatch_review(
            closure,
            "request",
            reviewer=lambda _path, _request: {"claims": []},
            recorded_claims=RecordedClaims({digest: {"claims": []}}),
        )


def test_a_flat_row_cannot_carry_its_own_adjudication(tmp_path: Path) -> None:
    """A flat row IS the claim, so its `adjudication` key is reviewer-authored.

    Honouring it would let the reviewer adjudicate itself, which is the one
    thing the two-column ledger exists to prevent.
    """

    closure = _closure(tmp_path)
    run = dispatch_review(closure, "request", reviewer=lambda _path, _request: {"claims": [_claim("self")]})
    flat_row = {
        **run.claims[0].as_dict(),
        "adjudication": {"status": "rejected-with-citation", "citation": "semantic.py:1"},
    }
    payload = {
        "closure_path": str(closure),
        "closure_digest": run.closure_digest,
        "reviewer_ran": True,
        "rows": [flat_row],
    }

    ledger = coerce_review_ledger(payload)

    assert ledger.entries[0].status is AdjudicationState.UNADJUDICATED
    assert gate_construction_claims(ledger, []).state is OracleState.NOT_EXAMINED

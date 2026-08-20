"""G4 wiring for the adversarial-review claim ledger."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path

from dp_scenarios.grading.oracles import OracleFinding, OracleResult, OracleState

from .adjudication import normalize_adjudication
from .dispatch import closure_content_digest
from .models import (
    Adjudication,
    AdjudicationState,
    ClaimLedgerEntry,
    ReviewLedger,
    ReviewRun,
    ReviewerClaim,
)
from .scoring import score_review


def _claim_from_mapping(
    value: Mapping[str, object],
    index: int,
    closure_digest: str | None = None,
) -> ReviewerClaim:
    raw = value.get("raw") if isinstance(value.get("raw"), Mapping) else value
    raw_mapping = dict(raw) if isinstance(raw, Mapping) else {}
    claim_id = value.get(
        "id",
        value.get("claim_id", raw_mapping.get("id", raw_mapping.get("claim_id"))),
    )
    if not isinstance(claim_id, str) or not claim_id.strip():
        raise ValueError(f"serialized review claim {index} has no id")
    claim_id = claim_id.strip()
    statement = value.get("claim", raw_mapping.get("claim", ""))
    severity = value.get("severity", raw_mapping.get("severity", "UNKNOWN"))
    reason = value.get("reason", value.get("reviewer_reason", raw_mapping.get("reason", "")))
    evidence = value.get("evidence", raw_mapping.get("evidence"))
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError(f"serialized review claim {index} has no evidence")
    identity = value.get("identity", value.get("claim_identity", raw_mapping.get("identity")))
    if not isinstance(identity, str) or not identity.strip():
        if closure_digest is None:
            raise ValueError(f"serialized review claim {index} has no identity")
        identity = hashlib.sha256(
            f"{closure_digest}\0{claim_id}\0{evidence.strip()}".encode("utf-8")
        ).hexdigest()
    why = value.get("why_it_matters", raw_mapping.get("why_it_matters"))
    return ReviewerClaim(
        claim_id=claim_id,
        identity=identity.strip(),
        severity=severity if isinstance(severity, str) else "UNKNOWN",
        claim=statement if isinstance(statement, str) else "",
        evidence=evidence,
        reviewer_reason=reason if isinstance(reason, str) else "",
        why_it_matters=why if isinstance(why, str) else None,
        raw=raw_mapping,
    )


def _entry_from_mapping(
    value: Mapping[str, object],
    index: int,
    closure_path: Path | None,
    closure_digest: str | None,
) -> ClaimLedgerEntry:
    claim_value = value.get("claim")
    nested_claim = isinstance(claim_value, Mapping)
    if nested_claim:
        claim = _claim_from_mapping(claim_value, index, closure_digest)
    else:
        claim = _claim_from_mapping(value, index, closure_digest)
    # A flat row IS the claim, so every key on it -- `adjudication` included --
    # is reviewer-authored.  Only a row that separates the two columns can carry
    # a builder adjudication.
    adjudication_value = value.get("adjudication") if nested_claim else None
    if closure_path is None:
        adjudication = Adjudication(
            AdjudicationState.UNADJUDICATED,
            note="serialized adjudication cannot be validated without a closure path",
        )
    else:
        # Only a nested adjudication object is a builder column.  Claim-level
        # status/citation/defect fields are reviewer-authored and ignored.
        adjudication = normalize_adjudication(
            closure_path,
            adjudication_value if isinstance(adjudication_value, Mapping) else None,
        )
    return ClaimLedgerEntry(
        claim,
        adjudication,
    )


def coerce_review_ledger(value: object) -> ReviewLedger:
    """Accept the typed ledger or its JSON-compatible representation."""

    if isinstance(value, ReviewLedger):
        return value
    if isinstance(value, ReviewRun):
        return ReviewLedger.from_run(value)
    if not isinstance(value, Mapping):
        return ReviewLedger(None, None, False, "invalid", error="review ledger is not a mapping")
    closure = value.get("closure_path")
    closure_path = Path(closure) if isinstance(closure, str) else None
    closure_digest = value.get("closure_digest") if isinstance(value.get("closure_digest"), str) else None
    mode = value.get("mode", "mapping") if isinstance(value.get("mode", "mapping"), str) else "mapping"
    raw_rows = value.get("rows", value.get("entries"))
    if raw_rows is None and isinstance(value.get("claims"), Sequence):
        raw_rows = tuple({"claim": claim} for claim in value["claims"] if isinstance(claim, Mapping))
    if raw_rows is None:
        raw_rows = ()
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
        raw_rows = ()
    try:
        entries = tuple(
            _entry_from_mapping(row, index, closure_path, closure_digest)
            for index, row in enumerate(raw_rows, start=1)
            if isinstance(row, Mapping)
        )
    except (TypeError, ValueError) as exc:
        return ReviewLedger(
            closure_path,
            closure_digest,
            False,
            mode,
            error=f"invalid serialized review ledger: {exc}",
        )
    return ReviewLedger(
        closure_path,
        closure_digest,
        bool(value.get("reviewer_ran", value.get("examined", False))),
        mode,
        entries,
        value.get("error") if isinstance(value.get("error"), str) else None,
    )


def gate_g4(ledger: object, seeded_defects: object = None) -> OracleResult:
    """Evaluate G4 as a three-state, fail-closed oracle.

    A clean review satisfies G4 only when every claim is adjudicated and no
    claim is upheld.  Known seeded defects missed by the reviewer violate the
    gate when the scenario supplies their explicit declaration.  A failed or
    incomplete review is ``not-examined`` and never a pass.
    """

    review = coerce_review_ledger(ledger)
    if not review.examined:
        if review.error:
            code = "g4_reviewer_failed"
            detail = review.error
        elif not review.reviewer_ran:
            code = "g4_reviewer_not_run"
            detail = "adversarial reviewer did not run"
        else:
            code = "g4_closure_not_examined"
            detail = "closure was not readable or its digest could not be verified"
        return OracleResult(
            OracleState.NOT_EXAMINED,
            value=review,
            findings=(OracleFinding(code, detail),),
        )

    if review.closure_path is None or review.closure_digest is None:
        return OracleResult(
            OracleState.NOT_EXAMINED,
            value=review,
            findings=(OracleFinding("g4_closure_not_examined", "closure identity is absent"),),
        )
    try:
        if closure_content_digest(review.closure_path) != review.closure_digest:
            return OracleResult(
                OracleState.NOT_EXAMINED,
                value=review,
                findings=(OracleFinding("g4_closure_changed", "closure digest no longer matches review"),),
            )
    except Exception as exc:
        return OracleResult(
            OracleState.NOT_EXAMINED,
            value=review,
            findings=(OracleFinding("g4_closure_not_examined", str(exc)),),
        )

    score = score_review(review, seeded_defects)
    if not score.declaration_examined:
        return OracleResult(
            OracleState.NOT_EXAMINED,
            value=score,
            findings=(
                OracleFinding(
                    "g4_seeded_defects_not_declared",
                    "scenario did not provide a recognized seeded-defect declaration",
                ),
            ),
        )
    if review.unadjudicated:
        return OracleResult(
            OracleState.NOT_EXAMINED,
            value=score,
            findings=(
                OracleFinding(
                    "g4_claim_unadjudicated",
                    "every reviewer claim needs a builder adjudication",
                    len(review.unadjudicated),
                ),
            ),
        )

    upheld = [entry for entry in review.entries if entry.status is AdjudicationState.UPHELD]
    findings: list[OracleFinding] = []
    for entry in upheld:
        findings.append(
            OracleFinding(
                "g4_claim_upheld",
                "adversarial review found a defect in the closure",
                entry.identity,
            )
        )
    if score.missed_defects:
        findings.append(
            OracleFinding(
                "g4_seeded_defect_missed",
                "review did not find every scenario-declared defect",
                list(score.missed_defects),
            )
        )
    if findings:
        return OracleResult(OracleState.VIOLATED, value=score, findings=tuple(findings))
    return OracleResult(OracleState.SATISFIED, value=score)


__all__ = ["coerce_review_ledger", "gate_g4"]

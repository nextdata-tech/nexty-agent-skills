"""Builder-side claim adjudication and closure citation validation."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

from .dispatch import closure_content_digest
from .models import (
    Adjudication,
    AdjudicationState,
    ClaimLedgerEntry,
    ReviewLedger,
    ReviewRun,
    ReviewerClaim,
)


Adjudicator = Callable[[Path, ReviewerClaim], object]
_CITATION_RE = re.compile(r"^(?P<path>.+):(?P<line>[1-9][0-9]*)$")


def citation_in_closure(closure: str | Path, citation: object) -> bool:
    """Return whether ``citation`` names an existing closure file and line."""

    if not isinstance(citation, str) or not citation.strip():
        return False
    match = _CITATION_RE.fullmatch(citation.strip())
    if match is None:
        return False
    root = Path(closure)
    relative = Path(match.group("path"))
    if relative.is_absolute() or ".." in relative.parts:
        return False
    line_number = int(match.group("line"))
    try:
        if root.is_dir():
            candidate = root / relative
            base = root.resolve()
        elif root.is_file():
            if relative.as_posix() not in {root.name, "."}:
                return False
            candidate = root
            base = root.parent.resolve()
        else:
            return False
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(base) or not resolved.is_file():
            return False
        line_count = len(resolved.read_bytes().splitlines())
    except (OSError, RuntimeError, ValueError):
        return False
    return 1 <= line_number <= line_count


def _status(value: object) -> AdjudicationState | None:
    if isinstance(value, AdjudicationState):
        return value
    if isinstance(value, str):
        if value == "rejected":
            return AdjudicationState.REJECTED_WITH_CITATION
        try:
            return AdjudicationState(value)
        except ValueError:
            return None
    return None


def _defect_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = tuple(value)
    else:
        return ()
    result: list[str] = []
    for item in values:
        if isinstance(item, str) and item.strip() and item.strip() not in result:
            result.append(item.strip())
    return tuple(result)


def normalize_adjudication(
    closure: str | Path,
    value: object,
) -> Adjudication:
    """Normalize builder output and fail closed on an uncited rejection."""

    if isinstance(value, Adjudication):
        candidate = value
    elif isinstance(value, Mapping):
        status = _status(value.get("status", value.get("adjudication")))
        candidate = Adjudication(
            status or AdjudicationState.UNADJUDICATED,
            value.get("citation") if isinstance(value.get("citation"), str) else None,
            _defect_ids(value.get("defect_ids", value.get("defects"))),
            value.get("note", "") if isinstance(value.get("note", ""), str) else "",
        )
    else:
        candidate = Adjudication(AdjudicationState.UNADJUDICATED, note="no adjudication returned")

    if candidate.status is AdjudicationState.REJECTED_WITH_CITATION:
        if not citation_in_closure(closure, candidate.citation):
            return Adjudication(
                AdjudicationState.UNADJUDICATED,
                note="rejection requires a citation into the closure",
            )
        return candidate
    if candidate.status is AdjudicationState.UPHELD:
        return candidate
    return Adjudication(
        AdjudicationState.UNADJUDICATED,
        candidate.citation,
        note=candidate.note,
    )


def adjudicate_claim(
    closure: str | Path,
    claim: ReviewerClaim,
    adjudication: object,
) -> Adjudication:
    """Adjudicate one claim, validating any rejection citation."""

    del claim  # The claim is passed for the caller's decision; validation is artifact-owned.
    return normalize_adjudication(closure, adjudication)


def _adjudicator_value(
    adjudicator: Adjudicator | Mapping[str, object],
    closure: Path,
    claim: ReviewerClaim,
) -> object:
    if isinstance(adjudicator, Mapping):
        return adjudicator.get(claim.identity, adjudicator.get(claim.claim_id))
    return adjudicator(closure, claim)


def adjudicate_review(
    review: ReviewRun | ReviewLedger,
    adjudicator: Adjudicator | Mapping[str, object],
) -> ReviewLedger:
    """Have a builder adjudicate every claim against the original closure.

    The callback receives the original closure, not the reviewer's snapshot.
    The digest is checked immediately before adjudication so a changed closure
    cannot silently inherit an earlier review.
    """

    ledger = ReviewLedger.from_run(review) if isinstance(review, ReviewRun) else review
    if not ledger.examined or ledger.closure_path is None or ledger.closure_digest is None:
        return ledger
    try:
        if closure_content_digest(ledger.closure_path) != ledger.closure_digest:
            return replace(ledger, reviewer_ran=False, error="closure changed before adjudication")
    except Exception as exc:
        return replace(ledger, reviewer_ran=False, error=str(exc) or exc.__class__.__name__)

    entries: list[ClaimLedgerEntry] = []
    for entry in ledger.entries:
        try:
            raw = _adjudicator_value(adjudicator, ledger.closure_path, entry.claim)
            disposition = adjudicate_claim(ledger.closure_path, entry.claim, raw)
        except Exception as exc:
            disposition = Adjudication(
                AdjudicationState.UNADJUDICATED,
                note=str(exc) or exc.__class__.__name__,
            )
        entries.append(ClaimLedgerEntry(entry.claim, disposition))
    return replace(ledger, entries=tuple(entries))


__all__ = [
    "Adjudicator",
    "adjudicate_claim",
    "adjudicate_review",
    "citation_in_closure",
    "normalize_adjudication",
]

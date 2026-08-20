"""Convenience facade for the complete reviewer measurement flow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .adjudication import Adjudicator, adjudicate_review
from .dispatch import RecordedClaims, ReviewDispatcher, Reviewer
from .gate import gate_g4
from .models import ReviewLedger, ReviewRun, ReviewScore
from .scoring import score_review


@dataclass(frozen=True, slots=True)
class ReviewerRig:
    """Run, adjudicate, score, and gate one closure review."""

    reviewer: Reviewer | object | None = None
    recorded_claims: RecordedClaims | Mapping[str, object] | None = None

    def dispatch(self, closure: str | Path, original_request: str) -> ReviewRun:
        """Dispatch the configured reviewer or recorded-claims source."""

        return ReviewDispatcher(
            reviewer=self.reviewer,
            recorded_claims=self.recorded_claims,
        ).dispatch(closure, original_request)

    def adjudicate(
        self,
        review: ReviewRun | ReviewLedger,
        adjudicator: Adjudicator | Mapping[str, object],
    ) -> ReviewLedger:
        """Apply builder adjudications against the original closure."""

        return adjudicate_review(review, adjudicator)

    def score(self, review: ReviewRun | ReviewLedger, seeded_defects: object = None) -> ReviewScore:
        """Return recall/precision counts and count ratios."""

        return score_review(review, seeded_defects)

    def gate(self, ledger: ReviewLedger | Mapping[str, object], seeded_defects: object = None) -> object:
        """Return the three-state G4 result."""

        return gate_g4(ledger, seeded_defects)


__all__ = ["ReviewerRig"]

"""Immutable records used by the adversarial-review rig.

The reviewer produces claims only.  In particular, reviewer output never
contains an adjudication that this module will accept: adjudications are
created by the separate builder-facing adjudication step.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from dp_scenarios.ledger.schema import QUALIFICATIONS


def _qualification_for(examined: bool) -> str:
    """Return a reviewer qualification from the ledger's closed vocabulary."""

    qualification = "demonstrated-once" if examined else "not-claimed"
    if qualification not in QUALIFICATIONS:
        raise RuntimeError(f"review qualification is not in the ledger vocabulary: {qualification}")
    return qualification


class AdjudicationState(str, Enum):
    """The closed vocabulary for a claim's builder adjudication."""

    UPHELD = "upheld"
    REJECTED_WITH_CITATION = "rejected-with-citation"
    UNADJUDICATED = "unadjudicated"


@dataclass(frozen=True, slots=True)
class ReviewerClaim:
    """One untrusted claim returned by the reviewer.

    ``claim_id`` is the reviewer's identity field from the shipped skill.  The
    opaque ``identity`` additionally binds it to the reviewed closure digest,
    so the same reviewer id on a different closure is a different claim.
    """

    claim_id: str
    identity: str
    severity: str
    claim: str
    evidence: str | None
    reviewer_reason: str
    why_it_matters: str | None
    raw: Mapping[str, object]

    @property
    def reason(self) -> str:
        """Compatibility spelling for the reviewer's stated reason."""

        return self.reviewer_reason

    def as_dict(self) -> dict[str, object]:
        """Return the claim without adding an adjudication."""

        return {
            "id": self.claim_id,
            "identity": self.identity,
            "severity": self.severity,
            "claim": self.claim,
            "evidence": self.evidence,
            "reason": self.reviewer_reason,
            "why_it_matters": self.why_it_matters,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True, slots=True)
class Adjudication:
    """A builder's disposition of one reviewer claim.

    ``defect_ids`` are supplied by the adjudicator after it reads the closure;
    they are never copied from reviewer output.  A rejection is normalized to
    ``unadjudicated`` unless ``citation`` points to a real closure file and
    line.
    """

    status: AdjudicationState
    citation: str | None = None
    defect_ids: tuple[str, ...] = ()
    note: str = ""

    @property
    def rejected(self) -> bool:
        """Whether this is a citation-backed rejection."""

        return self.status is AdjudicationState.REJECTED_WITH_CITATION

    def as_dict(self) -> dict[str, object]:
        """Return the adjudication in ledger form."""

        return {
            "status": self.status.value,
            "citation": self.citation,
            "defect_ids": list(self.defect_ids),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class ClaimLedgerEntry:
    """One row in the claim-to-adjudication ledger."""

    claim: ReviewerClaim
    adjudication: Adjudication

    @property
    def identity(self) -> str:
        """Return the stable claim identity used for re-runs."""

        return self.claim.identity

    @property
    def status(self) -> AdjudicationState:
        """Return the adjudication state."""

        return self.adjudication.status

    def as_dict(self) -> dict[str, object]:
        """Return the explicit two-column representation."""

        return {
            "claim": self.claim.as_dict(),
            "adjudication": self.adjudication.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ReviewRun:
    """The dispatch result before builder adjudication."""

    closure_path: Path | None
    closure_digest: str | None
    claims: tuple[ReviewerClaim, ...]
    reviewer_ran: bool
    mode: str
    error: str | None = None

    @property
    def examined(self) -> bool:
        """Whether a reviewer completed against a readable closure."""

        return self.reviewer_ran and self.closure_digest is not None and self.error is None

    @property
    def qualification(self) -> str:
        """Return the ledger vocabulary for this single review attempt."""

        return _qualification_for(self.examined)

    def as_dict(self) -> dict[str, object]:
        """Return a serializable dispatch record."""

        return {
            "closure_path": str(self.closure_path) if self.closure_path is not None else None,
            "closure_digest": self.closure_digest,
            "claims": [claim.as_dict() for claim in self.claims],
            "reviewer_ran": self.reviewer_ran,
            "mode": self.mode,
            "error": self.error,
            "qualification": self.qualification,
        }


@dataclass(frozen=True, slots=True)
class ReviewLedger:
    """The append-only claim/adjudication ledger for one review attempt."""

    closure_path: Path | None
    closure_digest: str | None
    reviewer_ran: bool
    mode: str
    entries: tuple[ClaimLedgerEntry, ...] = ()
    error: str | None = None

    @classmethod
    def from_run(cls, run: ReviewRun) -> "ReviewLedger":
        """Create an unadjudicated ledger from a dispatch result."""

        entries = tuple(
            ClaimLedgerEntry(claim, Adjudication(AdjudicationState.UNADJUDICATED))
            for claim in run.claims
        )
        return cls(
            closure_path=run.closure_path,
            closure_digest=run.closure_digest,
            reviewer_ran=run.reviewer_ran,
            mode=run.mode,
            entries=entries,
            error=run.error,
        )

    @property
    def examined(self) -> bool:
        """Whether dispatch completed and the closure was readable."""

        return self.reviewer_ran and self.closure_digest is not None and self.error is None

    @property
    def qualification(self) -> str:
        """Return the one-attempt qualification, never a percentage claim."""

        return _qualification_for(self.examined)

    @property
    def claims(self) -> tuple[ReviewerClaim, ...]:
        """Return all reviewer claims in stable ledger order."""

        return tuple(entry.claim for entry in self.entries)

    @property
    def unadjudicated(self) -> tuple[ClaimLedgerEntry, ...]:
        """Return claims for which the builder has not produced a finding."""

        return tuple(
            entry
            for entry in self.entries
            if entry.status is AdjudicationState.UNADJUDICATED
        )

    def as_dict(self) -> dict[str, object]:
        """Return the ledger with an explicit claim and adjudication column."""

        return {
            "closure_path": str(self.closure_path) if self.closure_path is not None else None,
            "closure_digest": self.closure_digest,
            "reviewer_ran": self.reviewer_ran,
            "mode": self.mode,
            "error": self.error,
            "qualification": self.qualification,
            "rows": [entry.as_dict() for entry in self.entries],
        }

    def to_rows(self) -> tuple[dict[str, object], ...]:
        """Return canonical serialized rows with separate claim and adjudication columns."""

        return tuple(
            {
                "claim": entry.claim.as_dict(),
                "adjudication": entry.adjudication.as_dict(),
                "qualification": self.qualification,
            }
            for entry in self.entries
        )


@dataclass(frozen=True, slots=True)
class SeededDefect:
    """A defect declared by a scenario package for reviewer measurement."""

    defect_id: str
    description: str = ""

    @property
    def id(self) -> str:
        """Compatibility spelling for scenario declarations."""

        return self.defect_id

    @classmethod
    def from_value(cls, value: object) -> "SeededDefect":
        """Normalize a string or mapping declaration."""

        if isinstance(value, str) and value.strip():
            return cls(value.strip())
        if isinstance(value, Mapping):
            raw_id = value.get("id", value.get("defect_id", value.get("name")))
            if isinstance(raw_id, str) and raw_id.strip():
                description = value.get("description", value.get("claim", ""))
                return cls(raw_id.strip(), description if isinstance(description, str) else "")
        raise TypeError("seeded defects must be non-empty ids or mappings with id")


@dataclass(frozen=True, slots=True)
class Ratio:
    """An auditable numerator/denominator pair, not a one-shot rate."""

    numerator: int
    denominator: int
    qualification: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.numerator < 0 or self.denominator < 0 or self.numerator > self.denominator:
            raise ValueError("ratio requires 0 <= numerator <= denominator")

    @property
    def value(self) -> float | None:
        """Return a numeric value only for a rate-capable observation."""

        if self.qualification == _qualification_for(True):
            raise ValueError("demonstrated-once observations cannot be represented as rates")
        return self.numerator / self.denominator if self.denominator else None

    @property
    def fraction(self) -> str:
        """Return the count-preserving ratio spelling."""

        return f"{self.numerator}/{self.denominator}"

    def as_dict(self) -> dict[str, object]:
        """Serialize counts and the ratio without a percentage field."""

        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "ratio": self.fraction,
        }


@dataclass(frozen=True, slots=True)
class ReviewScore:
    """Recall and precision counts for one measured review attempt."""

    examined: bool
    qualification: str
    declaration_examined: bool
    planted_defects: tuple[str, ...]
    found_defects: tuple[str, ...]
    missed_defects: tuple[str, ...]
    true_positive_claims: int
    claims_about_nothing_planted: int
    unadjudicated_claims: int
    recall_ratio: Ratio
    precision_ratio: Ratio

    def __post_init__(self) -> None:
        if self.qualification not in QUALIFICATIONS:
            raise ValueError(f"review qualification is not in the ledger vocabulary: {self.qualification}")
        for field_name in ("recall_ratio", "precision_ratio"):
            ratio = getattr(self, field_name)
            if ratio.qualification != self.qualification:
                object.__setattr__(
                    self,
                    field_name,
                    Ratio(ratio.numerator, ratio.denominator, self.qualification),
                )

    @property
    def recall(self) -> Ratio:
        """Return recall as a count ratio, never as a percentage."""

        return self.recall_ratio

    @property
    def precision(self) -> Ratio:
        """Return precision as a count ratio, never as a percentage."""

        return self.precision_ratio

    @property
    def claim_count(self) -> int:
        """Return every claim, including claims not yet adjudicated."""

        return (
            self.true_positive_claims
            + self.claims_about_nothing_planted
            + self.unadjudicated_claims
        )

    @property
    def adjudicated_claims(self) -> int:
        """Return the denominator available for precision scoring."""

        return self.true_positive_claims + self.claims_about_nothing_planted

    def as_dict(self) -> dict[str, object]:
        """Return counts, ratios, and qualification."""

        return {
            "examined": self.examined,
            "qualification": self.qualification,
            "declaration_examined": self.declaration_examined,
            "planted_defects": list(self.planted_defects),
            "found_defects": list(self.found_defects),
            "missed_defects": list(self.missed_defects),
            "true_positive_claims": self.true_positive_claims,
            "claims_about_nothing_planted": self.claims_about_nothing_planted,
            "unadjudicated_claims": self.unadjudicated_claims,
            "claim_count": self.claim_count,
            "adjudicated_claims": self.adjudicated_claims,
            "recall": self.recall_ratio.as_dict(),
            "precision": self.precision_ratio.as_dict(),
        }


# Public vocabulary aliases used by small scenario adapters.
Claim = ReviewerClaim
ClaimLedger = ReviewLedger
AdjudicationStatus = AdjudicationState


def as_claim_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    """Extract the claim list from common recorded/reviewer envelopes."""

    if isinstance(value, Mapping):
        if "error" in value:
            raise ValueError(str(value.get("error") or "reviewer returned an error"))
        candidate = value.get("claims", value.get("findings"))
        if candidate is None:
            if "id" in value or "claim_id" in value or "claim" in value:
                candidate = (value,)
            else:
                raise TypeError("reviewer output must contain a claims list")
    else:
        candidate = value
    if not isinstance(candidate, Sequence) or isinstance(candidate, (str, bytes, bytearray)):
        raise TypeError("reviewer claims must be a sequence of objects")
    result: list[Mapping[str, object]] = []
    for index, item in enumerate(candidate):
        if not isinstance(item, Mapping):
            raise TypeError(f"review claim {index} must be an object")
        result.append(dict(item))
    return tuple(result)


__all__ = [
    "Adjudication",
    "AdjudicationStatus",
    "AdjudicationState",
    "Claim",
    "ClaimLedger",
    "ClaimLedgerEntry",
    "Ratio",
    "ReviewLedger",
    "ReviewRun",
    "ReviewScore",
    "ReviewerClaim",
    "SeededDefect",
    "as_claim_sequence",
]

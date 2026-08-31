"""Claims-list data and integrity hashing.

The invariant here is that a claims approval covers exactly one canonical
claims list.  Hashing excludes the mutable approval metadata, which prevents
the approval hash from becoming circular and lets the checker reject stale
or silently regenerated claims without writing anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


ALLOWED_DIRECTIONS = frozenset({"documented-supported", "documented-unsupported"})


class ClaimsIntegrityError(ValueError):
    """Raised when a claims file is malformed or has stale approval metadata."""


def sha256_bytes(value: bytes) -> str:
    """Return a content hash with an explicit algorithm prefix."""

    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Hash UTF-8 text without normalizing its bytes."""

    return sha256_bytes(value.encode("utf-8"))


@dataclass(frozen=True)
class Claim:
    """One quoted documentation claim and the runtime code it probes."""

    claim_id: str
    skill_file: str
    line: int
    quote: str
    content_hash: str
    expected_finding_code: str
    direction: str
    category: str = "api"
    probe_id: str = "kitchen-sink"
    build_signature: str | None = None

    def __post_init__(self) -> None:
        if not self.claim_id:
            raise ClaimsIntegrityError("claim has an empty claim_id")
        if self.line < 1:
            raise ClaimsIntegrityError(f"claim {self.claim_id} has invalid line {self.line}")
        if self.direction not in ALLOWED_DIRECTIONS:
            raise ClaimsIntegrityError(
                f"claim {self.claim_id} has unsupported direction {self.direction!r}"
            )
        if not self.expected_finding_code:
            raise ClaimsIntegrityError(f"claim {self.claim_id} has no expected_finding_code")
        if not self.probe_id:
            raise ClaimsIntegrityError(f"claim {self.claim_id} has no probe_id")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Claim":
        """Decode a claim while naming the offending field when possible."""

        required = (
            "claim_id",
            "skill_file",
            "line",
            "quote",
            "content_hash",
            "expected_finding_code",
            "direction",
        )
        missing = [key for key in required if key not in value]
        if missing:
            raise ClaimsIntegrityError(f"claim is missing field(s): {', '.join(missing)}")
        try:
            return cls(
                claim_id=str(value["claim_id"]),
                skill_file=str(value["skill_file"]),
                line=int(value["line"]),
                quote=str(value["quote"]),
                content_hash=str(value["content_hash"]),
                expected_finding_code=str(value["expected_finding_code"]),
                direction=str(value["direction"]),
                category=str(value.get("category", "api")),
                probe_id=str(value.get("probe_id", "kitchen-sink")),
                build_signature=(
                    str(value["build_signature"])
                    if value.get("build_signature") is not None
                    else None
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ClaimsIntegrityError(f"invalid claim fields in {value!r}: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation used by the claims hash."""

        result = {
            "claim_id": self.claim_id,
            "skill_file": self.skill_file,
            "line": self.line,
            "quote": self.quote,
            "content_hash": self.content_hash,
            "expected_finding_code": self.expected_finding_code,
            "direction": self.direction,
            "category": self.category,
            "probe_id": self.probe_id,
        }
        if self.build_signature is not None:
            result["build_signature"] = self.build_signature
        return result


@dataclass(frozen=True)
class Baseline:
    """The reviewed source-tree snapshot bound to a claims list."""

    skill_files: dict[str, str]
    reviewer: str
    review_date: str
    approves_claims_hash: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Baseline":
        files = value.get("skill_files", value.get("source_files", {}))
        if not isinstance(files, Mapping):
            raise ClaimsIntegrityError("baseline.skill_files must be an object")
        reviewer = value.get("reviewer", value.get("reviewed_by", ""))
        review_date = value.get("review_date", "")
        approved = value.get("approves_claims_hash", "")
        if not reviewer:
            raise ClaimsIntegrityError("baseline.reviewer is required")
        if not review_date:
            raise ClaimsIntegrityError("baseline.review_date is required")
        if not approved:
            raise ClaimsIntegrityError("baseline.approves_claims_hash is required")
        return cls(
            skill_files={str(key): str(hash_value) for key, hash_value in files.items()},
            reviewer=str(reviewer),
            review_date=str(review_date),
            approves_claims_hash=str(approved),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return baseline metadata with deterministic file ordering."""

        return {
            "skill_files": dict(sorted(self.skill_files.items())),
            "reviewer": self.reviewer,
            "review_date": self.review_date,
            "approves_claims_hash": self.approves_claims_hash,
        }


@dataclass(frozen=True)
class ClaimsDocument:
    """A claims list plus its human-approved source baseline."""

    claims: tuple[Claim, ...]
    baseline: Baseline
    approval: dict[str, Any] | None = field(default=None)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ClaimsDocument":
        raw_claims = value.get("claims")
        if not isinstance(raw_claims, Sequence) or isinstance(raw_claims, (str, bytes)):
            raise ClaimsIntegrityError("claims must be a JSON array")
        claims = tuple(Claim.from_dict(item) for item in raw_claims if isinstance(item, Mapping))
        if len(claims) != len(raw_claims):
            raise ClaimsIntegrityError("every item in claims must be an object")
        ids = [claim.claim_id for claim in claims]
        if len(ids) != len(set(ids)):
            raise ClaimsIntegrityError("claims contains duplicate claim_id values")
        baseline_value = value.get("baseline")
        if not isinstance(baseline_value, Mapping):
            raise ClaimsIntegrityError("baseline must be a JSON object")
        approval = value.get("approval")
        if not isinstance(approval, Mapping):
            raise ClaimsIntegrityError("approval block is required")
        document = cls(
            claims=claims,
            baseline=Baseline.from_dict(baseline_value),
            approval=dict(approval) if approval is not None else None,
        )
        document.verify_approval_hash()
        return document

    def verify_approval_hash(self) -> str:
        """Verify and return the hash approved by the baseline metadata."""

        actual = claims_content_hash(self.claims)
        if actual != self.baseline.approves_claims_hash:
            raise ClaimsIntegrityError(
                "claims approval is stale: "
                f"baseline.approves_claims_hash={self.baseline.approves_claims_hash}, "
                f"current claims hash={actual}"
            )
        approval = self.approval
        if not isinstance(approval, Mapping):
            raise ClaimsIntegrityError("approval block is required")
        reviewer = approval.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ClaimsIntegrityError("approval.reviewer is required")
        approved_new = approval.get("new_claims_hash")
        if approved_new != actual:
            raise ClaimsIntegrityError(
                "approval.new_claims_hash does not match the current claims list: "
                f"{approved_new} != {actual}"
            )
        return actual

    def to_dict(self) -> dict[str, Any]:
        """Return the complete on-disk representation."""

        result: dict[str, Any] = {
            "claims": [claim.to_dict() for claim in self.claims],
            "baseline": self.baseline.to_dict(),
        }
        if self.approval is not None:
            result["approval"] = self.approval
        return result


def _claim_mapping(value: Claim | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Claim):
        return value.to_dict()
    if not isinstance(value, Mapping):
        raise TypeError(f"claims list item must be Claim or mapping, got {type(value).__name__}")
    return Claim.from_dict(value).to_dict()


def claims_content_hash(claims: Sequence[Claim | Mapping[str, Any]]) -> str:
    """Hash only the canonical claims array, excluding approval metadata."""

    payload = [_claim_mapping(claim) for claim in claims]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(encoded)


def load_claims(path: Path | str, *, verify: bool = True) -> ClaimsDocument:
    """Load a claims file and optionally enforce its approval hash."""

    claims_path = Path(path)
    try:
        value = json.loads(claims_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ClaimsIntegrityError(f"cannot read claims file {claims_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ClaimsIntegrityError(f"claims file {claims_path}:{exc.lineno} is not valid JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ClaimsIntegrityError(f"claims file {claims_path} must contain a JSON object")
    document = ClaimsDocument.from_dict(value) if verify else _document_without_verification(value)
    return document


def _document_without_verification(value: Mapping[str, Any]) -> ClaimsDocument:
    """Decode a document for diagnostics without accepting stale approval."""

    raw_claims = value.get("claims", [])
    baseline_value = value.get("baseline", {})
    if not isinstance(raw_claims, Sequence) or not isinstance(baseline_value, Mapping):
        raise ClaimsIntegrityError("claims and baseline must be present before approval can be checked")
    claims = tuple(Claim.from_dict(item) for item in raw_claims if isinstance(item, Mapping))
    approval = value.get("approval")
    return ClaimsDocument(claims, Baseline.from_dict(baseline_value), dict(approval) if isinstance(approval, Mapping) else None)


def document_json(document: ClaimsDocument) -> str:
    """Serialize a claims document deterministically for an approval write."""

    if document.approval is None:
        raise ClaimsIntegrityError("cannot serialize claims without an approval block")
    return json.dumps(document.to_dict(), ensure_ascii=False, indent=2, sort_keys=False) + "\n"

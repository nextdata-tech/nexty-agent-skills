"""Read-only documentation/runtime drift canary primitives.

The checking surface never changes claims; explicit human re-baselining is
implemented in :mod:`dp_scenarios.canary.rebaseline`.
"""

from .claims import Claim, ClaimsDocument, claims_content_hash, load_claims
from .extract import ClaimDriftError, ExtractionResult, extract_claims
from .verdict import Verdict, aggregate_verdict

__all__ = [
    "Claim",
    "ClaimDriftError",
    "ClaimsDocument",
    "ExtractionResult",
    "Verdict",
    "aggregate_verdict",
    "claims_content_hash",
    "extract_claims",
    "load_claims",
]

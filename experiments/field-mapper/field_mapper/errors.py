"""Exception taxonomy. `value_status` is a projection of this module.

CONTRACT.md §1 splits this out for one reason: §4's blocking table is only
enforceable if the mapping from raised exception to `value_status` lives in ONE
place. If `transport.py` decides some statuses and `validate.py` decides others,
the "systemic failure blocks, row-level absence does not" boundary erodes at the
first new error type.

The boundary, restated as code:

- `CellError`     -> a row-level fact. Lands as a non-`ok` cell. Does not block.
- `SystemicError` -> the run cannot produce trustworthy output. BLOCKS the build.

Pure stdlib. This module must never import `transport` or `anthropic`.
"""

from __future__ import annotations

__all__ = [
    "FieldMapperError",
    "CellError",
    "ValidationExhausted",
    "EvidenceAbsent",
    "TransportExhausted",
    "Refusal",
    "SchemaReject",
    "SystemicError",
    "CredentialMissing",
    "DependencyMissing",
    "SchemaRejectedByApi",
    "GrantError",
    "BudgetExceeded",
    "CoverageBlocked",
    "SpecError",
    "ModelNotFound",
    "RunCancelled",
    # `*Error`-suffixed aliases of the same classes (see bottom of module).
    "CredentialMissingError",
    "DependencyMissingError",
    "SchemaRejectedError",
    "TransportExhaustedError",
    "BudgetExceededError",
    "ModelNotFoundError",
    "RunCancelledError",
    "RefusalError",
    "ValidationExhaustedError",
    "EvidenceAbsentError",
    "ERROR_CODES",
]


class FieldMapperError(Exception):
    """Root of the taxonomy, so callers catch by class and never by string."""

    #: Stable machine token landed in `mapper_proposals.error_code`.
    #: Never free text; never interpolated with row content.
    error_code: str | None = None


# --------------------------------------------------------------------------
# Row-level: lands as a non-`ok` cell, does not block the build on its own.
# --------------------------------------------------------------------------


class CellError(FieldMapperError):
    """A fact about ONE cell. The run continues; the threshold gate decides."""


class ValidationExhausted(CellError):
    """Value returned, but failed harness checks after the retry budget.

    Maps to `value_status = validation_failed`. NOT `evidence_absent` — the task
    brief calls this out explicitly, and they are different conditions: the model
    answered and was wrong, versus the source is silent.
    """

    error_code = None  # `error_code` is non-null IFF value_status == "error".


class EvidenceAbsent(CellError):
    """The model was asked, responded within contract, and reported silence.

    Maps to `value_status = evidence_absent`. Not an error, not a failure — the
    honest reading of a silent source (CONTRACT.md §3).
    """

    error_code = None


class TransportExhausted(CellError):
    """429/500/529/connection errors survived backoff. Row-level until the rate
    ceiling is crossed, at which point §4 promotes it to a systemic block."""

    error_code = "transport_exhausted"


class Refusal(CellError):
    """`stop_reason == "refusal"` — HTTP 200 with empty or partial content."""

    error_code = "refusal"


class SchemaReject(CellError):
    """Content unparseable despite structured output, or `stop_reason ==
    "max_tokens"` truncating mid-object. Never salvaged as a partial answer."""

    error_code = "schema_reject"


# --------------------------------------------------------------------------
# Systemic: BLOCKS. A blocked build lands nothing (CONTRACT.md §4).
# --------------------------------------------------------------------------


class SystemicError(FieldMapperError):
    """Not about any row's content. Landing partial output would be the lie."""


class CredentialMissing(SystemicError):
    """One missing credential means every cell is unattempted; landing 0%
    coverage as data is the failure this rule exists to prevent."""

    error_code = "credential_missing"


class DependencyMissing(SystemicError):
    """`anthropic` absent, extractor absent, landed-text model absent.

    This is the error `transport.py` raises on `ModuleNotFoundError` — failing
    gracefully and clearly on the un-installed SDK is correct behavior, not a
    bug to work around.
    """

    error_code = "dependency_missing"


class SchemaRejectedByApi(SystemicError):
    """The compiled wire schema was rejected. It will reject every cell."""

    error_code = "schema_reject"


class GrantError(SystemicError):
    """Grant missing or mismatched. Raised BEFORE any source read (design §9)."""

    error_code = "grant_missing"


class BudgetExceeded(SystemicError):
    """Preflight over the grant ceiling, or remaining budget cannot meet
    required coverage. Fails deterministically, not when the money runs out."""

    error_code = "budget_exceeded"


class CoverageBlocked(SystemicError):
    """A §4 threshold was crossed. Carries the gate report for narration."""

    error_code = "coverage_blocked"

    def __init__(self, message: str, report: object | None = None) -> None:
        super().__init__(message)
        self.report = report


class SpecError(SystemicError):
    """The spec is unusable — no stable row identity, unknown field, bad
    constraint. A spec that cannot define stable row identity is rejected
    (design §3)."""

    error_code = "spec_invalid"


class ModelNotFound(SystemicError):
    """The configured model id was rejected by the API (404).

    Systemic, and deliberately NOT retried: a 404 on the model means the spec
    names a model this key cannot reach, which no amount of backoff fixes.
    """

    error_code = "model_not_found"


class RunCancelled(SystemicError):
    """Deadline hit, or the run was cancelled.

    Undispatched cells land `skipped`, which blocks — a cancelled run must not
    be landable as a complete one (CONTRACT.md §8).
    """

    error_code = "cancelled"


# --------------------------------------------------------------------------
# `*Error`-suffixed aliases.
#
# Two spellings exist because the taxonomy is read in two registers: the
# `CellError`/`SystemicError` split reads best as a *classification* (which is
# why the base names are unsuffixed), while call sites that `raise` read better
# with the conventional `...Error` suffix. These are the SAME classes, not
# parallel hierarchies — aliasing rather than subclassing is what keeps
# `except CredentialMissing` and `except CredentialMissingError` catching the
# same thing, so a caller can never accidentally handle only half a case.
# --------------------------------------------------------------------------

CredentialMissingError = CredentialMissing
DependencyMissingError = DependencyMissing
SchemaRejectedError = SchemaRejectedByApi
TransportExhaustedError = TransportExhausted
BudgetExceededError = BudgetExceeded
ModelNotFoundError = ModelNotFound
RunCancelledError = RunCancelled
RefusalError = Refusal
ValidationExhaustedError = ValidationExhausted
EvidenceAbsentError = EvidenceAbsent


#: Every stable machine token that may land in `error_code`. A token outside
#: this set is a schema violation. Kept as a frozenset so a test can assert the
#: landed column never carries free text.
ERROR_CODES = frozenset(
    {
        "transport_exhausted",
        "refusal",
        "schema_reject",
        "credential_missing",
        "dependency_missing",
        "grant_missing",
        "budget_exceeded",
        "coverage_blocked",
        "spec_invalid",
        "model_not_found",
        "cancelled",
    }
)

"""Append-only evidence ledgers for scenario runs.

The package keeps the run manifest, evidence rows, storage rules, and lint
rules together so a caller cannot accidentally treat narrated text as
evidence.  Row zero identifies the run configuration; every later row is an
immutable observation, and corrections are additional supersession rows.
"""

from .lint import (
    CLAIM_WITHOUT_EVIDENCE,
    Finding,
    INCOMPLETE_SUPERVISOR_FACTS,
    INVALID_EVENT_ID,
    INVALID_MATCHED_RULE_ID,
    INVALID_MANIFEST,
    INVALID_QUALIFICATION,
    INVALID_SUPERSESSION,
    LEDGER_EMPTY,
    LintReport,
    PHASE_NOT_APPLICABLE_WITHOUT_REASON,
    PHASE_UNACCOUNTED,
    ROW_MANIFEST_MISMATCH,
    SENTINEL_NOT_PERMITTED_FOR_TIER,
    SUPERVISOR_FACT_ABSENT,
    SUPERVISOR_FACT_MISMATCH,
    SUPERVISOR_FACT_NOT_STRING,
    SupervisorFacts,
    TURN_DECREASED,
    UnhandledSituationError,
    lint,
    supersession_diff,
)
from .manifest import (
    Comparability,
    ComparabilityResult,
    Manifest,
    ManifestError,
    NOT_APPLICABLE,
    fixture_dir_hash,
)
from .schema import (
    ACTION_KINDS,
    LEDGER_FIELDS,
    PHASE_STATUSES,
    QUALIFICATIONS,
    LedgerRow,
)
from .store import (
    LedgerError,
    LedgerFormatError,
    LedgerLockError,
    LedgerStore,
    LedgerTamperError,
    read_ledger,
)

__all__ = [
    "ACTION_KINDS",
    "CLAIM_WITHOUT_EVIDENCE",
    "Comparability",
    "ComparabilityResult",
    "Finding",
    "INCOMPLETE_SUPERVISOR_FACTS",
    "INVALID_EVENT_ID",
    "INVALID_MATCHED_RULE_ID",
    "INVALID_MANIFEST",
    "INVALID_QUALIFICATION",
    "INVALID_SUPERSESSION",
    "LEDGER_FIELDS",
    "LedgerError",
    "LedgerFormatError",
    "LedgerLockError",
    "LedgerRow",
    "LedgerStore",
    "LedgerTamperError",
    "LEDGER_EMPTY",
    "LintReport",
    "Manifest",
    "ManifestError",
    "NOT_APPLICABLE",
    "PHASE_STATUSES",
    "PHASE_NOT_APPLICABLE_WITHOUT_REASON",
    "PHASE_UNACCOUNTED",
    "QUALIFICATIONS",
    "ROW_MANIFEST_MISMATCH",
    "SENTINEL_NOT_PERMITTED_FOR_TIER",
    "SUPERVISOR_FACT_ABSENT",
    "SUPERVISOR_FACT_MISMATCH",
    "SUPERVISOR_FACT_NOT_STRING",
    "SupervisorFacts",
    "TURN_DECREASED",
    "UnhandledSituationError",
    "fixture_dir_hash",
    "lint",
    "read_ledger",
    "supersession_diff",
]

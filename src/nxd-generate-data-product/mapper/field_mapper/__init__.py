"""Field mapper — Layer-1 harness.

CONTRACT.md §1 defines the full public surface, and this module is now the
whole of it.

Two names are deliberately ABSENT. `transport.Client` is private: Layer 2 must
not be able to make an unbudgeted, unledgered call. `PreflightEstimate` and
`estimate` live in `transport` and are imported from there by a caller that has
already decided to spend money — importing them here would pull the SDK guard
into every `import field_mapper`, and `--dry-run` has to work on a machine with
no `anthropic` installed.

`__version__` is load-bearing, not decoration: CONTRACT.md open question 6
requires the harness version to appear in the ledger AND in `mapper_spec_id`'s
inputs — otherwise a harness change (a tightened bijection assert, a changed
normalizer) is invisible when comparing two Layer-2 experiments.
"""

from __future__ import annotations

__version__ = "0.1.0"

from . import (
    errors,
    grant,
    identity,
    ledger,
    mapper,
    records,
    resolver,
    schema,
    spec,
    validate,
)
from .errors import (
    CellError,
    CoverageBlocked,
    FieldMapperError,
    GrantError,
    SpecError,
    SystemicError,
)
from .grant import Grant
from .identity import new_execution_id
from .mapper import (
    MapperInput,
    MapResult,
    Quarantine,
    map_inputs,
)
from .records import (
    EffectiveSource,
    LocatorKind,
    MapperEvidence,
    MapperProposal,
    MapperReview,
    StaleReason,
    TypedValue,
    ValueType,
    Verdict,
)
from .ledger import (
    AttemptRecord,
    LedgerCorruptionError,
    RunLedger,
    SecretLeakError,
    read_attempts,
    replay_validation,
)
from .resolver import (
    BijectionError,
    EffectiveValue,
    Resolution,
    ResolverInputError,
    StaleReview,
    resolve,
)
from .spec import (
    Cardinality,
    GrainDeclaration,
    MapperSpec,
    TargetField,
    Thresholds,
)
from .validate import (
    CoverageReport,
    FieldConstraint,
    ValidatedCell,
    ValueStatus,
    VerifyStatus,
    Violation,
    evaluate_coverage,
    normalize_text,
    run_with_retry,
    validate_value,
    verify_quote,
)

__all__ = [
    "__version__",
    "errors",
    "grant",
    "identity",
    "ledger",
    "mapper",
    "records",
    "resolver",
    "schema",
    "spec",
    "validate",
    "FieldMapperError",
    "CellError",
    "SystemicError",
    "SpecError",
    "GrantError",
    "CoverageBlocked",
    # -- mapper (CONTRACT.md §1: the N->M primitive) -------------------------
    # `map_inputs` returns proposals + evidence in ONE bundle. There is no API
    # that returns proposals without their evidence — that API is how the
    # orphan-evidence bug gets written.
    "map_inputs",
    "MapperInput",
    "MapResult",
    "Quarantine",
    # -- grant (CONTRACT.md §9: checked BEFORE any source read) --------------
    "Grant",
    "new_execution_id",
    # -- spec (CONTRACT.md §1: `MapperSpec.load` / `.mapper_spec_id`) --------
    "MapperSpec",
    "TargetField",
    "GrainDeclaration",
    "Cardinality",
    "Thresholds",
    # -- records (CONTRACT.md §1: the three record types + ValueStatus) ------
    "MapperProposal",
    "MapperReview",
    "MapperEvidence",
    "TypedValue",
    "ValueType",
    "Verdict",
    "LocatorKind",
    "EffectiveSource",
    "StaleReason",
    # -- resolver (CONTRACT.md §1: `resolve`, `Resolution.*`, §7) ------------
    "resolve",
    "Resolution",
    "EffectiveValue",
    "StaleReview",
    "BijectionError",
    "ResolverInputError",
    # -- ledger (CONTRACT.md §9: hashes only; parser/validator replay only) --
    "RunLedger",
    "AttemptRecord",
    "SecretLeakError",
    "LedgerCorruptionError",
    "read_attempts",
    "replay_validation",
    "ValueStatus",
    "VerifyStatus",
    "Violation",
    "FieldConstraint",
    "ValidatedCell",
    "CoverageReport",
    "normalize_text",
    "validate_value",
    "verify_quote",
    "run_with_retry",
    "evaluate_coverage",
]

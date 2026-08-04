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

from . import errors
from . import grant
from . import identity
from . import ledger
from . import mapper
from . import records
from . import resolver
from . import schema
from . import spec
from . import validate
from .errors import CellError
from .errors import CoverageBlocked
from .errors import FieldMapperError
from .errors import GrantError
from .errors import SpecError
from .errors import SystemicError
from .grant import Grant
from .identity import new_execution_id
from .ledger import AttemptRecord
from .ledger import LedgerCorruptionError
from .ledger import RunLedger
from .ledger import SecretLeakError
from .ledger import read_attempts
from .ledger import replay_validation
from .mapper import MapperInput
from .mapper import MapResult
from .mapper import Quarantine
from .mapper import map_inputs
from .records import EffectiveSource
from .records import LocatorKind
from .records import MapperEvidence
from .records import MapperProposal
from .records import MapperReview
from .records import StaleReason
from .records import TypedValue
from .records import ValueType
from .records import Verdict
from .resolver import BijectionError
from .resolver import EffectiveValue
from .resolver import Resolution
from .resolver import ResolverInputError
from .resolver import StaleReview
from .resolver import resolve
from .spec import Cardinality
from .spec import GrainDeclaration
from .spec import MapperSpec
from .spec import TargetField
from .spec import Thresholds
from .validate import CoverageReport
from .validate import FieldConstraint
from .validate import ValidatedCell
from .validate import ValueStatus
from .validate import VerifyStatus
from .validate import Violation
from .validate import evaluate_coverage
from .validate import normalize_text
from .validate import run_with_retry
from .validate import validate_value
from .validate import verify_quote

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

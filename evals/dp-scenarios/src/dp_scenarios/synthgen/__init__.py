"""Deterministic scenario fixtures and independent gold references.

The package enforces reproducibility by requiring an explicit seed for every
dataset and by keeping source generation, defect injection, and gold
calculation as separate layers.  Generated fixtures are disposable; the
manifest and gold files make each generated run auditable.
"""

from .datasets import DATASET_DEFINITIONS, DatasetDefinition, get_dataset
from .generator import (
    GenerationResult,
    PiiScanStatus,
    VerificationError,
    find_nondeterministic_sources,
    generate,
    generate_dataset,
    mutate_dataset,
    pii_promise_holds,
    verify_dataset,
)

__all__ = [
    "DATASET_DEFINITIONS",
    "DatasetDefinition",
    "GenerationResult",
    "PiiScanStatus",
    "VerificationError",
    "find_nondeterministic_sources",
    "generate",
    "generate_dataset",
    "get_dataset",
    "mutate_dataset",
    "pii_promise_holds",
    "verify_dataset",
]

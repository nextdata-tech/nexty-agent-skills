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
from .reference import register_reference_builder
from .registry import RegistryError, dataset_definitions, register_dataset, registered_dataset_names

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
    "dataset_definitions",
    "register_dataset",
    "register_reference_builder",
    "registered_dataset_names",
    "RegistryError",
    "mutate_dataset",
    "pii_promise_holds",
    "verify_dataset",
]

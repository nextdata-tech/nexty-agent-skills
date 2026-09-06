"""Tests for additive dataset and independent-gold provider registration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dp_scenarios.synthgen.datasets import DATASET_DEFINITIONS, get_dataset
from dp_scenarios.synthgen.reference import (
    ReferenceGold,
    _REFERENCE_BUILDERS,
    register_reference_builder,
)
from dp_scenarios.synthgen.registry import (
    RegistryError,
    get_registered_dataset,
    register_dataset,
)
from dp_scenarios.synthgen import registry


def test_builtin_dataset_registry_exposes_provider_owned_plants() -> None:
    assert DATASET_DEFINITIONS["grain_trap"].plant == "grain_trap_fanout"
    assert DATASET_DEFINITIONS["zero_row_optional"].plant == "optional_zero_row"
    assert DATASET_DEFINITIONS["zero_row_optional"].requires_explicit_plant is True


def test_additive_dataset_registration_rejects_duplicate_names() -> None:
    definition = SimpleNamespace(name="registry-test-dataset", plant="registry-test-plant")
    try:
        assert register_dataset(definition) is definition
        with pytest.raises(RegistryError, match="already registered"):
            register_dataset(definition)
    finally:
        registry._DATASETS.pop(definition.name, None)


def test_unknown_dataset_is_fail_closed() -> None:
    with pytest.raises(RegistryError, match="unknown dataset"):
        get_registered_dataset("does-not-exist")
    with pytest.raises(ValueError, match="unknown dataset"):
        get_dataset("does-not-exist")


def test_reference_builder_registration_rejects_duplicate_names() -> None:
    def builder(_data_dir: object) -> ReferenceGold:
        return ReferenceGold(files={})

    try:
        assert register_reference_builder("registry-test-gold", builder) is builder
        with pytest.raises(ValueError, match="already registered"):
            register_reference_builder("registry-test-gold", builder)
    finally:
        _REFERENCE_BUILDERS.pop("registry-test-gold", None)

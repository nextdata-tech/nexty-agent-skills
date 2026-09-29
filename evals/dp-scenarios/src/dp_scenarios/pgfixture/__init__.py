"""Least-privilege Postgres fixture for the credential-rotation scenario."""

from .fixture import (
    ConnectionInfo,
    FIXTURE_UNAVAILABLE_MARKER,
    FixtureSafetyError,
    FixtureTeardownError,
    FixtureUnavailable,
    PgFixture,
    PostgresFixture,
    RotationError,
    RotationRecord,
    SKIP_UNAVAILABLE_MARKER,
    skip_unavailable,
)
from .seed import (
    DATASET,
    DATASET_GRAIN_TRAP,
    DATASET_INVENTORY_ROTATION,
    SUPPORTED_DATASETS,
    SeededData,
    seed_inventory,
)

__all__ = [
    "ConnectionInfo",
    "DATASET",
    "DATASET_GRAIN_TRAP",
    "DATASET_INVENTORY_ROTATION",
    "FIXTURE_UNAVAILABLE_MARKER",
    "FixtureSafetyError",
    "FixtureTeardownError",
    "FixtureUnavailable",
    "PgFixture",
    "PostgresFixture",
    "RotationError",
    "RotationRecord",
    "SKIP_UNAVAILABLE_MARKER",
    "SUPPORTED_DATASETS",
    "SeededData",
    "seed_inventory",
    "skip_unavailable",
]

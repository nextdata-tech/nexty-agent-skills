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
from .seed import SeededData, seed_inventory

__all__ = [
    "ConnectionInfo",
    "FIXTURE_UNAVAILABLE_MARKER",
    "FixtureSafetyError",
    "FixtureTeardownError",
    "FixtureUnavailable",
    "PgFixture",
    "PostgresFixture",
    "RotationError",
    "RotationRecord",
    "SKIP_UNAVAILABLE_MARKER",
    "SeededData",
    "seed_inventory",
    "skip_unavailable",
]

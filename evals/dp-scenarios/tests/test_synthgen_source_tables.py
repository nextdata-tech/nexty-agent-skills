"""Runner-private deterministic JSON source tables for fixture generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random

import pytest

from dp_scenarios.synthgen.datasets import BASE_INSTANT, DatasetDefinition
from dp_scenarios.synthgen.generator import (
    VerificationError,
    generate_dataset,
    verify_dataset,
)
from dp_scenarios.synthgen.reference import (
    ReferenceGold,
    _REFERENCE_BUILDERS,
    reference_gold,
    read_source_table,
)
from dp_scenarios.synthgen.registry import _DATASETS


DATASET_NAME = "p3a-source-table-fixture"
SOURCE_MARKER = "P3A_ONLY_SOURCE_ROW_MARKER_8f19c2"


def _builder(seed: int, _rng: random.Random) -> dict[str, list[dict[str, object]]]:
    return {
        "summary": [{"day": "2024-01-01", "event_count": 5 + seed % 3}],
        "events_v1": [
            {
                "id": f"v1-{seed}-{index}",
                "detail": {"labels": ["signup", index], "context": {"seed": seed}},
                "note": SOURCE_MARKER,
            }
            for index in range(5)
        ],
        "events_v2": [
            {
                "id": f"v2-{seed}-{index}",
                "detail": {"labels": ["usage", index], "context": {"seed": seed}},
                "note": SOURCE_MARKER,
            }
            for index in range(4)
        ],
    }


def _reference_builder(data_dir: Path, *, source_dir: Path) -> ReferenceGold:
    del data_dir
    rows = read_source_table(source_dir, "events_v1")
    return ReferenceGold(
        files={
            "source_reference.json": [
                {"first_event": rows[0]["id"], "nested_seed": rows[0]["detail"]["context"]["seed"]}
            ]
        }
    )


@pytest.fixture
def source_dataset(monkeypatch: pytest.MonkeyPatch) -> DatasetDefinition:
    definition = DatasetDefinition(
        name=DATASET_NAME,
        base_instant=BASE_INSTANT,
        table_columns={"summary": ("day", "event_count")},
        injectors=(),
        builder=_builder,
        description="Test-only dataset with runner-hidden generated sources.",
        plant="p3a_source_fixture",
        source_tables=("events_v1", "events_v2"),
    )
    monkeypatch.setitem(_DATASETS, DATASET_NAME, definition)
    monkeypatch.setitem(_REFERENCE_BUILDERS, DATASET_NAME, _reference_builder)
    return definition


def _snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_source_tables_are_canonical_hashed_and_verified(
    tmp_path: Path, source_dataset: DatasetDefinition
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generated = generate_dataset(source_dataset.name, 13, first)
    generate_dataset(source_dataset.name, 13, second)

    assert _snapshot(first) == _snapshot(second)
    assert not (first / "data/events_v1.csv").exists()
    assert not (first / "data/events_v2.csv").exists()
    source_rows = _builder(13, random.Random(13))["events_v1"]
    expected = (
        json.dumps(source_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    source_path = first / "source/events_v1.json"
    assert source_path.read_bytes() == expected

    manifest = json.loads(generated.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_tables"] == {
        name: {
            "path": f"source/{name}.json",
            "row_count": len(_builder(13, random.Random(13))[name]),
            "sha256": hashlib.sha256((first / f"source/{name}.json").read_bytes()).hexdigest(),
        }
        for name in ("events_v1", "events_v2")
    }
    assert manifest["table_row_counts"] == {"summary": 1}
    assert set(manifest["table_row_counts"]).isdisjoint(manifest["source_tables"])
    assert verify_dataset(first)

    source_path.write_bytes(source_path.read_bytes().replace(b"v1-13-0", b"v1-13-X"))
    with pytest.raises(VerificationError, match="source differs"):
        verify_dataset(first)


def test_reference_builder_reads_source_dir_and_legacy_builders_still_work(
    tmp_path: Path, source_dataset: DatasetDefinition
) -> None:
    output = tmp_path / "fixture"
    generated = generate_dataset(source_dataset.name, 7, output)
    reference = json.loads((generated.gold_dir / "source_reference.json").read_text(encoding="utf-8"))
    assert reference == [{"first_event": "v1-7-0", "nested_seed": 7}]
    default_reference = reference_gold(source_dataset.name, generated.data_dir)
    assert default_reference.files["source_reference.json"] == reference

    # Existing public reference builders continue to receive only data_dir.
    legacy = generate_dataset("grain_trap", 29, tmp_path / "legacy")
    assert (legacy.gold_dir / "grain_trap_by_region.json").is_file()


def test_source_table_names_are_unique_safe_and_disjoint() -> None:
    with pytest.raises(ValueError, match="unique"):
        DatasetDefinition(
            "bad-duplicates", BASE_INSTANT, {}, (), _builder, "bad", source_tables=("x", "x")
        )
    with pytest.raises(ValueError, match="safe file stem"):
        DatasetDefinition(
            "bad-path", BASE_INSTANT, {}, (), _builder, "bad", source_tables=("../escape",)
        )
    with pytest.raises(ValueError, match="disjoint"):
        DatasetDefinition(
            "bad-overlap",
            BASE_INSTANT,
            {"events": ("id",)},
            (),
            _builder,
            "bad",
            source_tables=("events",),
        )


def test_declared_source_table_missing_from_builder_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_dataset: DatasetDefinition
) -> None:
    from dp_scenarios.synthgen import generator as generator_module

    built = _builder(13, random.Random(13))
    monkeypatch.setattr(
        generator_module,
        "build_tables",
        lambda _name, _seed, _rng: {name: rows for name, rows in built.items() if name != "events_v2"},
    )
    with pytest.raises(ValueError, match="omitted source table 'events_v2'"):
        generate_dataset(source_dataset.name, 13, tmp_path / "missing")

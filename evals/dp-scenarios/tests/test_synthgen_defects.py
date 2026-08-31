"""Focused tests for declarative seeded defect injectors."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import csv
import json
from pathlib import Path
import random
import unicodedata

import pytest

from dp_scenarios.synthgen.defects import (
    _orphan_key,
    duplicate_rows,
    negative_values,
    orphan_foreign_keys,
    out_of_order_events,
    pii_sentinels,
    tombstones,
)
from dp_scenarios.synthgen import generator as generator_module
from dp_scenarios.synthgen.generator import generate_dataset, pii_promise_holds


def test_duplicate_rows_has_exact_and_ignorable_near_duplicates() -> None:
    frame = [
        {"id": index, "value": index + 1, "ignorable_note": "original"}
        for index in range(4)
    ]
    output, record = duplicate_rows(0.75)(frame, random.Random(8))
    assert len(output) == 7
    assert record.changed_rows == 3
    assert all("near-duplicate" not in str(row) for row in output)
    assert {detail["kind"] for detail in record.details} == {"exact", "near"}
    for detail in record.details:
        source = output[detail["source_index"]]
        duplicate = output[detail["appended_index"]]
        if detail["kind"] == "exact":
            assert duplicate == source
        else:
            differing = {
                key
                for key in set(source) | set(duplicate)
                if source.get(key) != duplicate.get(key)
            }
            assert differing == {"ignorable_note"}


def test_duplicate_rows_fails_closed_without_a_schema_column() -> None:
    with pytest.raises(ValueError, match="existing ignorable column"):
        duplicate_rows(0.5)([{"id": index} for index in range(4)], random.Random(8))


def test_orphans_survive_normalization_and_numeric_coercion_attempts() -> None:
    frame = [{"id": 1, "order_id": "ORD-1"}, {"id": 2, "order_id": "Ord-2"}]
    parent_keys = {"ord-1", "ord-2"}
    output, record = orphan_foreign_keys(
        2,
        parent_keys={"ORD-1", "Ord-2"},
        seed=29,
        dataset="grain_trap",
    )(frame, random.Random(3))
    assert record.changed_rows == 2
    for row in output:
        value = row["order_id"]
        assert isinstance(value, str)
        for form in ("NFKC", "NFKD"):
            normalized = unicodedata.normalize(form, value)
            normalized = normalized.replace("\u200b", "").strip().casefold()
            assert normalized not in parent_keys
        with pytest.raises((TypeError, ValueError)):
            int(value)
        with pytest.raises((TypeError, ValueError)):
            float(value)


def test_orphan_generation_uses_parent_keys_not_child_key_range() -> None:
    child = [{"order_id": 1}]
    colliding_parent_key = _orphan_key(
        child,
        "order_id",
        1,
        seed=29,
        dataset="grain_trap",
        ordinal=0,
        row_index=0,
    )
    output, _ = orphan_foreign_keys(
        1,
        parent_keys={colliding_parent_key},
        seed=29,
        dataset="grain_trap",
    )(child, random.Random(3))
    assert output[0]["order_id"] != colliding_parent_key


def test_tombstones_negative_values_pii_and_event_ordering() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    frame = [
        {
            "id": index,
            "sequence": index,
            "status": "active",
            "amount": Decimal("10.00") + index,
            "event_timestamp": (base + timedelta(days=index)).isoformat(),
            "customer_email": f"customer-{index}@example.invalid",
        }
        for index in range(5)
    ]
    tombstoned, tombstone_record = tombstones(0.4)(frame, random.Random(1))
    assert tombstone_record.changed_rows == 2
    assert sum(row["status"] == "deleted" for row in tombstoned) == 2

    negative, negative_record = negative_values("amount", 2)(tombstoned, random.Random(2))
    assert negative_record.changed_rows == 2
    assert sum(row["amount"] < 0 for row in negative) == 2

    out_of_order, order_record = out_of_order_events(1.0)(negative, random.Random(3))
    assert order_record.changed_rows == 5
    timestamps = [row["event_timestamp"] for row in out_of_order]
    assert timestamps != sorted(timestamps)
    assert [row["sequence"] for row in out_of_order] == list(range(5))

    planted, pii_record = pii_sentinels(
        ["customer_email"], seed=4, dataset="zero_row_optional"
    )(out_of_order, random.Random(4))
    marker = pii_record.markers["customer_email"]
    assert planted[0]["customer_email"] == marker
    assert len(marker) > 32
    digest = marker.split("sentinel-", 1)[1].split("@", 1)[0]
    assert len(set(digest)) >= 12


def test_pii_dictionary_and_mutation_oracle_distinguish_clean_and_leaked_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = tmp_path / "clean"
    mutated = tmp_path / "mutated"

    captured_parent_keys = None
    original_make_injector = generator_module.make_injector

    def record_parent_keys(name, parameters, **kwargs):
        nonlocal captured_parent_keys
        if name == "orphan_foreign_keys":
            captured_parent_keys = parameters.get("parent_keys")
        return original_make_injector(name, parameters, **kwargs)

    monkeypatch.setattr(generator_module, "make_injector", record_parent_keys)
    generate_dataset("grain_trap", 29, clean)
    generate_dataset("grain_trap", 29, mutated, mutation=True)

    clean_manifest = json.loads(
        (clean / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    mutated_manifest = json.loads(
        (mutated / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    assert clean_manifest["pii_dictionary"]["classified_columns"]
    assert clean_manifest["pii_dictionary"]["scan_patterns"]
    assert clean_manifest["mutation"]["enabled"] is False
    assert mutated_manifest["mutation"]["enabled"] is True
    clean_landed = tmp_path / "real-clean-landed"
    clean_landed.mkdir()
    (clean_landed / "orders.csv").write_text("order_id\nORD-1\n", encoding="utf-8")
    assert pii_promise_holds(clean, clean_landed) == "held"
    assert pii_promise_holds(mutated, mutated / "data" / "landed") == "leaked"
    assert pii_promise_holds(clean, tmp_path / "missing-landed") == "not-examined"
    empty_landed = tmp_path / "empty-landed"
    empty_landed.mkdir()
    assert pii_promise_holds(clean, empty_landed) == "not-examined"
    assert (mutated / "data/landed/pii-leak.csv").is_file()

    with (clean / "data/orders.csv").open(encoding="utf-8", newline="") as handle:
        order_ids = {row["order_id"] for row in csv.DictReader(handle)}
    assert captured_parent_keys == order_ids
    orphan_values = {
        detail["after"]
        for item in clean_manifest["applied_injectors"]
        if item["name"] == "orphan_foreign_keys"
        for detail in item["changed"]["details"]
    }
    assert orphan_values.isdisjoint(order_ids)

    clean_files = {
        path.relative_to(clean).as_posix(): path.read_bytes()
        for path in clean.rglob("*")
        if path.is_file()
    }
    for marker in clean_manifest["pii_markers"].values():
        locations = {
            path for path, content in clean_files.items() if marker.encode() in content
        }
        assert locations <= {"data/line_items.csv", "fixture-manifest.json"}

    blank_manifest = dict(clean_manifest)
    blank_manifest["pii_dictionary"] = dict(clean_manifest["pii_dictionary"])
    blank_manifest["pii_dictionary"]["sentinel_values"] = {}
    (clean / "fixture-manifest.json").write_text(
        json.dumps(blank_manifest), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="no PII sentinel values"):
        pii_promise_holds(clean, clean_landed)

    clean_zero = tmp_path / "clean-zero"
    generate_dataset("zero_row_optional", 29, clean_zero)
    zero_manifest = json.loads(
        (clean_zero / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    assert set(clean_manifest["pii_markers"].values()).isdisjoint(
        zero_manifest["pii_markers"].values()
    )
    _, grain_marker_record = pii_sentinels(
        ["customer_email"], seed=29, dataset="grain_trap"
    )([{"customer_email": "before"}], random.Random(0))
    _, zero_marker_record = pii_sentinels(
        ["customer_email"], seed=29, dataset="zero_row_optional"
    )([{"customer_email": "before"}], random.Random(0))
    assert (
        grain_marker_record.markers["customer_email"]
        != zero_marker_record.markers["customer_email"]
    )


def test_injectors_do_not_touch_module_random_state() -> None:
    random.seed(101)
    before = random.getstate()
    duplicate_rows(0.5)(
        [{"id": index, "ignorable_note": "x"} for index in range(4)], random.Random(9)
    )
    assert random.getstate() == before

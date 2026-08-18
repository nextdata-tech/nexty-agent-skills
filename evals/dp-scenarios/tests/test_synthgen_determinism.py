"""Determinism and emitted-layout tests for the seeded fixture generator."""

from __future__ import annotations

import ast
import csv
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess

import yaml

from dp_scenarios.synthgen.generator import (
    _NondeterminismVisitor,
    find_nondeterministic_sources,
    generate_dataset,
)
from dp_scenarios.synthgen.datasets import BASE_INSTANT


PACKAGE_DIR = Path(__file__).parents[1] / "src" / "dp_scenarios" / "synthgen"


def _snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _manifest(path: Path) -> dict:
    return json.loads((path / "fixture-manifest.json").read_text(encoding="utf-8"))


def _injector_indices(manifest: dict, name: str, table: str) -> set[int]:
    return {
        detail["row_index"]
        for item in manifest["applied_injectors"]
        if item["name"] == name and item["target_table"] == table
        for detail in item["changed"]["details"]
    }


def test_same_seed_is_byte_identical_and_in_place_regeneration_is_safe(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_dataset("grain_trap", 17, first)
    generate_dataset("grain_trap", 17, second)
    assert _snapshot(first) == _snapshot(second)

    unrelated = first / "README-local.txt"
    unrelated.write_text("caller-owned\n", encoding="utf-8")
    before = _manifest(first)
    generate_dataset("grain_trap", 17, first)
    after = _manifest(first)
    assert _snapshot(first)["README-local.txt"] == b"caller-owned\n"
    assert before["file_hashes"] == after["file_hashes"]
    assert before["fixture_hash"] == after["fixture_hash"]


def test_seed_wires_rng_into_value_columns_and_injector_row_sets(tmp_path: Path) -> None:
    first = tmp_path / "seed-17"
    second = tmp_path / "seed-18"
    generate_dataset("grain_trap", 17, first)
    generate_dataset("grain_trap", 18, second)

    with (first / "data/line_items.csv").open(encoding="utf-8", newline="") as handle:
        first_items = list(csv.DictReader(handle))
    with (second / "data/line_items.csv").open(encoding="utf-8", newline="") as handle:
        second_items = list(csv.DictReader(handle))
    assert [row["quantity"] for row in first_items] != [row["quantity"] for row in second_items]

    first_manifest = _manifest(first)
    second_manifest = _manifest(second)
    assert _injector_indices(first_manifest, "orphan_foreign_keys", "line_items") != _injector_indices(
        second_manifest, "orphan_foreign_keys", "line_items"
    )
    assert _injector_indices(first_manifest, "tombstones", "orders") != _injector_indices(
        second_manifest, "tombstones", "orders"
    )


def test_base_instant_and_ast_guard_cover_the_whole_package() -> None:
    parsed_base = datetime.fromisoformat(BASE_INSTANT)
    assert parsed_base.tzinfo is not None
    assert parsed_base.utcoffset().total_seconds() == 0
    assert find_nondeterministic_sources(PACKAGE_DIR) == []

    # Deliberately broken implementation probe: aliases, entropy modules,
    # indirect getattr, unseeded RNGs, and random use inside a function must
    # all be rejected.
    broken = ast.parse(
        """
import os as entropy
import random
import secrets
import time as clock
import uuid
from datetime import datetime as DateTime

random.random()
now = DateTime.now

def build():
    bound = clock.perf_counter
    return (
        random.randrange(4),
        random.Random(),
        random.SystemRandom(),
        clock.time_ns(),
        clock.localtime(),
        clock.perf_counter_ns(),
        clock.monotonic_ns(),
        entropy.urandom(4),
        secrets.token_hex(),
        uuid.uuid4(),
        DateTime.utcfromtimestamp(0),
        DateTime.now().astimezone(),
        now(),
        bound(),
        getattr(clock, 'time')(),
    )
"""
    )
    visitor = _NondeterminismVisitor(Path("broken.py"))
    visitor.visit(broken)
    findings = "\n".join(visitor.violations)
    assert "module-scope random use" in findings
    assert "random.randrange" in findings
    assert "unseeded random.Random" in findings
    assert any(
        line.rsplit(": ", 1)[-1] == "forbidden random.SystemRandom"
        for line in visitor.violations
    )
    assert "time.time" in findings
    assert "time.time_ns" in findings
    assert "time.localtime" in findings
    assert "time.perf_counter_ns" in findings
    assert "time.monotonic_ns" in findings
    assert "os.urandom" in findings
    assert "uuid.uuid4" in findings
    assert "secrets.token_hex" in findings
    assert "datetime.now" in findings
    assert "datetime.utcfromtimestamp" in findings
    assert "attribute alias" in findings
    assert "astimezone" in findings
    assert "astimezone" in findings


def test_gitattributes_is_effective_in_a_staged_git_fixture(tmp_path: Path) -> None:
    output = tmp_path / "fixture"
    generate_dataset("zero_row_optional", 4, output)
    repo = tmp_path / "git-fixture"
    shutil.copytree(output, repo)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    checked = subprocess.run(
        ["git", "check-attr", "filter", "--", "data/primary.csv"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert checked.stdout.strip().endswith("filter: unset")


def test_pinned_grain_seed_is_a_real_scenario_config(tmp_path: Path) -> None:
    config = Path(__file__).parents[1] / "scenarios" / "grain_trap.yaml"
    values = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert values["dataset"] == "grain_trap"
    assert values["seed"] == 29
    assert values["query"]["measure"] == "regional_revenue"

    output = tmp_path / "pinned"
    generate_dataset("grain_trap", int(values["seed"]), output)
    assert _manifest(output)["seed"] == 29


def test_grain_trap_trap_property_survives_seed_sweep(tmp_path: Path) -> None:
    output = tmp_path / "sweep"
    for seed in range(300):
        generate_dataset("grain_trap", seed, output)
        with (output / "data/orders.csv").open(encoding="utf-8", newline="") as handle:
            orders = list(csv.DictReader(handle))
        rows = json.loads((output / "gold/grain_trap_by_region.json").read_text(encoding="utf-8"))
        diagnostics = json.loads(
            (output / "gold/grain_trap_diagnostics.json").read_text(encoding="utf-8")
        )
        correct = {}
        for order in orders:
            if order["status"] != "deleted":
                correct[order["region"]] = correct.get(order["region"], Decimal("0")) + Decimal(
                    order["order_amount"]
                )
        naive = {
            row["region"]: row["naive_fanout_revenue"]
            for row in diagnostics["regions"]
        }
        assert rows
        assert all(
            Decimal(str(row["regional_revenue"])) == correct[row["region"]]
            and row["regional_revenue"] != naive[row["region"]]
            for row in rows
        )
        # The graded measure is made from integer cents, so it cannot contain
        # a half-cent tie.  Rounded typical-order averages remain diagnostics;
        # seed 29 intentionally has two such presentation ties.
        for row in rows:
            exact_cents = correct[row["region"]] * 100
            assert exact_cents == exact_cents.to_integral_value()


def test_pii_markers_change_with_seed(tmp_path: Path) -> None:
    first = tmp_path / "seed-29"
    second = tmp_path / "seed-30"
    generate_dataset("zero_row_optional", 29, first)
    generate_dataset("zero_row_optional", 30, second)
    assert _manifest(first)["pii_markers"] != _manifest(second)["pii_markers"]

"""Tests proving the SQL reference is the independent T0 oracle."""

from __future__ import annotations

import anyio
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import platform

from inspect_ai.model import ChatMessageAssistant, ChatMessageTool, ModelName
from inspect_ai.scorer import CORRECT, INCORRECT, Target
from inspect_ai.solver import TaskState
from inspect_ai.tool import ToolCall
import pytest

from dp_scenarios.synthgen.cli import main
from dp_scenarios.synthgen.generator import generate_dataset, verify_dataset
from nxd_eval.scorers import rows_equal


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def _score_rows(rows: list[dict], gold: list[dict]):
    state = TaskState(
        model=ModelName("mockllm/model"),
        sample_id="grain-trap",
        epoch=0,
        input="q",
        messages=[
            ChatMessageAssistant(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        function="run_semantic_query",
                        arguments={"measures": ["regional_revenue"]},
                    )
                ],
            ),
            ChatMessageTool(
                content=json.dumps({"compiled_sql": "select", "rows": rows}),
                function="run_semantic_query",
                tool_call_id="call-1",
            ),
        ],
        metadata={"bucket": "answer"},
    )
    return anyio.run(lambda: rows_equal()(state, Target(json.dumps(gold))))


def test_grain_trap_gold_is_typed_ex_shape_and_discriminates_fanout(
    tmp_path: Path,
) -> None:
    output = tmp_path / "grain"
    generate_dataset("grain_trap", 29, output)
    with (output / "data/orders.csv").open(encoding="utf-8", newline="") as handle:
        orders = list(csv.DictReader(handle))
    with (output / "data/line_items.csv").open(encoding="utf-8", newline="") as handle:
        line_items = list(csv.DictReader(handle))
    gold_rows = json.loads(
        (output / "gold/grain_trap_by_region.json").read_text(encoding="utf-8")
    )
    diagnostics = json.loads(
        (output / "gold/grain_trap_diagnostics.json").read_text(encoding="utf-8")
    )
    gold_control = json.loads(
        (output / "gold/grain_trap_control.json").read_text(encoding="utf-8")
    )
    data_control = json.loads(
        (output / "data/grain_trap_control.json").read_text(encoding="utf-8")
    )

    assert isinstance(gold_rows, list)
    assert all(set(row) == {"region", "regional_revenue"} for row in gold_rows)
    assert all(isinstance(row["regional_revenue"], float) for row in gold_rows)
    assert gold_control == data_control
    assert isinstance(gold_control, list)
    assert set(gold_control[0]) == {"control_total"}

    active = [row for row in orders if row["status"] != "deleted"]
    by_id = {row["order_id"]: row for row in active}
    by_region: dict[str, list[dict[str, str]]] = {}
    joined_by_region: dict[str, list[dict[str, str]]] = {}
    for row in active:
        by_region.setdefault(row["region"], []).append(row)
    for line in line_items:
        parent = by_id.get(line["order_id"])
        if parent is not None:
            joined_by_region.setdefault(parent["region"], []).append(parent)

    independent_total = sum(Decimal(row["order_amount"]) for row in active)
    assert _money(independent_total) == f'{gold_control[0]["control_total"]:.2f}'
    gold_by_region = {row["region"]: row for row in gold_rows}
    diagnostic_by_region = {row["region"]: row for row in diagnostics["regions"]}
    correct_rows = []
    naive_rows = []
    for region, region_orders in by_region.items():
        correct = sum(Decimal(row["order_amount"]) for row in region_orders) / len(region_orders)
        fanout_rows = joined_by_region[region]
        naive = sum(Decimal(row["order_amount"]) for row in fanout_rows) / len(fanout_rows)
        correct_revenue = sum(Decimal(row["order_amount"]) for row in region_orders)
        naive_revenue = sum(Decimal(row["order_amount"]) for row in fanout_rows)
        assert float(correct_revenue) == gold_by_region[region]["regional_revenue"]
        assert float(correct_revenue) == diagnostic_by_region[region]["regional_revenue"]
        assert float(naive_revenue) == diagnostic_by_region[region]["naive_fanout_revenue"]
        assert float(_money(correct)) == diagnostic_by_region[region]["correct_typical_order_value"]
        assert float(_money(naive)) == diagnostic_by_region[region]["naive_fanout_order_value"]
        assert float(_money(correct)) != float(_money(naive))
        correct_rows.append(
            {"region": region, "regional_revenue": float(correct_revenue)}
        )
        naive_rows.append(
            {"region": region, "regional_revenue": float(naive_revenue)}
        )

    correct_score = _score_rows(correct_rows, gold_rows)
    naive_score = _score_rows(naive_rows, gold_rows)
    assert correct_score.value == CORRECT
    assert naive_score.value == INCORRECT


def test_zero_row_optional_gold_has_exact_required_and_optional_counts(tmp_path: Path) -> None:
    output = tmp_path / "zero"
    generate_dataset("zero_row_optional", 29, output)
    rows = json.loads(
        (output / "gold/zero_row_optional_counts.json").read_text(encoding="utf-8")
    )
    diagnostics = json.loads(
        (output / "gold/zero_row_optional_diagnostics.json").read_text(encoding="utf-8")
    )
    with (output / "data/primary.csv").open(encoding="utf-8", newline="") as handle:
        primary_count = sum(1 for _ in csv.DictReader(handle))
    with (output / "data/optional_events.csv").open(encoding="utf-8", newline="") as handle:
        optional_count = sum(1 for _ in csv.DictReader(handle))
    assert rows == [
        {"resource": "optional_events", "row_count": 0},
        {"resource": "primary", "row_count": 5},
    ]
    assert diagnostics == [
        {"resource": "optional_events", "row_count": 0, "required": False},
        {"resource": "primary", "row_count": 5, "required": True},
    ]
    assert primary_count == 5
    assert optional_count == 0


def test_cli_verify_rederives_gold_and_fails_after_one_gold_byte_changes(
    tmp_path: Path,
) -> None:
    output = tmp_path / "cli"
    assert main(["grain_trap", "--seed", "29", "--out-dir", str(output)]) == 0
    assert main(["verify", "--out-dir", str(output)]) == 0

    mutated = tmp_path / "mutated"
    assert main(
        [
            "--mode",
            "mutate",
            "--dataset",
            "grain_trap",
            "--seed",
            "29",
            "--out-dir",
            str(mutated),
        ]
    ) == 0
    assert main(["verify", "--out-dir", str(mutated)]) == 1
    assert main(["verify", "--allow-mutation", "--out-dir", str(mutated)]) == 0

    manifest_path = output / "fixture-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["python_version"] = "0.0.0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.warns(RuntimeWarning, match="interpreter version"):
        assert verify_dataset(output)
    manifest_path.write_text(
        json.dumps({**manifest, "python_version": platform.python_version()}),
        encoding="utf-8",
    )

    gold_path = output / "gold/grain_trap_by_region.json"
    original = gold_path.read_bytes()
    gold_path.write_bytes(original.replace(b"north", b"nortH", 1))
    assert main(["verify", "--out-dir", str(output)]) == 1

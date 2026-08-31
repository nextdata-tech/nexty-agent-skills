"""Guard tests for the silent fan-out scenario and its EX-scored gold."""

from __future__ import annotations

import csv
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from dp_scenarios.scenario import load_scenario, scenario_script_hash


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/s6-grain-trap")


def test_turn_one_is_one_analyst_sentence_without_source_driver_or_mechanism_nouns() -> None:
    ask = SCENARIO.answer_sheet.turn_one
    forbidden = {
        "source", "driver", "mechanism", "data", "dataset", "table", "join",
        "aggregation", "average", "sum", "order", "line item", "deleted", "tombstone",
        "revenue", "total", "per", "each", "group", "count", "grain", "parent",
        "child", "fan-out", "row", "record",
    }
    lowered = ask.casefold()
    assert sum(character in ".!?" for character in ask) == 1
    assert not any(term in lowered for term in forbidden)
    assert "regional_revenue" not in lowered


def test_gold_scoring_path_discriminates_correct_and_naive_fanout_answers(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "grain")
    gold = SCENARIO.load_gold("answer", generated.out_dir)
    with (generated.data_dir / "orders.csv").open(encoding="utf-8", newline="") as handle:
        orders = list(csv.DictReader(handle))
    with (generated.data_dir / "line_items.csv").open(encoding="utf-8", newline="") as handle:
        line_items = list(csv.DictReader(handle))
    active = [row for row in orders if row["status"] != "deleted"]
    active_by_id = {row["order_id"]: row for row in active}
    correct_by_region: dict[str, Decimal] = {}
    naive_by_region: dict[str, Decimal] = {}
    for row in active:
        correct_by_region[row["region"]] = correct_by_region.get(row["region"], Decimal("0")) + Decimal(row["order_amount"])
    for line in line_items:
        parent = active_by_id.get(line["order_id"])
        if parent is not None:
            region = parent["region"]
            naive_by_region[region] = naive_by_region.get(region, Decimal("0")) + Decimal(parent["order_amount"])
    correct_rows = tuple(
        {"region": region, "regional_revenue": float(value)}
        for region, value in sorted(correct_by_region.items())
    )
    naive = tuple(
        {"region": region, "regional_revenue": float(value)}
        for region, value in sorted(naive_by_region.items())
    )
    diagnostics = SCENARIO.raw_gold("diagnostics", generated.out_dir)

    assert correct_rows == tuple(sorted(gold.rows, key=lambda row: row["region"]))
    assert all(
        float(naive_by_region[row["region"]]) == row["naive_fanout_revenue"]
        for row in diagnostics["regions"]
    )

    correct = SCENARIO.score_query(correct_rows, generated.out_dir)
    wrong = SCENARIO.score_query(naive, generated.out_dir)
    assert correct.verdict == "correct"
    assert correct.gold_gate.passed
    assert wrong.verdict == "expected_naive_fanout"
    assert not wrong.gold_gate.passed
    assert "g6_query_rows_differ" in wrong.gold_gate.codes
    assert wrong.naive_gate.passed


def test_control_total_equals_an_independent_sum_of_the_source_csv(tmp_path: Path) -> None:
    rows = SCENARIO.load_gold("answer").rows
    graded = sum((Decimal(str(row["regional_revenue"])) for row in rows), Decimal("0"))
    assert graded == Decimal(str(SCENARIO.control_total))
    assert SCENARIO.graded_control_total() == SCENARIO.control_total

    generated = SCENARIO.generate_fixture(tmp_path / "grain")
    with (generated.data_dir / "orders.csv").open(encoding="utf-8", newline="") as handle:
        source_total = sum(
            (Decimal(row["order_amount"]) for row in csv.DictReader(handle) if row["status"] == "active"),
            Decimal("0"),
        )
    assert source_total == Decimal(str(SCENARIO.control_total))


def test_follow_up_reads_both_static_grain_contracts_and_classifies_naive_answer() -> None:
    closure = {
        "semantic": {
            "grain": "order",
            "metrics": {"regional_revenue": {"aggregation": "sum"}},
        }
    }
    good = SCENARIO.follow_up_check(closure)
    assert good["passed"]
    assert SCENARIO.follow_up_gate(
        closure,
        fired_plants={"fired_plant_ids": ["grain_trap_fanout"]},
    ).passed

    missing_aggregation = SCENARIO.follow_up_check({"semantic": {"grain": "order", "metrics": {}}})
    wrong_grain = SCENARIO.follow_up_check({
        "semantic": {
            "grain": "line_item",
            "metrics": {"regional_revenue": {"aggregation": "sum"}},
        }
    })
    assert not missing_aggregation["passed"]
    assert "aggregation_not_declared" in missing_aggregation["findings"]
    assert not wrong_grain["passed"]
    assert "grain_mismatch" in wrong_grain["findings"]


def test_follow_up_path_reads_only_the_named_semantic_document(tmp_path: Path) -> None:
    closure = tmp_path / "closure"
    closure.mkdir()
    (closure / "semantic.json").write_text(
        '{"semantic": {"grain": "order", "metrics": {"regional_revenue": {"aggregation": "sum"}}}}\n',
        encoding="utf-8",
    )
    (closure / "unrelated.json").write_text(
        '{"semantic": {"grain": "line_item", "metrics": {}}}\n',
        encoding="utf-8",
    )

    result = SCENARIO.follow_up_check(closure)

    assert result["passed"]


def test_follow_up_diagnosis_distinguishes_naive_from_other_wrong() -> None:
    closure = {"semantic": {"grain": "order", "metrics": {"regional_revenue": {"aggregation": "sum"}}}}
    gold = SCENARIO.load_gold("answer").rows
    diagnostics = SCENARIO.raw_gold("diagnostics")
    naive = tuple({"region": row["region"], "regional_revenue": row["naive_fanout_revenue"]} for row in diagnostics["regions"])
    other = tuple({"region": row["region"], "regional_revenue": 0.0} for row in gold)
    assert SCENARIO.follow_up_check(closure, naive)["query_verdict"] == "expected_naive_fanout"
    assert SCENARIO.follow_up_check(closure, other)["query_verdict"] == "other_wrong"


def test_follow_up_merges_control_total_findings_with_query_findings() -> None:
    closure = {"semantic": {"grain": "order", "metrics": {"regional_revenue": {"aggregation": "sum"}}}}
    rows = [dict(row) for row in SCENARIO.load_gold("answer").rows]
    rows[0]["regional_revenue"] = float(rows[0]["regional_revenue"]) + 1.0

    result = SCENARIO.follow_up_check(closure, query_rows=rows)

    assert SCENARIO.has_scoreable_answer_gold
    assert result["query_verdict"] == "other_wrong"
    assert result["control_total_verdict"] == "violated"
    assert "control_total_mismatch" in result["findings"]


def test_follow_up_reconciles_against_generated_fixture_control_total(tmp_path: Path) -> None:
    changed = replace(SCENARIO, fixture=replace(SCENARIO.fixture, seed=SCENARIO.seed + 1))
    generated = changed.generate_fixture(tmp_path / "grain")
    rows = changed.load_gold("answer", generated.out_dir).rows
    closure = {"semantic": {"grain": "order", "metrics": {"regional_revenue": {"aggregation": "sum"}}}}

    assert changed.raw_gold("control_total", generated.out_dir) != changed.raw_gold("control_total")
    result = changed.follow_up_check(closure, generated.out_dir, rows)

    assert result["query_verdict"] == "correct"
    assert result["control_total_verdict"] == "satisfied"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("patience_turns", 99),
        ("label", "a different analyst"),
        ("behaviors", {"interrogative": True}),
    ],
)
def test_operator_script_hash_is_stable_and_changes_for_persona_mutations(field: str, value: object) -> None:
    loaded_again = load_scenario(ROOT / "scenarios/s6-grain-trap")
    assert SCENARIO.operator_script_hash == loaded_again.operator_script_hash
    assert SCENARIO.operator_script_hash == scenario_script_hash(SCENARIO.operator_script)
    changed_script = replace(
        SCENARIO.operator_script,
        turns=SCENARIO.operator_script.turns[:-1]
        + ({"text": "A changed final check.", "substitute_reply": False},),
    )
    persona_kwargs = {field: value}
    if field == "behaviors":
        persona_kwargs["behaviors"] = {**dict(SCENARIO.operator_script.persona.behaviors), **value}  # type: ignore[dict-item]
    changed_persona = replace(SCENARIO.operator_script.persona, **persona_kwargs)
    changed_persona_script = replace(SCENARIO.operator_script, persona=changed_persona)
    assert SCENARIO.operator_script_hash != scenario_script_hash(changed_script)
    assert SCENARIO.operator_script_hash != scenario_script_hash(changed_persona_script)


def test_declared_seed_recreates_every_committed_gold_artifact_byte_for_byte(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "grain")

    for name, package_path in SCENARIO.gold_paths.items():
        generated_path = generated.out_dir / SCENARIO.gold_refs[name]
        assert generated_path.read_bytes() == package_path.read_bytes()


def test_required_plant_is_event_backed_and_fired_evidence_is_a_prerequisite() -> None:
    assert SCENARIO.plant_vocabulary == {
        "grain_trap_fanout",
        "orphan_foreign_keys",
        "pii_sentinels",
        "tombstones",
    }
    assert SCENARIO.events.planted_card_ids() == SCENARIO.required_plants
    assert SCENARIO.check_fired_plants({"fired_plant_ids": ["grain_trap_fanout"]}).passed
    assert SCENARIO.check_fired_plants({"fired_plant_ids": []}).ungraded

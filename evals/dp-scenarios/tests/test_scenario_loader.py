"""Guard tests for strict, package-only scenario declarations."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest
import yaml

from dp_scenarios.scenario import ScenarioError, load_scenario, load_scenarios
from dp_scenarios.synthgen import get_dataset


ROOT = Path(__file__).parents[1]
SCENARIO_ROOT = ROOT / "scenarios"


def _copy_s6_package(tmp_path: Path) -> Path:
    root = tmp_path / "scenarios"
    root.mkdir()
    shutil.copytree(SCENARIO_ROOT / "s6-grain-trap", root / "s6-grain-trap")
    (root / "_personas").mkdir()
    shutil.copy2(SCENARIO_ROOT / "_personas/smoke.yaml", root / "_personas/smoke.yaml")
    return root / "s6-grain-trap"


def _copy_s5_package(tmp_path: Path) -> Path:
    root = tmp_path / "scenarios"
    root.mkdir()
    shutil.copytree(SCENARIO_ROOT / "s5-smoke-zero-row", root / "s5-smoke-zero-row")
    (root / "_personas").mkdir()
    shutil.copy2(SCENARIO_ROOT / "_personas/smoke.yaml", root / "_personas/smoke.yaml")
    return root / "s5-smoke-zero-row"


def test_both_scenario_packages_load_and_resolve_their_declared_references(tmp_path: Path) -> None:
    scenarios = load_scenarios(SCENARIO_ROOT)
    assert {scenario.id for scenario in scenarios} == {"S6", "S5-smoke"}
    for scenario in scenarios:
        assert get_dataset(scenario.dataset).name == scenario.dataset
        assert scenario.seed == 29
        assert scenario.fixture_variant
        assert scenario.coverage["variant"] == scenario.fixture_variant
        assert scenario.coverage["untested"]
        assert scenario.persona_path.is_file()
        assert scenario.answer_sheet_path.is_file()
        assert scenario.events_path.is_file()
        assert scenario.required_plants
        assert set(scenario.gates) == {f"G{index}" for index in range(1, 8)}
        assert scenario.gates["G7"].kind in {"grain_and_aggregation", "optional_required_outputs"}
        generated = scenario.generate_fixture(tmp_path / scenario.id)
        for name, path in scenario.gold.items():
            assert path.is_file()
            generated_path = scenario.gold_path(name, generated.out_dir)
            assert generated_path.is_file()
            assert generated_path.read_bytes() == path.read_bytes()


@pytest.mark.parametrize("missing", sorted({
    "version", "id", "tier", "fixture", "turn_budget", "repeatability",
    "coverage", "persona", "answer_sheet", "events", "phase_map", "required_plants",
    "gates", "gold", "operator",
}))
def test_loader_rejects_each_missing_required_declaration_field(missing: str, tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    del source[missing]
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="missing"):
        load_scenario(package)


def test_loader_requires_the_explicit_fixture_plant_declaration(tmp_path: Path) -> None:
    package = _copy_s5_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["fixture"].pop("plant")
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="fixture requires dataset, seed, variant, and plant"):
        load_scenario(package)


def test_loader_rejects_a_scenario_that_declares_no_plants(tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["required_plants"] = []
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="required_plants"):
        load_scenario(package)


def test_loader_rejects_a_free_text_plant_identifier(tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["required_plants"] = ["bogus_plant"]
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="unknown identifier"):
        load_scenario(package)


def test_loader_rejects_each_unreachable_certified_phase(tmp_path: Path) -> None:
    package = _copy_s5_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["phase_map"][5] = 4
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="unreachable"):
        load_scenario(package)


def test_loader_rejects_a_phase_map_that_does_not_cover_every_turn(tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["phase_map"].pop(7)
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="exactly one phase for every"):
        load_scenario(package)


def test_loader_rejects_an_unknown_follow_up_kind(tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gates"]["G7"]["kind"] = "bogus_follow_up"
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="supported"):
        load_scenario(package)


def test_loader_rejects_a_repeatability_epoch_count_that_does_not_match_tier(tmp_path: Path) -> None:
    package = _copy_s5_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["repeatability"]["epochs"] = 1
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="epochs"):
        load_scenario(package)


def test_loader_rejects_a_certified_gate_without_scoreable_gold(tmp_path: Path) -> None:
    package = _copy_s5_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["repeatability"]["certification"]["gates"] = ["G6"]
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="G6.*answer"):
        load_scenario(package)


def test_loader_rejects_a_deterministic_certificate_with_a_lower_bound_below_contract(tmp_path: Path) -> None:
    package = _copy_s5_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["repeatability"]["certification"]["lower_bound"] = 0.5
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="lower_bound 0.90"):
        load_scenario(package)


def test_loader_rejects_a_scenario_tier_outside_the_manifest_vocabulary(tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["tier"] = "bogus"
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="unknown scenario tier"):
        load_scenario(package)


def test_loader_rejects_a_budget_smaller_than_the_script(tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["turn_budget"] = 1
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="at least the number"):
        load_scenario(package)


@pytest.mark.parametrize("reference", ["persona", "answer_sheet", "events"])
def test_loader_rejects_a_missing_declared_runtime_reference(reference: str, tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source[reference] = "missing.yaml"
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="does not resolve"):
        load_scenario(package)


@pytest.mark.parametrize("gold_key", ["answer", "control_total", "diagnostics"])
def test_loader_rejects_a_missing_declared_s6_gold_reference(gold_key: str, tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gold"][gold_key] = "gold/missing.json"
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="does not resolve"):
        load_scenario(package)


def test_loader_rejects_an_empty_or_extra_gold_key_set(tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gold"].pop("answer")
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="gold keys"):
        load_scenario(package)

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    package = _copy_s6_package(empty_root)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gold"] = {}
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="gold keys"):
        load_scenario(package)

    extra_root = tmp_path / "extra"
    extra_root.mkdir()
    package = _copy_s6_package(extra_root)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gold"]["extra"] = source["gold"]["answer"]
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="gold keys"):
        load_scenario(package)


def test_loader_rejects_an_answer_sheet_identity_mismatch(tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    answer = package / "answer-sheet.yaml"
    source = yaml.safe_load(answer.read_text(encoding="utf-8"))
    source["scenario_id"] = "not-S6"
    answer.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="scenario_id"):
        load_scenario(package)


def test_follow_up_gate_propagates_scenario_finding_and_machine_readability_is_checked(tmp_path: Path) -> None:
    package = _copy_s5_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gates"]["G7"]["resources"]["optional_events"]["required"] = True
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="diagnostics gold requiredness"):
        load_scenario(package)


def test_loader_rejects_a_required_plant_without_a_backing_event_card(tmp_path: Path) -> None:
    package = _copy_s5_package(tmp_path)
    events = package / "events.yaml"
    events.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ScenarioError, match="backed by planted event"):
        load_scenario(package)


def test_loader_rejects_a_required_plant_without_manifest_evidence(tmp_path: Path) -> None:
    package = _copy_s5_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gates"]["G7"]["plant_evidence"] = {}
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="plant_evidence.*missing"):
        load_scenario(package)


def test_loader_rejects_a_non_positive_turn_budget(tmp_path: Path) -> None:
    package = _copy_s6_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["turn_budget"] = 0
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="positive integer"):
        load_scenario(package)


def test_discovery_does_not_need_a_python_registry() -> None:
    discovered = load_scenarios(SCENARIO_ROOT)
    direct = tuple(load_scenario(SCENARIO_ROOT / name) for name in ("s5-smoke-zero-row", "s6-grain-trap"))
    assert tuple(item.id for item in discovered) == tuple(item.id for item in direct)

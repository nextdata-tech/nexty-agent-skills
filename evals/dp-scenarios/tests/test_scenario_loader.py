"""Guard tests for strict, package-only scenario declarations."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest
import yaml

from dp_scenarios.grading import GATE_PHASES
from dp_scenarios.scenario import ScenarioError, load_scenario, load_scenarios, select_tier
from dp_scenarios.synthgen import get_dataset


ROOT = Path(__file__).parents[1]
SCENARIO_ROOT = ROOT / "scenarios"


def _copy_parent_child_package(tmp_path: Path) -> Path:
    root = tmp_path / "scenarios"
    root.mkdir()
    shutil.copytree(SCENARIO_ROOT / "parent-child-grain-trap", root / "parent-child-grain-trap")
    (root / "_personas").mkdir()
    shutil.copy2(SCENARIO_ROOT / "_personas/smoke.yaml", root / "_personas/smoke.yaml")
    return root / "parent-child-grain-trap"


def _copy_zero_row_package(tmp_path: Path) -> Path:
    root = tmp_path / "scenarios"
    root.mkdir()
    shutil.copytree(SCENARIO_ROOT / "zero-row-optional-output", root / "zero-row-optional-output")
    (root / "_personas").mkdir()
    shutil.copy2(SCENARIO_ROOT / "_personas/smoke.yaml", root / "_personas/smoke.yaml")
    return root / "zero-row-optional-output"


def test_both_scenario_packages_load_and_resolve_their_declared_references(tmp_path: Path) -> None:
    scenarios = load_scenarios(SCENARIO_ROOT)
    assert {scenario.id for scenario in scenarios} == {
        "parent-child-grain-trap",
        "zero-row-optional-output",
        "credential-rotation",
        "sigterm-diagnosis",
    }
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
        assert set(scenario.gates) == set(GATE_PHASES)
        assert scenario.gates["follow-up"].kind in {
            "grain_and_aggregation",
            "optional_required_outputs",
            "credential_rotation",
            "sigterm_diagnosis",
        }
        generated = scenario.generate_fixture(tmp_path / scenario.id)
        for name, path in scenario.gold.items():
            assert path.is_file()
        if scenario.gates["follow-up"].kind in {"credential_rotation", "sigterm_diagnosis"}:
            # credential-rotation's committed gold documents facts about the
            # live Postgres closure, and sigterm-diagnosis's documents facts
            # about the SIGTERM/transform-window drill (both reconciled
            # directly against their own regenerated evidence in their
            # dedicated test modules); neither is reproduced by the plain CSV
            # synthgen path the other two scenarios use, so neither is
            # compared byte-for-byte against `generate_fixture` here.
            continue
        for name, path in scenario.gold.items():
            generated_path = scenario.gold_path(name, generated.out_dir)
            assert generated_path.is_file()
            assert generated_path.read_bytes() == path.read_bytes()


@pytest.mark.parametrize("missing", sorted({
    "version", "id", "tier", "fixture", "turn_budget", "repeatability",
    "coverage", "persona", "answer_sheet", "events", "phase_map", "required_plants",
    "gates", "gold", "operator",
}))
def test_loader_rejects_each_missing_required_declaration_field(missing: str, tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    del source[missing]
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="missing"):
        load_scenario(package)


def test_loader_requires_the_explicit_fixture_plant_declaration(tmp_path: Path) -> None:
    package = _copy_zero_row_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["fixture"].pop("plant")
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="fixture requires dataset, seed, variant, and plant"):
        load_scenario(package)


def test_loader_rejects_a_scenario_that_declares_no_plants(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["required_plants"] = []
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="required_plants"):
        load_scenario(package)


def test_loader_rejects_a_free_text_plant_identifier(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["required_plants"] = ["bogus_plant"]
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="unknown identifier"):
        load_scenario(package)


def test_loader_rejects_each_unreachable_certified_phase(tmp_path: Path) -> None:
    package = _copy_zero_row_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["phase_map"][5] = 4
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="unreachable"):
        load_scenario(package)


def test_loader_rejects_a_phase_map_that_does_not_cover_every_turn(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["phase_map"].pop(7)
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="exactly one phase for every"):
        load_scenario(package)


def test_loader_rejects_an_unknown_follow_up_kind(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gates"]["follow-up"]["kind"] = "bogus_follow_up"
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="supported"):
        load_scenario(package)


def test_loader_rejects_a_repeatability_epoch_count_that_does_not_match_tier(tmp_path: Path) -> None:
    package = _copy_zero_row_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["repeatability"]["epochs"] = 1
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="epochs"):
        load_scenario(package)


def test_loader_rejects_a_certified_gate_without_scoreable_gold(tmp_path: Path) -> None:
    package = _copy_zero_row_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["repeatability"]["certification"]["gates"] = ["query"]
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="query.*answer"):
        load_scenario(package)


def test_loader_rejects_a_deterministic_certificate_with_a_lower_bound_below_contract(tmp_path: Path) -> None:
    package = _copy_zero_row_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["repeatability"]["certification"]["lower_bound"] = 0.5
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="lower_bound 0.90"):
        load_scenario(package)


def test_loader_rejects_a_scenario_tier_outside_the_manifest_vocabulary(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["tier"] = "bogus"
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="unknown scenario tier"):
        load_scenario(package)


def test_loader_rejects_a_budget_smaller_than_the_script(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["turn_budget"] = 1
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="at least the number"):
        load_scenario(package)


@pytest.mark.parametrize("reference", ["persona", "answer_sheet", "events"])
def test_loader_rejects_a_missing_declared_runtime_reference(reference: str, tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source[reference] = "missing.yaml"
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="does not resolve"):
        load_scenario(package)


@pytest.mark.parametrize("gold_key", ["answer", "control_total", "diagnostics"])
def test_loader_rejects_a_missing_declared_parent_child_gold_reference(gold_key: str, tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gold"][gold_key] = "gold/missing.json"
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="does not resolve"):
        load_scenario(package)


def test_loader_rejects_an_empty_or_extra_gold_key_set(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gold"].pop("answer")
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="gold keys"):
        load_scenario(package)

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    package = _copy_parent_child_package(empty_root)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gold"] = {}
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="gold keys"):
        load_scenario(package)

    extra_root = tmp_path / "extra"
    extra_root.mkdir()
    package = _copy_parent_child_package(extra_root)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gold"]["extra"] = source["gold"]["answer"]
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="gold keys"):
        load_scenario(package)


def test_loader_rejects_an_answer_sheet_identity_mismatch(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    answer = package / "answer-sheet.yaml"
    source = yaml.safe_load(answer.read_text(encoding="utf-8"))
    source["scenario_id"] = "not-parent-child-grain-trap"
    answer.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="scenario_id"):
        load_scenario(package)


def test_follow_up_gate_propagates_scenario_finding_and_machine_readability_is_checked(tmp_path: Path) -> None:
    package = _copy_zero_row_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gates"]["follow-up"]["resources"]["optional_events"]["required"] = True
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScenarioError, match="diagnostics gold requiredness"):
        load_scenario(package)


def test_loader_rejects_a_required_plant_without_a_backing_event_card(tmp_path: Path) -> None:
    package = _copy_zero_row_package(tmp_path)
    events = package / "events.yaml"
    events.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ScenarioError, match="backed by planted event"):
        load_scenario(package)


def test_loader_rejects_a_required_plant_without_manifest_evidence(tmp_path: Path) -> None:
    package = _copy_zero_row_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gates"]["follow-up"]["plant_evidence"] = {}
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="plant_evidence.*missing"):
        load_scenario(package)


def test_loader_rejects_a_non_positive_turn_budget(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["turn_budget"] = 0
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    with pytest.raises(ScenarioError, match="positive integer"):
        load_scenario(package)


def test_discovery_does_not_need_a_python_registry() -> None:
    discovered = load_scenarios(SCENARIO_ROOT)
    # Ordered by each package's declared run_order: zero-row-optional-output (1),
    # parent-child-grain-trap (2), credential-rotation (3), sigterm-diagnosis (4).
    direct = tuple(
        load_scenario(SCENARIO_ROOT / name)
        for name in (
            "zero-row-optional-output",
            "parent-child-grain-trap",
            "credential-rotation",
            "sigterm-diagnosis",
        )
    )
    assert tuple(item.id for item in discovered) == tuple(item.id for item in direct)


def _rename_answer_sheet(package: Path, reference: str, scenario_id: str) -> None:
    sheet_path = (package / reference).resolve()
    sheet = yaml.safe_load(sheet_path.read_text(encoding="utf-8"))
    sheet["scenario_id"] = scenario_id
    sheet_path.write_text(yaml.safe_dump(sheet, sort_keys=False), encoding="utf-8")


def test_tier_order_follows_declared_run_order_not_directory_name(tmp_path: Path) -> None:
    root = tmp_path / "scenarios"
    shutil.copytree(SCENARIO_ROOT, root)
    shutil.rmtree(root / "zero-row-optional-output")
    shutil.rmtree(root / "parent-child-grain-trap")
    shutil.rmtree(root / "credential-rotation")
    shutil.rmtree(root / "sigterm-diagnosis")
    for name, run_order in (("aaa-first-by-name", 2), ("zzz-last-by-name", 1)):
        package = root / name
        shutil.copytree(SCENARIO_ROOT / "parent-child-grain-trap", package)
        declaration = package / "scenario.yaml"
        source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
        source["id"] = name
        source["run_order"] = run_order
        declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
        _rename_answer_sheet(package, source["answer_sheet"], name)

    assert [scenario.id for scenario in load_scenarios(root)] == [
        "zzz-last-by-name",
        "aaa-first-by-name",
    ]


def test_two_scenarios_cannot_claim_the_same_run_order(tmp_path: Path) -> None:
    root = tmp_path / "scenarios"
    shutil.copytree(SCENARIO_ROOT, root)
    shutil.rmtree(root / "zero-row-optional-output")
    shutil.rmtree(root / "parent-child-grain-trap")
    shutil.rmtree(root / "credential-rotation")
    shutil.rmtree(root / "sigterm-diagnosis")
    for name in ("one", "two"):
        package = root / name
        shutil.copytree(SCENARIO_ROOT / "parent-child-grain-trap", package)
        declaration = package / "scenario.yaml"
        source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
        source["id"] = name
        source["run_order"] = 1
        declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
        _rename_answer_sheet(package, source["answer_sheet"], name)

    with pytest.raises(ScenarioError, match="run_order"):
        load_scenarios(root)


def test_an_omitted_gate_value_means_the_gate_runs_its_standard_check() -> None:
    scenario = load_scenario(SCENARIO_ROOT / "parent-child-grain-trap")

    assert scenario.gates["intake"].kind == "intake"
    assert scenario.gates["query"].kind == "query"
    assert scenario.gates["follow-up"].kind == "grain_and_aggregation"


def test_legacy_t0_scenario_tier_remains_accepted(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["tier"] = "T0"
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    assert load_scenario(package).tier == "T0"


def test_select_tier_returns_only_the_scenarios_declaring_that_tier() -> None:
    """The smoke tier must not silently acquire a core scenario.

    ``load_scenarios`` deliberately loads every package under a root, so the
    tier boundary is only real if something selects on it. Before this,
    ``scenario.tier`` was carried into the manifest and never used to choose
    what ran.
    """

    scenarios = load_scenarios(SCENARIO_ROOT)
    assert {scenario.id for scenario in scenarios} == {
        "parent-child-grain-trap",
        "zero-row-optional-output",
        "credential-rotation",
        "sigterm-diagnosis",
    }
    smoke = select_tier(scenarios, "smoke")
    assert {scenario.id for scenario in smoke} == {
        "parent-child-grain-trap",
        "zero-row-optional-output",
    }
    core = select_tier(scenarios, "core")
    assert {scenario.id for scenario in core} == {"credential-rotation", "sigterm-diagnosis"}


def test_select_tier_preserves_declared_run_order() -> None:
    scenarios = load_scenarios(SCENARIO_ROOT)
    smoke = select_tier(scenarios, "smoke")
    assert [scenario.run_order for scenario in smoke] == sorted(
        scenario.run_order for scenario in smoke
    )


def test_select_tier_rejects_an_unknown_tier() -> None:
    scenarios = load_scenarios(SCENARIO_ROOT)
    with pytest.raises(ScenarioError):
        select_tier(scenarios, "full")


def test_a_tier_that_matches_no_scenario_is_an_error_not_an_empty_clean_run() -> None:
    """An empty selection would produce a tier result that examined nothing.

    The harness already refuses to treat a tier that examined no scenario as
    evidence of a clean run; selection fails closed for the same reason.
    """

    scenarios = select_tier(load_scenarios(SCENARIO_ROOT), "core")
    with pytest.raises(ScenarioError):
        select_tier(scenarios, "smoke")

"""Guard tests for strict, package-only scenario declarations."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest
import yaml

from dp_scenarios import followups
from dp_scenarios.grading import GATE_PHASES
from dp_scenarios.scenario import (
    SCENARIO_TIERS,
    ScenarioError,
    load_scenario,
    load_scenarios,
    requires_live_session,
    select_tier,
)
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




# The tier each shipped scenario belongs to. Deliberately explicit: this is the
# one thing about a scenario package that must not change by accident, so it is
# stated here rather than derived from the package that would be doing the
# changing. See test_select_tier_returns_only_the_scenarios_declaring_that_tier.
EXPECTED_TIERS = {
    "zero-row-optional-output": "smoke",
    "parent-child-grain-trap": "smoke",
    "credential-rotation": "core",
    "sigterm-diagnosis": "core",
    "restart-and-switch": "core",
    "capability-shortfall": "live",
    "crm-pipeline": "core",
    "finance-close": "core",
    "inventory-position": "core",
}

_BASE_REQUIRED_GATES = set(GATE_PHASES) - {"capability", "narrowing"}
EXPECTED_REQUIRED_GATES = {
    scenario_id: _BASE_REQUIRED_GATES
    | ({"capability"} if scenario_id in {"capability-shortfall", "crm-pipeline"} else set())
    for scenario_id in EXPECTED_TIERS
}
GATES_WITHOUT_A_STAGING_SCENARIO = {"narrowing"}


def _packages_on_disk() -> set[str]:
    """Every scenario package directory that declares a scenario.yaml.

    Derived rather than enumerated: a hardcoded list of scenario ids is one
    shared edit point per new scenario, which is exactly what makes two
    scenarios authored in parallel conflict over a file they otherwise do not
    share. The property worth asserting is that discovery finds what is on
    disk, not that it finds a list someone remembered to update.
    """

    return {
        package.name
        for package in SCENARIO_ROOT.iterdir()
        if package.is_dir()
        and not package.name.startswith("_")
        and (package / "scenario.yaml").is_file()
    }


def _copy_zero_row_package(tmp_path: Path) -> Path:
    root = tmp_path / "scenarios"
    root.mkdir()
    shutil.copytree(SCENARIO_ROOT / "zero-row-optional-output", root / "zero-row-optional-output")
    (root / "_personas").mkdir()
    shutil.copy2(SCENARIO_ROOT / "_personas/smoke.yaml", root / "_personas/smoke.yaml")
    return root / "zero-row-optional-output"


def test_both_scenario_packages_load_and_resolve_their_declared_references(tmp_path: Path) -> None:
    compared: list[str] = []
    scenarios = load_scenarios(SCENARIO_ROOT)
    assert {scenario.id for scenario in scenarios} == _packages_on_disk()
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
        # Derived, not enumerated: a per-kind list here is one more shared
        # edit per scenario, which is what the followups registry removed.
        assert followups.is_registered(scenario.gates["follow-up"].kind)
        generated = scenario.generate_fixture(tmp_path / scenario.id)
        for name, path in scenario.gold.items():
            assert path.is_file()
        if not followups.get(scenario.gates["follow-up"].kind).gold_reproducible_from_fixture:
            # This kind's gold records something the CSV generator does not
            # produce -- live Postgres facts, or declared runtime constants --
            # so it cannot be compared byte-for-byte against a regenerated
            # fixture. Its counts are reconciled against independently
            # recounted evidence in the kind's own test module, and the fields
            # it duplicates from scenario.yaml are checked by
            # test_gold_never_disagrees_with_the_declaration_it_duplicates.
            continue
        for name, path in scenario.gold.items():
            generated_path = scenario.gold_path(name, generated.out_dir)
            assert generated_path.is_file()
            assert generated_path.read_bytes() == path.read_bytes()
            compared.append(f"{scenario.id}:{name}")

    # The opt-out above is a `continue`, so it can swallow the byte comparison
    # entirely. Asserting the exact set rather than truthiness: a single kind
    # opting out wrongly drops its artifacts from this list while leaving a
    # non-empty one behind, which a truthiness check would not notice.
    expected_comparisons = {
        f"{scenario.id}:{name}"
        for scenario in scenarios
        if followups.get(scenario.gates["follow-up"].kind).gold_reproducible_from_fixture
        for name in scenario.gold
    }
    assert set(compared) == expected_comparisons
    assert expected_comparisons, "no scenario's gold was compared against a regenerated fixture"


def test_public_scenarios_declare_the_expected_required_gate_set() -> None:
    scenarios = load_scenarios(SCENARIO_ROOT)

    for scenario in scenarios:
        expected = EXPECTED_REQUIRED_GATES[scenario.id]
        declared = set(GATE_PHASES)
        if not scenario.stages_capability_shortfall:
            declared.remove("capability")
        if not scenario.stages_definition_change:
            declared.remove("narrowing")
        assert declared == expected
        assert scenario.stages_definition_change is False

    staged_capability = {
        scenario.id for scenario in scenarios if scenario.stages_capability_shortfall
    }
    assert staged_capability == {"capability-shortfall", "crm-pipeline"}


def test_every_gate_has_a_public_staging_scenario_or_an_explicit_follow_up_allowlist() -> None:
    scenarios = load_scenarios(SCENARIO_ROOT)
    # Read the predicates the tier actually consults, not the expectation
    # table above: deriving both sides from the same constant made this pass
    # against an implementation that had no predicates at all.
    required_by_public_scenario = set(_BASE_REQUIRED_GATES)
    for scenario in scenarios:
        if scenario.stages_capability_shortfall:
            required_by_public_scenario.add("capability")
        if scenario.stages_definition_change:
            required_by_public_scenario.add("narrowing")
    missing = set(GATE_PHASES) - required_by_public_scenario
    # No public scenario declares a mid-run definition change yet. Keep this
    # named until the future narrowing-staging follow-up adds one.
    assert missing == GATES_WITHOUT_A_STAGING_SCENARIO


def test_definition_change_gate_setting_is_a_declaration_seam(tmp_path: Path) -> None:
    package = _copy_parent_child_package(tmp_path)
    declaration = package / "scenario.yaml"
    source = yaml.safe_load(declaration.read_text(encoding="utf-8"))
    source["gates"]["narrowing"] = {
        "kind": "narrowing",
        "definition_change": {
            "trigger_turn": 3,
            "changed_metrics": ["regional_revenue"],
        },
    }
    declaration.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    scenario = load_scenario(package)

    assert scenario.stages_definition_change


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
    direct = sorted(
        (load_scenario(SCENARIO_ROOT / name) for name in _packages_on_disk()),
        key=lambda scenario: scenario.run_order,
    )
    assert [item.id for item in discovered] == [item.id for item in direct]


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
    shutil.rmtree(root / "restart-and-switch")
    shutil.rmtree(root / "capability-shortfall")
    shutil.rmtree(root / "crm-pipeline")
    shutil.rmtree(root / "finance-close")
    shutil.rmtree(root / "inventory-position")
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
    shutil.rmtree(root / "restart-and-switch")
    shutil.rmtree(root / "capability-shortfall")
    shutil.rmtree(root / "crm-pipeline")
    shutil.rmtree(root / "finance-close")
    shutil.rmtree(root / "inventory-position")
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
    assert {scenario.id for scenario in scenarios} == _packages_on_disk()

    smoke = select_tier(scenarios, "smoke")
    core = select_tier(scenarios, "core")
    live = select_tier(scenarios, "live")

    # Which tier a scenario belongs to is pinned, not merely partitioned.
    # A partition assertion is satisfied by a scenario silently migrating
    # between tiers, and that migration is exactly the defect this suite
    # cares about: a smoke scenario drifting to core stops running on every
    # change, and a core scenario drifting to smoke pulls a Docker Postgres
    # into the tier that has to stay cheap. Adding a scenario means adding a
    # line here on purpose -- the set assertion below fails until you do.
    assert EXPECTED_TIERS.keys() == _packages_on_disk()
    assert {scenario.id: scenario.tier for scenario in scenarios} == EXPECTED_TIERS

    smoke_ids = {scenario.id for scenario in smoke}
    core_ids = {scenario.id for scenario in core}
    live_ids = {scenario.id for scenario in live}
    assert smoke_ids.isdisjoint(core_ids)
    assert smoke_ids.isdisjoint(live_ids)
    assert core_ids.isdisjoint(live_ids)
    assert {scenario.id for scenario in (*smoke, *core, *live)} == _packages_on_disk()
    assert smoke and core and live

    # What select_tier itself returns, pinned against EXPECTED_TIERS rather
    # than against the loader. EXPECTED_TIERS pins what load_scenarios
    # reports; without this, inverting select_tier's own predicate -- so
    # --tier smoke runs the core scenarios and vice versa -- satisfies every
    # assertion above, because the two sets merely swap.
    for tier in ("smoke", "core", "live"):
        expected = {name for name, declared in EXPECTED_TIERS.items() if declared == tier}
        assert {scenario.id for scenario in select_tier(scenarios, tier)} == expected
        assert all(scenario.tier == tier for scenario in select_tier(scenarios, tier))


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


def test_gold_never_disagrees_with_the_declaration_it_duplicates() -> None:
    """A gold artifact that restates scenario.yaml must restate it correctly.

    Several gold files carry a second copy of facts the declaration already
    owns -- the dataset and seed the fixture was generated from, and (for
    sigterm-diagnosis) the true cause and declared filter the follow-up
    settings define. The handler reads those from the settings, never from the
    gold, so an unchecked copy can drift out of agreement and mislead the next
    reader without failing anything.
    """

    checked: list[str] = []
    for scenario in load_scenarios(SCENARIO_ROOT):
        settings = scenario.gates["follow-up"].settings
        for name in scenario.gold:
            document = scenario.raw_gold(name)
            if not isinstance(document, dict):
                continue
            if "dataset" in document:
                assert document["dataset"] == scenario.dataset, f"{scenario.id}:{name} dataset"
                checked.append(f"{scenario.id}:{name}:dataset")
            if "seed" in document:
                assert document["seed"] == scenario.seed, f"{scenario.id}:{name} seed"
                checked.append(f"{scenario.id}:{name}:seed")
            for key, declared in settings.items():
                if key in document and isinstance(declared, (str, int, float, bool)):
                    assert document[key] == declared, f"{scenario.id}:{name} {key}"
                    checked.append(f"{scenario.id}:{name}:{key}")

    # Guard the loop itself: if no gold duplicated anything, this test would
    # pass while asserting nothing at all.
    assert checked, "no gold artifact duplicated a declared field"


def test_select_tier_treats_the_legacy_t0_spelling_as_smoke(tmp_path: Path) -> None:
    """T0 is documented as smoke's alias and the loader still accepts it.

    Matching the literal string would omit a T0 package from a smoke run
    rather than reject it, and select_tier only raises when *nothing* matches
    -- so the omission would never surface. A package quietly dropped from the
    tier that runs on every change is the same defect as one wrongly added.
    """

    root = tmp_path / "scenarios"
    shutil.copytree(SCENARIO_ROOT, root)
    smoke_package = next(
        path
        for path in root.iterdir()
        if path.is_dir()
        and not path.name.startswith("_")
        and (path / "scenario.yaml").is_file()
        and yaml.safe_load((path / "scenario.yaml").read_text(encoding="utf-8"))["tier"] == "smoke"
    )
    declaration = yaml.safe_load((smoke_package / "scenario.yaml").read_text(encoding="utf-8"))
    declaration["tier"] = "T0"
    (smoke_package / "scenario.yaml").write_text(yaml.safe_dump(declaration), encoding="utf-8")

    scenarios = load_scenarios(root)
    smoke_ids = {scenario.id for scenario in select_tier(scenarios, "smoke")}
    assert smoke_package.name in smoke_ids, "a T0 package was dropped from the smoke tier"
    # And the alias resolves in both directions.
    assert {scenario.id for scenario in select_tier(scenarios, "T0")} == smoke_ids


def test_live_is_the_only_tier_that_cannot_be_replayed() -> None:
    """Pin the live-only set against every declared tier, not against itself.

    ``requires_live_session`` decides whether the deterministic CLI refuses a
    replay run. Asserting only that ``"live"`` is live-only would let the
    predicate widen to every tier -- which would refuse every existing replay
    run -- without failing here.
    """

    live_only = {tier for tier in SCENARIO_TIERS if requires_live_session(tier)}
    assert live_only == {"live"}
    assert not requires_live_session("T0"), "the legacy smoke spelling is replayable"


def test_capability_shortfall_is_the_first_package_to_declare_the_live_tier() -> None:
    # The live tier existed before any package used it (b6acc702); this pins
    # capability-shortfall as the first, and only, package that does. A
    # second scenario silently added to "live" is a real change and should
    # fail this until EXPECTED_TIERS is updated on purpose.
    live_ids = {name for name, tier in EXPECTED_TIERS.items() if tier == "live"}
    assert live_ids == {"capability-shortfall"}
    selected = select_tier(load_scenarios(ROOT / "scenarios"), "live")
    assert {scenario.id for scenario in selected} == live_ids

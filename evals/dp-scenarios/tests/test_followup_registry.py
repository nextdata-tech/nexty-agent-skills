"""The follow-up registry is what makes a scenario package additive.

Each scenario used to need four edits to ``scenario.py``: a dispatch branch,
a gold-keys table entry, a certification-gold entry, and a settings-validation
branch. Two scenarios written at the same time conflicted over that file even
when they shared no behaviour. These tests hold the properties that replace
those four edits -- and, deliberately, that a kind which fails to register is
loud rather than silently ungraded.
"""

from __future__ import annotations

import pkgutil
from pathlib import Path

import pytest

from dp_scenarios import followups, support
from dp_scenarios.followups import FollowUpContext, FollowUpError, FollowUpKind, register
from dp_scenarios.scenario import ScenarioError, load_scenarios

SCENARIO_ROOT = Path(__file__).resolve().parents[1] / "scenarios"


# Which loader-time cross-checks each kind declares, as
# (validate_plant_evidence, validate_fixture_gold). Recorded explicitly so a
# new kind opting out of both is a visible line in review rather than a silent
# default -- see FollowUpKind's field comment.
EXPECTED_CROSS_CHECKS = {
    "grain_and_aggregation": (False, False),
    "credential_rotation": (False, False),
    "sigterm_diagnosis": (False, False),
    "optional_required_outputs": (True, True),
}



def test_every_shipped_scenario_resolves_its_follow_up_kind_through_the_registry() -> None:
    # ``_parse_gold`` already rejects a package whose gold keys differ from its
    # kind's, so asserting that agreement here would only restate the loader.
    # What is worth pinning is that every shipped kind resolves at all, and
    # that each one states its loader-time cross-checks explicitly -- a kind
    # silently opting out of both is how an ungraded gold artifact shipped.
    for scenario in load_scenarios(SCENARIO_ROOT):
        kind = followups.get(scenario.gates["follow-up"].kind)
        assert kind.name in EXPECTED_CROSS_CHECKS, f"{kind.name} declares no recorded intent"
        declared = (
            kind.validate_plant_evidence is not None,
            kind.validate_fixture_gold is not None,
        )
        assert declared == EXPECTED_CROSS_CHECKS[kind.name]


def test_discovery_imports_every_kind_module_beside_the_registry() -> None:
    """Auto-discovery is the whole point: a new module needs no shared edit."""

    modules = {
        module.name
        for module in pkgutil.iter_modules(followups.__path__)
        if not module.name.startswith("_")
    }
    assert modules, "no follow-up kind modules found"
    assert modules == followups.registered_names()


def test_a_duplicate_kind_name_is_rejected_rather_than_silently_overwriting() -> None:
    """Two packages sharing a name would mean the second decides how the
    first is graded."""

    existing = sorted(followups.registered_names())[0]
    original = followups._REGISTRY[existing]
    try:
        with pytest.raises(FollowUpError):
            register(
                FollowUpKind(
                    name=existing,
                    gold_keys=frozenset(),
                    handler=lambda *_args: {"status": "examined", "passed": True, "findings": []},
                )
            )
    finally:
        # If the guard ever regresses, the overwrite must not leak into every
        # later test in the session as an unrelated cascade of failures.
        followups._REGISTRY[existing] = original


def test_an_unregistered_kind_names_what_is_available() -> None:
    with pytest.raises(FollowUpError) as error:
        followups.get("not-a-real-kind")
    message = str(error.value)
    assert "not-a-real-kind" in message
    for name in followups.registered_names():
        assert name in message


def test_the_loader_rejects_a_scenario_declaring_an_unregistered_kind(tmp_path: Path) -> None:
    import shutil

    import yaml

    root = tmp_path / "scenarios"
    shutil.copytree(SCENARIO_ROOT, root)
    package = next(
        path
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith("_") and (path / "scenario.yaml").is_file()
    )
    declaration = yaml.safe_load((package / "scenario.yaml").read_text(encoding="utf-8"))
    declaration["gates"]["follow-up"] = {"kind": "no_such_kind"}
    (package / "scenario.yaml").write_text(yaml.safe_dump(declaration), encoding="utf-8")

    with pytest.raises(ScenarioError) as error:
        load_scenarios(root)
    assert "no_such_kind" in str(error.value)


def test_a_kind_module_that_fails_to_import_is_raised_by_the_real_discover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A swallowed import error leaves a scenario silently ungraded.

    This drives ``followups._discover`` itself. An earlier version of this test
    asserted against a hand-written copy of the discovery loop, so wrapping the
    real ``import_module`` call in ``except: pass`` left it passing -- a test
    holding its own narrative rather than the code's behaviour.
    """

    def explode(name: str) -> object:
        raise RuntimeError(f"kind module is broken: {name}")

    monkeypatch.setattr(followups.importlib, "import_module", explode)
    with pytest.raises(RuntimeError, match="kind module is broken"):
        followups._discover()


def test_discover_actually_imports_each_module_it_finds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The companion property: discovery must reach every module, so a kind
    that stops being imported is caught rather than quietly unregistered."""

    imported: list[str] = []
    monkeypatch.setattr(followups.importlib, "import_module", lambda name: imported.append(name))
    followups._discover()

    assert imported, "discovery imported nothing"
    assert {name.rsplit(".", 1)[-1] for name in imported} == followups.registered_names()


def test_context_defaults_do_not_conflate_an_absent_oracle_with_none() -> None:
    """``row_count_oracle`` distinguishes "not supplied" from a supplied
    ``None``; defaulting it to ``None`` would make an absent oracle look like
    a declared empty one."""

    context = FollowUpContext()
    assert context.row_count_oracle is support._MISSING
    assert context.fixture_dir is None

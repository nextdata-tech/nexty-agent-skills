"""The follow-up registry is what makes a scenario package additive.

Each scenario used to need four edits to ``scenario.py``: a dispatch branch,
a gold-keys table entry, a certification-gold entry, and a settings-validation
branch. Two scenarios written at the same time conflicted over that file even
when they shared no behaviour. These tests hold the properties that replace
those four edits -- and, deliberately, that a kind which fails to register is
loud rather than silently ungraded.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from dp_scenarios import followups
from dp_scenarios.followups import FollowUpContext, FollowUpError, FollowUpKind, register
from dp_scenarios.scenario import ScenarioError, load_scenarios

SCENARIO_ROOT = Path(__file__).resolve().parents[1] / "scenarios"


def test_every_shipped_scenario_resolves_its_follow_up_kind_through_the_registry() -> None:
    for scenario in load_scenarios(SCENARIO_ROOT):
        kind = followups.get(scenario.gates["follow-up"].kind)
        assert kind.name == scenario.gates["follow-up"].kind
        assert callable(kind.handler)
        # The gold the package declares is exactly the gold the kind requires,
        # so a declared-but-ungraded artifact cannot slip through the loader.
        assert set(scenario.gold) == set(kind.gold_keys)


def test_discovery_imports_every_kind_module_beside_the_registry() -> None:
    """Auto-discovery is the whole point: a new module needs no shared edit."""

    modules = {
        path.stem
        for path in (Path(followups.__file__).parent).glob("*.py")
        if not path.stem.startswith("_")
    }
    assert modules, "no follow-up kind modules found"
    assert modules <= followups.registered_names()


def test_a_duplicate_kind_name_is_rejected_rather_than_silently_overwriting() -> None:
    """Two packages sharing a name would mean the second decides how the
    first is graded."""

    existing = sorted(followups.registered_names())[0]
    with pytest.raises(FollowUpError):
        register(
            FollowUpKind(
                name=existing,
                gold_keys=frozenset(),
                handler=lambda *_args: {"status": "examined", "passed": True, "findings": []},
            )
        )


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


def test_a_kind_module_that_fails_to_import_is_raised_not_swallowed(tmp_path: Path) -> None:
    """A swallowed import error would leave a scenario silently ungraded.

    Rather than corrupt the real package, this drives ``_discover`` against a
    throwaway package laid out the same way.
    """

    package = tmp_path / "brokenfollowups"
    package.mkdir()
    (package / "__init__.py").write_text(
        textwrap.dedent(
            """
            import importlib
            import pkgutil
            from pathlib import Path


            def _discover() -> None:
                for module in pkgutil.iter_modules([str(Path(__file__).parent)]):
                    if module.name.startswith("_"):
                        continue
                    importlib.import_module(f"{__name__}.{module.name}")
            """
        ),
        encoding="utf-8",
    )
    (package / "broken.py").write_text("raise RuntimeError('kind module is broken')\n", encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    try:
        import importlib

        module = importlib.import_module("brokenfollowups")
        with pytest.raises(RuntimeError, match="kind module is broken"):
            module._discover()
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("brokenfollowups", None)
        sys.modules.pop("brokenfollowups.broken", None)


def test_context_defaults_do_not_conflate_an_absent_oracle_with_none() -> None:
    """``row_count_oracle`` distinguishes "not supplied" from a supplied
    ``None``; defaulting it to ``None`` would make an absent oracle look like
    a declared empty one."""

    context = FollowUpContext()
    assert context.row_count_oracle is not None
    assert context.fixture_dir is None

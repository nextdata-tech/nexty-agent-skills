"""Pin runner opt-in marker filenames to the files scenarios actually ship.

A marker is a *filename* agreed on by two sides that never reference each other:
``run.py`` names it in a ``*_RUNNER_SIDE_FIXTURES`` set and looks for it on disk,
and a scenario opts in by shipping a file with exactly that name. Nothing links
them, so renaming one side leaves no broken import and no failing assert — the
opt-in just silently stops resolving and every cell takes the no-runtime branch.

That is not hypothetical: renaming ``pocket.json`` to ``desktop.json`` in
``run.py`` without moving the six fixture files (PR #148) disabled the desktop
supervisor for every scenario that requested it, and the scenarios are
``ci_skip``'d so nothing caught it.

These tests assert the pairing in both directions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "evals" / "public"


def _run_module():
    evals_dir = ROOT / "evals"
    if str(evals_dir) not in sys.path:
        sys.path.insert(0, str(evals_dir))
    spec = importlib.util.spec_from_file_location("_eval_run", evals_dir / "run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_eval_run", module)
    spec.loader.exec_module(module)
    return module


run = _run_module()

# marker filename -> the resolver that reads it. Both sides must agree, or the
# opt-in silently disappears.
MARKER_RESOLVERS = {
    "desktop.json": run.scenario_needs_desktop,
    "desktop_stdio.json": run.scenario_needs_desktop_stdio,
    "mcp.json": run.scenario_needs_mcp,
    "http_stub.json": run.scenario_needs_http_stub,
}


def _scenarios():
    return sorted(d for d in PUBLIC.iterdir() if d.is_dir())


@pytest.mark.parametrize("marker", sorted(MARKER_RESOLVERS))
def test_marker_is_declared_runner_side(marker: str) -> None:
    """A marker must be withheld from the agent, or it leaks the opt-in."""
    declared = set()
    for name in dir(run):
        if name.endswith("_RUNNER_SIDE_FIXTURES") or name.endswith("_SERVER_SIDE_FIXTURES"):
            value = getattr(run, name)
            if isinstance(value, (set, frozenset)):
                declared |= value
    assert marker in declared, (
        f"{marker!r} is read by a resolver but appears in no *_RUNNER_SIDE_FIXTURES "
        f"set, so it would be copied into the agent's workspace"
    )


@pytest.mark.parametrize("marker", sorted(MARKER_RESOLVERS))
def test_every_marker_on_disk_resolves(marker: str) -> None:
    """A shipped marker file must be found by its resolver.

    Fails when the resolver's filename drifts from the files scenarios ship —
    the exact failure that disabled the desktop opt-in.
    """
    resolver = MARKER_RESOLVERS[marker]
    shipped = [d for d in _scenarios() if (d / "fixtures" / marker).exists()]
    unresolved = [d.name for d in shipped if resolver(d) is None]
    assert not unresolved, (
        f"{len(unresolved)} scenario(s) ship fixtures/{marker} but {resolver.__name__} "
        f"returns None for them: {unresolved}"
    )


def test_every_declared_runner_side_marker_is_resolvable() -> None:
    """Each ``*.json`` withheld from the agent as an opt-in marker has a resolver.

    ``run.py`` withholds a marker by listing it in a ``*_RUNNER_SIDE_FIXTURES``
    set, and consumes it through a resolver. Renaming one side and not the other
    leaves a marker that is withheld but never read — withholding is the part
    that still "works", so the file looks live while doing nothing.

    Non-marker entries (data fixtures, checkers, directories) are excluded by
    name; what remains must be resolvable.
    """
    # Withheld because they are ground truth the agent must not see — not opt-in
    # markers, so no resolver reads them.
    non_markers = {
        "seed.sql",
        "golden_pairs.json",
        "reference-closure",
        "build_data.py",
        "catalog.json",
        "semantic.json",
        "truth.json",
    }
    declared: set[str] = set()
    for name in dir(run):
        if name.endswith("_RUNNER_SIDE_FIXTURES") or name.endswith("_SERVER_SIDE_FIXTURES"):
            value = getattr(run, name)
            if isinstance(value, (set, frozenset)):
                declared |= value

    marker_like = {
        entry for entry in declared
        if entry.endswith(".json") and entry not in non_markers
    }
    unresolvable = sorted(marker_like - set(MARKER_RESOLVERS))
    assert not unresolvable, (
        "withheld from the agent as an opt-in marker but read by no resolver in "
        f"MARKER_RESOLVERS — a rename likely drifted the two sides apart: {unresolvable}"
    )


def test_no_scenario_is_left_behind_by_a_marker_rename() -> None:
    """Scenarios that opt into the same runtime agree on the marker filename.

    A partial rename is the dangerous shape: rename five of six marker files and
    the suite still resolves the runtime, ``test_desktop_opt_in_is_live`` still
    passes, and only the missed scenario silently grades without a supervisor.

    Sibling detection, no hardcoded old names: a scenario shipping
    ``reference-closure/`` or ``build_data.py`` — the fixtures that exist only to
    support a runtime cell — must also resolve a runtime marker.
    """
    stranded: list[str] = []
    for scenario in _scenarios():
        fixtures = scenario / "fixtures"
        if not fixtures.is_dir():
            continue
        runtime_shaped = (fixtures / "reference-closure").is_dir()
        if not runtime_shaped:
            continue
        if all(resolver(scenario) is None for resolver in MARKER_RESOLVERS.values()):
            stranded.append(scenario.name)
    assert not stranded, (
        "scenario ships a reference-closure (a runtime cell's fixture) but resolves "
        f"no opt-in marker — its marker file was likely missed by a rename: {stranded}"
    )


def test_desktop_opt_in_is_live() -> None:
    """At least one scenario resolves the desktop runtime.

    A blunt canary: if this reaches zero, the desktop path is off across the
    whole suite and every cell grades without a supervisor.
    """
    resolved = [d.name for d in _scenarios() if run.scenario_needs_desktop(d) is not None]
    assert resolved, (
        "no scenario resolves the desktop opt-in — fixtures/desktop.json is "
        "missing everywhere, or scenario_needs_desktop() looks for the wrong name"
    )

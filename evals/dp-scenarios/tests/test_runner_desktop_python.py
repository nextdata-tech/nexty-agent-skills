"""The desktop interpreter must stay the venv's own path, not its target.

A virtualenv's ``bin/python`` is a symlink to the base interpreter.  Handing
the supervisor the *resolved* path gives it the same executable running
outside the venv, so ``sys.prefix`` moves and the venv's site-packages
disappear.  That is not a theoretical difference: a live ``capability-shortfall``
run on 2026-09-03 spawned the resolved base interpreter, which lacked the
PyYAML the venv carried, and every closure failed to compile.  The build,
query, narrowing and capability gates all recorded ``not-examined``, so the
run looked like an agent that never got round to building rather than a
harness that had made building impossible.

These tests assert the property that failed -- the returned path still points
inside the venv, and an interpreter spawned from it still imports what the
venv installed -- rather than asserting the call the code makes.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from dp_scenarios.runner.tier import TierError

SCRIPT = Path(__file__).parents[1] / "scripts/run_local_claude.py"


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("dp_scenarios_run_local_claude", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_venv_interpreter_is_not_resolved_to_its_base(tmp_path: Path) -> None:
    """The returned path must remain the symlink, not what it points at."""

    venv_dir = tmp_path / "desktop-venv"
    venv.create(venv_dir, with_pip=False, symlinks=True)
    interpreter = venv_dir / "bin" / "python"
    if not interpreter.is_symlink():
        pytest.skip("this platform's venv does not symlink bin/python")

    returned = _load_runner_module().resolve_desktop_python(interpreter)

    assert returned == interpreter.absolute()
    assert returned.resolve() != returned, "the fixture no longer exercises a symlink"


def test_the_returned_interpreter_still_sees_the_venvs_site_packages(tmp_path: Path) -> None:
    """The property the resolve broke, checked by actually running it.

    A package importable through the venv path but not through the resolved
    base path is exactly the PyYAML situation that lost the live run.
    """

    venv_dir = tmp_path / "desktop-venv"
    venv.create(venv_dir, with_pip=False, symlinks=True)
    interpreter = venv_dir / "bin" / "python"
    if not interpreter.is_symlink():
        pytest.skip("this platform's venv does not symlink bin/python")

    site_packages = next(iter((venv_dir / "lib").glob("python*/site-packages")))
    (site_packages / "desktop_only_marker.py").write_text("VALUE = 'from-the-venv'\n")

    returned = _load_runner_module().resolve_desktop_python(interpreter)
    probe = "import desktop_only_marker; print(desktop_only_marker.VALUE)"

    completed = subprocess.run([str(returned), "-c", probe], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "from-the-venv"

    # The same probe through the resolved base interpreter must fail, or this
    # test would pass just as well against the bug it exists to catch.
    base = subprocess.run([str(interpreter.resolve()), "-c", probe], capture_output=True, text=True)
    assert base.returncode != 0, "the base interpreter can already import it; the fixture proves nothing"


def test_an_explicit_selection_wins_over_the_default(tmp_path: Path) -> None:
    interpreter = tmp_path / "python"
    interpreter.write_text("#!/bin/sh\n")
    interpreter.chmod(0o755)

    assert _load_runner_module().resolve_desktop_python(interpreter) == interpreter.absolute()


def test_a_relative_selection_is_made_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The supervisor is spawned elsewhere, so a relative path would not survive."""

    interpreter = tmp_path / "python"
    interpreter.write_text("#!/bin/sh\n")
    interpreter.chmod(0o755)
    monkeypatch.chdir(tmp_path)

    returned = _load_runner_module().resolve_desktop_python(Path("python"))

    assert returned.is_absolute()
    assert returned == interpreter.absolute()


def test_a_missing_or_non_executable_interpreter_is_rejected(tmp_path: Path) -> None:
    module = _load_runner_module()
    with pytest.raises(TierError, match="not executable"):
        module.resolve_desktop_python(tmp_path / "absent")

    plain = tmp_path / "not-executable"
    plain.write_text("")
    plain.chmod(0o644)
    with pytest.raises(TierError, match="not executable"):
        module.resolve_desktop_python(plain)


def test_the_default_points_at_the_desktop_venv() -> None:
    default = _load_runner_module()._default_desktop_python()
    assert default.parts[-3:] == ("desktop-venv", "bin", "python")

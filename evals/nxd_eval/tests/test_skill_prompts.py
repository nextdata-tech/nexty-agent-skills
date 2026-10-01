"""The prompts are rendered from skill files and packaged with the wheel."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from nxd_eval import skill_prompt
from nxd_eval.skill_prompts import PACKS, render_from_skills, skills_root
from nxd_eval.solver import CONFIDENCE_INSTRUCTION

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
SRC = REPO_ROOT / "src"


def _all_skills() -> tuple[str, ...]:
    return tuple(dict.fromkeys(skill for dirs in PACKS.values() for skill in dirs))


def _uv_executable() -> str | None:
    return shutil.which("uv")


def _expected_files(src_root: Path) -> dict[str, bytes]:
    # Tracked files only: hatchling skips caches like __pycache__ and .DS_Store
    # that a dev checkout may hold.
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", *_all_skills()],
        cwd=src_root,
        capture_output=True,
        check=True,
    ).stdout.decode().split("\0")
    return {rel: (src_root / rel).read_bytes() for rel in tracked if rel}


def test_prompt_renders_skill_sources_at_call_time():
    assert skills_root() == SRC
    assert skill_prompt() == render_from_skills(SRC)


def test_embedded_skills_take_precedence_over_repository_sources(tmp_path, monkeypatch):
    package_file = tmp_path / "repo/evals/nxd_eval/src/nxd_eval/skill_prompts/__init__.py"
    package_file.parent.mkdir(parents=True)
    package_file.touch()
    monkeypatch.setattr("nxd_eval.skill_prompts.__file__", str(package_file))

    embedded = tmp_path / "repo/evals/nxd_eval/src/nxd_eval/_skills"
    checkout = tmp_path / "repo/src"
    for skill in _all_skills():
        (embedded / skill).mkdir(parents=True)
        (checkout / skill).mkdir(parents=True)

    assert skills_root() == embedded


def test_skills_root_falls_back_to_checkout_for_an_incomplete_embedded_tree(tmp_path, monkeypatch):
    package_file = tmp_path / "repo/evals/nxd_eval/src/nxd_eval/skill_prompts/__init__.py"
    package_file.parent.mkdir(parents=True)
    package_file.touch()
    monkeypatch.setattr("nxd_eval.skill_prompts.__file__", str(package_file))

    embedded = package_file.parents[1] / "_skills"
    (embedded / _all_skills()[0]).mkdir(parents=True)
    checkout = package_file.parents[5] / "src"
    for skill in _all_skills():
        (checkout / skill).mkdir(parents=True)

    assert skills_root() == checkout


def test_skills_root_fails_clearly_when_neither_source_exists(tmp_path, monkeypatch):
    package_file = tmp_path / "repo/evals/nxd_eval/src/nxd_eval/skill_prompts/__init__.py"
    package_file.parent.mkdir(parents=True)
    package_file.touch()
    monkeypatch.setattr("nxd_eval.skill_prompts.__file__", str(package_file))

    with pytest.raises(FileNotFoundError, match="skill sources not found"):
        skills_root()


def test_wheel_force_include_mapping_matches_pack_directories():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    wheel = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["force-include"] == {
        f"../../src/{skill}": f"nxd_eval/_skills/{skill}" for skill in _all_skills()
    }
    assert not (PROJECT_ROOT / "src/nxd_eval/_skills").exists()


def test_prompt_carries_the_query_procedure_and_intent_gate():
    prompt = skill_prompt()
    for needle in (
        "running non-interactively",
        "must appear as a filter in the selection",
        "compiled_sql applies each of those",
        "enumerate every constraint in the verbatim question",
        "Semantic-layer MCP ports",
        "Intent gate (REQUIRED before `run_semantic_query`)",
        "Catalog-aware critic",
        "Round-trip echo",
        "## Execution rule",
    ):
        assert needle in prompt
    assert prompt.rstrip().endswith(CONFIDENCE_INSTRUCTION)


def test_prompt_has_no_links_into_the_skill_tree():
    assert "](" not in skill_prompt()


def test_unknown_pack_is_rejected():
    with pytest.raises(ValueError, match="unknown pack"):
        skill_prompt("nexty-desktop")


def test_moved_heading_fails_rendering(tmp_path):
    for rel in (
        "nxd-query-data-product/SKILL.md",
        "nxd-semantic-query-intent/SKILL.md",
        "nxd-semantic-query-intent/reference/semantic-intent-validation.md",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("# renamed\n")
    with pytest.raises(ValueError, match="start marker not found"):
        render_from_skills(tmp_path)


@pytest.mark.skipif(_uv_executable() is None, reason="uv is required for the packaging integration test")
def test_wheel_embeds_complete_skill_trees_and_renders_without_the_repo(tmp_path):
    result = subprocess.run(
        [_uv_executable(), "build", "--wheel", "--out-dir", str(tmp_path / "dist"), str(PROJECT_ROOT)],
        text=True,
        capture_output=True,
        timeout=180,
    )
    assert result.returncode == 0, f"uv build failed:\n{result.stdout}\n{result.stderr}"
    wheel = next((tmp_path / "dist").glob("*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        wheel_files = {
            name.removeprefix("nxd_eval/_skills/"): archive.read(name)
            for name in archive.namelist()
            if name.startswith("nxd_eval/_skills/") and not name.endswith("/")
        }
        archive.extractall(tmp_path / "installed")
    assert wheel_files == _expected_files(SRC)

    # Import from the unpacked wheel in a directory outside the repository, so
    # only the embedded tree can satisfy skills_root().
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path / "installed")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from nxd_eval.skill_prompts import render_from_skills, skill_prompt, skills_root; "
            "assert skills_root().name == '_skills'; "
            "print(skill_prompt(), end='')",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, f"installed wheel prompt failed:\n{result.stdout}\n{result.stderr}"
    assert result.stdout == skill_prompt()

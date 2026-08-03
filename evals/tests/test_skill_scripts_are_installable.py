"""A script a skill tells the agent to run must survive installation.

Every install path copies ONLY `src/<skill>/` trees:

  * `scripts/install.sh --code`    -> `copy_skill_tree "$SRC_DIR/$s"`
  * `scripts/install.sh --desktop` -> `copy_skill_tree "$SRC_DIR/$s" "$cache/skills/$s"`
  * `build-skills.sh`              -> `cd "$skill_dir"; zip -qrD`
  * `.claude-plugin/plugin.json`   -> `"skills": "./src/"`

So a helper at the REPO ROOT `scripts/` ships to no install target. The pack
shipped `dp_diagnostics.py` and `validate_dp_spec.py` that way once: the agent
was told to run `lock write` and `record init`, the files were not on disk, and
self-check Phase C then hard-failed `closure.lock_missing` naming the same
missing script in its own remedy. Unit tests all passed, because they import
from the repo, not from an install.

The eval harness reproduces the same environment (it copies skill dirs into an
isolated workspace), so it cannot catch this either. Hence a plain pytest gate.

`self_check.py` is the deliberate exception and is asserted as such below: it is
copied INTO the closure and run from there, so it is delivered by the embedded
fence in `reference/self-check.md`, never by an installer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

# Delivered by embedding in a reference doc, not by an installer.
# `test_self_check_sync.py` keeps the fence and the file byte-identical.
DELIVERED_BY_EMBEDDING = {"self_check.py"}

HELPERS = ("dp_diagnostics.py", "validate_dp_spec.py")
VERSION_STAMP = ".nexty-plugin-version.json"
SCRIPT_PATH = re.compile(r"scripts/([\w-]+\.py)")
WORKED_SPEC = re.compile(r"^```markdown\n(.*?)^```", re.S | re.M)
BOOTSTRAP = re.compile(r"```bash\n(JOB_HELPER_DIR=.*?test -n \"\$JOB_HELPER_DIR\")\n```", re.S)


def _skill_docs() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.md") if p.is_file())


def test_every_referenced_script_ships_inside_a_skill_tree():
    """Every helper named by a skill document survives an install."""
    installable = {p.name for p in SRC.rglob("scripts/*.py")}
    missing: dict[str, list[str]] = {}
    for doc in _skill_docs():
        names = set(SCRIPT_PATH.findall(doc.read_text(encoding="utf-8")))
        unavailable = names - installable - DELIVERED_BY_EMBEDDING
        if unavailable:
            missing[str(doc.relative_to(SRC))] = sorted(unavailable)
    assert not missing, (
        "these scripts are invoked by skill docs but ship to no install target "
        f"(not under any src/<skill>/scripts/): {missing}"
    )


def test_the_two_spec_scripts_live_in_the_job_loop_skill():
    """Pin the home explicitly — a silent move back to the root is the bug."""
    home = SRC / "nxd-run-job-loop" / "scripts"
    for name in ("dp_diagnostics.py", "validate_dp_spec.py"):
        assert (home / name).is_file(), f"{name} must ship at src/nxd-run-job-loop/scripts/"
        assert not (REPO / "scripts" / name).exists(), (
            f"{name} is back at the repo root, where no installer copies it"
        )


@pytest.mark.parametrize("name", sorted(DELIVERED_BY_EMBEDDING))
def test_the_embedded_exception_is_real(name):
    """`self_check.py` is exempt only because a fence actually carries it."""
    assert (REPO / "scripts" / name).is_file()
    fence = (SRC / "nxd-generate-data-product" / "reference" / "self-check.md").read_text(encoding="utf-8")
    assert f"# {name}" in fence, (
        f"{name} is exempted from the install rule because it is embedded in "
        "reference/self-check.md. That fence is gone, so the exemption is now a hole."
    )


def test_a_cross_skill_call_names_the_owning_skill():
    """No skill may resolve these helpers from its workflow or closure cwd."""
    offenders = []
    for doc in _skill_docs():
        rel = doc.relative_to(SRC)
        for line_no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if "python3" in line and any(name in line and "scripts/" in line for name in HELPERS):
                if "$JOB_HELPER_DIR/scripts/" not in line:
                    offenders.append(f"{rel}:{line_no}: {line.strip()}")
    assert not offenders, (
        "helper call sites must use the resolved JOB_HELPER_DIR path, not a path "
        f"relative to a repository, workflow, or closure: {offenders}"
    )


def test_generator_selective_install_names_its_job_loop_dependency():
    generator = (SRC / "nxd-generate-data-product" / "SKILL.md").read_text(encoding="utf-8")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "Selective-install dependency" in generator
    assert "selective install must include both skills" in generator
    assert "nxd-run-job-loop nxd-generate-data-product" in readme


def _assert_helpers_run(skill_dir: Path) -> None:
    """Assert both entrypoints run from a copied or extracted install tree."""
    scripts = skill_dir / "scripts"
    validator = scripts / "validate_dp_spec.py"
    diagnostics = scripts / "dp_diagnostics.py"
    assert validator.is_file()
    assert diagnostics.is_file()
    assert (scripts / "requirements.txt").read_text(encoding="utf-8") == "PyYAML>=6.0,<7\n"

    schema = subprocess.run(
        [sys.executable, str(diagnostics), "schema", "--json"],
        cwd=skill_dir.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(schema.stdout)["schema"] == "nxd-dp-spec-schema-v1"

    examples = WORKED_SPEC.findall(
        (SRC / "nxd-run-job-loop" / "reference" / "dp-spec.md").read_text(encoding="utf-8")
    )
    assert len(examples) == 1
    worked_spec = skill_dir.parent / "worked-dp-spec.md"
    worked_spec.write_text(examples[0], encoding="utf-8")
    report = subprocess.run(
        [sys.executable, str(validator), str(worked_spec), "--json"],
        cwd=skill_dir.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(report.stdout)
    assert payload["tool"] == "validate_dp_spec"
    assert payload["ok"] is True
    assert payload["counts"]["error"] == 0


def _lock_plugin_version(skill_dir: Path) -> str:
    """Exercise the installed diagnostic script, not the source import."""
    spec = skill_dir.parent / "approved-dp-spec.md"
    spec.write_text(
        "---\ndp_spec_version: 1\nname: install_test\nworkflow: install-test\n"
        "status: approved\n---\n\n## intent\n\nInstalled helper version test.\n",
        encoding="utf-8",
    )
    closure = skill_dir.parent / "closure"
    result = subprocess.run(
        [sys.executable, str(skill_dir / "scripts" / "dp_diagnostics.py"), "lock", "write",
         str(spec), str(closure), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["compiler_version"]["plugin"]


def _bootstrap_resolves(home: Path, cwd: Path) -> Path:
    """Run the documented resolver, not a reimplementation of it."""
    text = (SRC / "nxd-run-job-loop" / "reference" / "scripts-bootstrap.md").read_text()
    match = BOOTSTRAP.search(text)
    assert match, "scripts-bootstrap.md must retain one executable resolver block"
    env = os.environ | {"HOME": str(home)}
    result = subprocess.run(
        ["bash", "-c", match.group(1) + '\nprintf "%s\\n" "$JOB_HELPER_DIR"'],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def test_bootstrap_resolver_has_no_hardcoded_plugin_version():
    text = (SRC / "nxd-run-job-loop" / "reference" / "scripts-bootstrap.md").read_text()
    assert not re.search(r"version\s*=\s*['\"]\d+\.\d+\.\d+['\"]", text)
    assert "nexty-agent-skills/*/skills/nxd-run-job-loop" in text


def _install(target: str, home: Path, *args: str) -> None:
    env = os.environ | {"HOME": str(home)}
    if target == "desktop":
        # Exercise the macOS-only cache installer on every test platform.
        fake_bin = home / "bin"
        fake_bin.mkdir()
        uname = fake_bin / "uname"
        uname.write_text("#!/usr/bin/env sh\necho Darwin\n")
        uname.chmod(0o755)
        env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    subprocess.run(
        ["bash", "scripts/install.sh", f"--{target}", "--skills", "nxd-run-job-loop",
         "--no-validate", "--no-submodule", "--yes", *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def test_code_install_includes_and_invokes_desktop_helpers(tmp_path: Path):
    _install("code", tmp_path)
    skill_dir = tmp_path / ".claude" / "skills" / "nxd-run-job-loop"
    outside = tmp_path / "outside-code"
    outside.mkdir()
    assert _bootstrap_resolves(tmp_path, outside) == skill_dir.resolve()
    _assert_helpers_run(skill_dir)
    version = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())["version"]
    assert json.loads((skill_dir / VERSION_STAMP).read_text()) == {
        "name": "nexty-agent-skills", "version": version
    }
    assert _lock_plugin_version(skill_dir) == version


@pytest.mark.parametrize("layout", ("src/nxd-run-job-loop", "skills/nxd-run-job-loop"))
def test_claude_code_plugin_install_layout_resolves_desktop_helpers(
    tmp_path: Path, layout: str
):
    skill_dir = tmp_path / ".claude" / "plugins" / "nexty-agent-skills" / layout
    shutil.copytree(SRC / "nxd-run-job-loop", skill_dir)
    outside = tmp_path / "outside-plugin"
    outside.mkdir()

    assert _bootstrap_resolves(tmp_path, outside) == skill_dir.resolve()


def test_desktop_cache_install_includes_and_invokes_desktop_helpers(tmp_path: Path):
    account, device = "test-account", "test-device"
    support = tmp_path / "Library" / "Application Support" / "Claude"
    (support / "local-agent-mode-sessions" / account / device / "cowork_plugins").mkdir(parents=True)
    (support / "cowork-enabled-cli-ops.json").write_text(json.dumps({"ownerAccountId": account}))
    (support / "config.json").write_text(json.dumps({f"dxt:allowlistEnabled:{device}": True}))

    _install("desktop", tmp_path)
    version = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())["version"]
    cache = support / "local-agent-mode-sessions" / account / device / "cowork_plugins" / "cache"
    skill_dir = cache / "nexty" / "nexty-agent-skills" / version / "skills" / "nxd-run-job-loop"
    outside = tmp_path / "outside-cowork"
    outside.mkdir()
    assert _bootstrap_resolves(tmp_path, outside) == skill_dir.resolve()
    _assert_helpers_run(skill_dir)
    assert _lock_plugin_version(skill_dir) == version


def test_desktop_zip_includes_and_invokes_desktop_helpers(tmp_path: Path):
    subprocess.run(["bash", "build-skills.sh"], cwd=REPO, check=True, capture_output=True, text=True)
    archive = REPO / "build" / "nxd-run-job-loop.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        assert "scripts/dp_diagnostics.py" in zf.namelist()
        assert "scripts/validate_dp_spec.py" in zf.namelist()
        assert "scripts/requirements.txt" in zf.namelist()
        skill_dir = (
            tmp_path / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
            / "skills-plugin" / "test-account" / "test-device" / "test-session" / "skills" / "nxd-run-job-loop"
        )
        zf.extractall(skill_dir)
    outside = tmp_path / "outside-zip"
    outside.mkdir()
    assert _bootstrap_resolves(tmp_path, outside) == skill_dir.resolve()
    _assert_helpers_run(skill_dir)

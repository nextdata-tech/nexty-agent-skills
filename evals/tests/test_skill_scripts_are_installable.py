"""A script a skill tells the agent to run must survive installation.

Claude Code installs copy only `src/<skill>/` trees. Desktop/Cowork builds the
same trees into an uploadable plugin archive:

  * `scripts/install.sh --code`    -> `copy_skill_tree "$SRC_DIR/$s"`
  * `scripts/install.sh --desktop` -> `build-skills.sh` plus the whole-pack plugin ZIP
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

`self_check.py` ships like every other helper, inside the skill tree that owns
the resolver. It is still copied INTO the closure and run from there, but the
installer now delivers the exact file instead of relying on transcription.
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

HELPERS = (
    "dp_diagnostics.py",
    "validate_dp_spec.py",
    "dp_spec_authoring.py",
    "dp_spec_v2.py",
    "self_check.py",
)
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
        unavailable = names - installable
        if unavailable:
            missing[str(doc.relative_to(SRC))] = sorted(unavailable)
    assert not missing, (
        "these scripts are invoked by skill docs but ship to no install target "
        f"(not under any src/<skill>/scripts/): {missing}"
    )


def test_the_spec_scripts_live_in_the_job_loop_skill():
    """Pin the home explicitly — a silent move back to the root is the bug."""
    home = SRC / "nxd-run-job-loop" / "scripts"
    for name in HELPERS:
        assert (home / name).is_file(), f"{name} must ship at src/nxd-run-job-loop/scripts/"
        assert not (REPO / "scripts" / name).exists(), (
            f"{name} is back at the repo root, where no installer copies it"
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


def test_self_check_copy_names_the_owning_skill():
    """The copy source uses the installed helper path; the run stays closure-local.

    The guard deliberately does NOT also require ``scripts/`` on the line. That
    spelling only ever appears because the resolved path contains it, so
    demanding it would make this test self-selecting: a copy written as
    ``cp ../../self_check.py <closure>/`` — a relative reach out of the closure,
    which is the copy most likely to be wrong — would never enter the guard and
    would pass in silence.
    """
    offenders = []
    for doc in _skill_docs():
        rel = doc.relative_to(SRC)
        for line_no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if "cp " in line and "self_check.py" in line:
                if '"$JOB_HELPER_DIR/scripts/self_check.py"' not in line:
                    offenders.append(f"{rel}:{line_no}: {line.strip()}")
    assert not offenders, (
        "self_check.py copy sites must use the resolved JOB_HELPER_DIR path: "
        f"{offenders}"
    )


def test_generator_selective_install_names_its_job_loop_dependency():
    generator = (SRC / "nxd-generate-data-product" / "SKILL.md").read_text(encoding="utf-8")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "Selective-install dependency" in generator
    assert "selective install must include both skills" in generator
    assert "nxd-run-job-loop nxd-generate-data-product" in readme


def _assert_helpers_run(skill_dir: Path) -> None:
    """Assert the installed helper entrypoints are present and runnable."""
    scripts = skill_dir / "scripts"
    validator = scripts / "validate_dp_spec.py"
    diagnostics = scripts / "dp_diagnostics.py"
    self_check = scripts / "self_check.py"
    assert validator.is_file()
    assert diagnostics.is_file()
    assert self_check.is_file()
    assert (scripts / "dp_spec_authoring.py").is_file()
    assert (scripts / "requirements.txt").read_text(encoding="utf-8") == "PyYAML>=6.0,<7\n"

    schema = subprocess.run(
        [sys.executable, str(diagnostics), "schema", "--json"],
        cwd=skill_dir.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(schema.stdout)["schema"] == "nxd-dp-spec-schema-v2"

    examples = [
        (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8")
    ]
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
    example = [
        (REPO / "evals" / "tests" / "fixtures" / "dp-spec-v2-valid.md").read_text(encoding="utf-8")
    ]
    spec.write_text(example[0], encoding="utf-8")
    sys.path.insert(0, str(skill_dir / "scripts"))
    import dp_spec_v2  # noqa: PLC0415
    proposed = dp_spec_v2.parse(spec.read_text(encoding="utf-8"))
    spec.write_text(dp_spec_v2.approve(proposed, base_hash=dp_spec_v2.semantic_hash(proposed)), encoding="utf-8")
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
        # Exercise the Desktop branch on every test platform.
        fake_bin = home / "bin"
        fake_bin.mkdir()
        uname = fake_bin / "uname"
        uname.write_text("#!/usr/bin/env sh\necho Darwin\n")
        uname.chmod(0o755)
        env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    command = ["bash", "scripts/install.sh", f"--{target}"]
    if target == "code":
        command += ["--skills", "nxd-run-job-loop"]
    command += ["--no-validate", "--no-submodule", "--yes", *args]
    subprocess.run(
        command,
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _run_installer(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"HOME": str(home)}
    return subprocess.run(
        ["bash", "scripts/install.sh", *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )


def _snapshot_tree(root: Path) -> dict[str, tuple[bool, int, int, bytes | None]]:
    snapshot = {}
    for path in sorted(root.rglob("*")):
        stat = path.stat()
        snapshot[str(path.relative_to(root))] = (
            path.is_dir(),
            stat.st_mode,
            stat.st_mtime_ns,
            None if path.is_dir() else path.read_bytes(),
        )
    return snapshot


def _write_legacy_app_state(home: Path) -> tuple[Path, Path]:
    support = home / "Library" / "Application Support" / "Claude"
    first_pair = support / "local-agent-mode-sessions" / "account-a" / "device-a"
    first_cowork = first_pair / "cowork_plugins"
    cache = first_cowork / "cache" / "nexty" / "nexty-agent-skills" / "0.36.4"
    cache.mkdir(parents=True)
    (first_cowork / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"nexty-agent-skills@nexty": [{"version": "0.36.4"}]}}),
        encoding="utf-8",
    )
    (first_cowork / "known_marketplaces.json").write_text(
        json.dumps({"nexty": {"source": {"source": "github"}}}), encoding="utf-8"
    )
    (first_pair / "cowork_settings.json").write_text(
        json.dumps({"enabledPlugins": {"nexty-agent-skills@nexty": True}}),
        encoding="utf-8",
    )

    second_pair = support / "local-agent-mode-sessions" / "account-b" / "device-b"
    second_cache = second_pair / "cowork_plugins" / "cache" / "nexty" / "nexty-agent-skills" / "0.36.3"
    second_cache.mkdir(parents=True)

    malformed_pair = support / "local-agent-mode-sessions" / "account-c" / "device-c"
    malformed_cowork = malformed_pair / "cowork_plugins"
    malformed_cowork.mkdir(parents=True)
    (malformed_cowork / "installed_plugins.json").write_text("{not-json", encoding="utf-8")

    unrelated_pair = support / "local-agent-mode-sessions" / "account-d" / "device-d"
    unrelated_cowork = unrelated_pair / "cowork_plugins"
    unrelated_cowork.mkdir(parents=True)
    (unrelated_cowork / "installed_plugins.json").write_text(
        json.dumps({"plugins": {"other-plugin@other": [{"version": "1.0.0"}]}}),
        encoding="utf-8",
    )
    settings_only_pair = support / "local-agent-mode-sessions" / "account-e" / "device-e"
    settings_only_pair.mkdir(parents=True)
    (settings_only_pair / "cowork_settings.json").write_text(
        json.dumps({"enabledPlugins": {"nexty-agent-skills@nexty": True}}),
        encoding="utf-8",
    )
    malformed_shape_pair = support / "local-agent-mode-sessions" / "account-f" / "device-f"
    malformed_shape_cowork = malformed_shape_pair / "cowork_plugins"
    malformed_shape_cowork.mkdir(parents=True)
    (malformed_shape_pair / "cowork_settings.json").write_text(
        json.dumps({"enabledPlugins": None}), encoding="utf-8"
    )
    (malformed_shape_cowork / "installed_plugins.json").write_text(
        json.dumps({"plugins": None}), encoding="utf-8"
    )
    return support, cache


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


def test_desktop_install_builds_uploadable_plugin_pack(tmp_path: Path):
    _install("desktop", tmp_path)
    app_state = tmp_path / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
    assert not app_state.exists()
    version = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())["version"]
    archive = REPO / "build" / f"nexty-agent-skills-v{version}.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert ".claude-plugin/plugin.json" in names
        assert "skills/nxd-run-job-loop/SKILL.md" in names
        assert "skills/nxd-run-job-loop/scripts/dp_diagnostics.py" in names
        assert not any(name.endswith(".zip") for name in names)
        plugin = json.loads(zf.read(".claude-plugin/plugin.json"))
        assert "skills" not in plugin

        plugin_root = tmp_path / "uploaded-plugin"
        zf.extractall(plugin_root)
        skill_dir = plugin_root / "skills" / "nxd-run-job-loop"

    _assert_helpers_run(skill_dir)
    assert _lock_plugin_version(skill_dir) == version


@pytest.mark.parametrize("mount_prefix", (Path(), Path("mnt")))
def test_cowork_local_plugins_cache_resolves_desktop_helpers(
    tmp_path: Path, mount_prefix: Path
):
    """Cowork exposes .local-plugins/cache directly or beneath its mnt mount."""
    version = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())["version"]
    skill_dir = (
        tmp_path / mount_prefix / ".local-plugins" / "cache" / "nexty" / "nexty-agent-skills"
        / version / "skills" / "nxd-run-job-loop"
    )
    shutil.copytree(SRC / "nxd-run-job-loop", skill_dir)
    outside = tmp_path / f"outside-local-plugins-{mount_prefix or 'root'}"
    outside.mkdir()
    assert _bootstrap_resolves(tmp_path, outside) == skill_dir.resolve()
    _assert_helpers_run(skill_dir)


@pytest.mark.parametrize("mount_prefix", (Path(), Path("mnt")))
def test_cowork_local_plugins_cache_prefers_highest_semver(
    tmp_path: Path, mount_prefix: Path
):
    """A mounted cache may retain several versions after plugin upgrades."""
    cache = tmp_path / mount_prefix / ".local-plugins" / "cache" / "nexty" / "nexty-agent-skills"
    for version in ("0.9.0", "0.36.2", "0.10.0"):
        shutil.copytree(
            SRC / "nxd-run-job-loop",
            cache / version / "skills" / "nxd-run-job-loop",
        )
    outside = tmp_path / f"outside-versioned-cache-{mount_prefix or 'root'}"
    outside.mkdir()

    assert _bootstrap_resolves(tmp_path, outside) == (
        cache / "0.36.2" / "skills" / "nxd-run-job-loop"
    ).resolve()


def test_desktop_zip_includes_and_invokes_desktop_helpers(tmp_path: Path):
    subprocess.run(["bash", "build-skills.sh"], cwd=REPO, check=True, capture_output=True, text=True)
    archive = REPO / "build" / "nxd-run-job-loop.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        assert "scripts/dp_diagnostics.py" in zf.namelist()
        assert "scripts/validate_dp_spec.py" in zf.namelist()
        assert "scripts/self_check.py" in zf.namelist()
        assert "scripts/dp_spec_authoring.py" in zf.namelist()
        assert "scripts/requirements.txt" in zf.namelist()
        skill_dir = (
            tmp_path / ".claude" / "plugins" / "uploaded-plugin" / "skills" / "nxd-run-job-loop"
        )
        zf.extractall(skill_dir)
    outside = tmp_path / "outside-zip"
    outside.mkdir()
    assert _bootstrap_resolves(tmp_path, outside) == skill_dir.resolve()
    _assert_helpers_run(skill_dir)


@pytest.mark.parametrize(
    "target_args",
    (
        ("--desktop",),
        ("--cowork",),
        ("--all",),
        ("--code", "--desktop"),
    ),
)
def test_desktop_targets_reject_skill_filters_before_code_mutation(
    tmp_path: Path, target_args: tuple[str, ...]
):
    result = _run_installer(
        tmp_path,
        *target_args,
        "--skills",
        "nxd-run-job-loop",
        "--no-validate",
        "--no-submodule",
        "--yes",
    )
    assert result.returncode != 0
    assert "--skills is only supported for Claude Code" in result.stderr
    assert not (tmp_path / ".claude" / "skills").exists()


@pytest.mark.parametrize("subcommand", ("uninstall", "status"))
def test_desktop_skill_filter_rejection_also_precedes_code_action(
    tmp_path: Path, subcommand: str
):
    skill = tmp_path / ".claude" / "skills" / "nxd-run-job-loop"
    skill.mkdir(parents=True)
    (skill / "marker.txt").write_text("keep", encoding="utf-8")
    before = _snapshot_tree(tmp_path / ".claude")

    result = _run_installer(tmp_path, subcommand, "--all", "--skills", "nxd-run-job-loop")

    assert result.returncode != 0
    assert "--skills is only supported for Claude Code" in result.stderr
    assert _snapshot_tree(tmp_path / ".claude") == before


@pytest.mark.parametrize("skills_arg", ("", "   "))
def test_empty_skill_filter_is_still_rejected_for_desktop_targets(
    tmp_path: Path, skills_arg: str
):
    result = _run_installer(
        tmp_path,
        "--desktop",
        "--skills",
        skills_arg,
        "--no-validate",
        "--no-submodule",
    )
    assert result.returncode != 0
    assert "--skills is only supported for Claude Code" in result.stderr


@pytest.mark.parametrize("subcommand", ("install", "uninstall"))
@pytest.mark.parametrize("skills_arg", ("", "   "))
def test_empty_skill_filter_is_rejected_for_code_targets(
    tmp_path: Path, subcommand: str, skills_arg: str
):
    result = _run_installer(
        tmp_path,
        subcommand,
        "--code",
        "--skills",
        skills_arg,
        "--no-validate",
        "--no-submodule",
    )
    assert result.returncode != 0
    assert "--skills was given but named no skills" in result.stderr
    assert not (tmp_path / ".claude" / "skills").exists()


def test_old_bash_empty_arrays_are_guarded_before_expansion():
    installer = (REPO / "scripts" / "install.sh").read_text(encoding="utf-8")
    builder = (REPO / "build-skills.sh").read_text(encoding="utf-8")
    assert '[[ ${#SKILLS[@]} -gt 0 ]] || return 0' in installer
    assert 'if [[ -n "${TARGETS[0]+set}" ]]; then' in installer
    assert 'if [[ -n "${SKILL_ZIPS[0]+set}" ]]; then' in builder
    assert 'if [[ -n "${prune_args[0]+set}" ]]; then' in builder


def test_whole_pack_report_count_matches_archive_members():
    result = subprocess.run(
        ["bash", "build-skills.sh"], cwd=REPO, capture_output=True, text=True, check=True
    )
    version = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())["version"]
    archive = REPO / "build" / f"nexty-agent-skills-v{version}.zip"
    match = re.search(r"Plugin pack: .* \((\d+) files,", result.stdout)
    assert match, result.stdout
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        expected = sum(not item.is_dir() for item in members)
        assert len({item.filename for item in members}) == len(members)
    assert int(match.group(1)) == expected


@pytest.mark.parametrize("subcommand", ("status", "uninstall"))
def test_desktop_commands_report_legacy_app_state_without_mutation(
    tmp_path: Path, subcommand: str
):
    support, cache = _write_legacy_app_state(tmp_path)
    before = _snapshot_tree(support)

    result = _run_installer(tmp_path, subcommand, "--desktop")

    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert "Legacy-format Claude app-state evidence detected" in output
    assert "legacy-format installed_plugins registration" in output
    assert "legacy-format enabledPlugins registration" in output
    assert "legacy-format cache artifact" in output
    assert str(cache) in output
    assert "account-e/device-e/cowork_settings.json" in output
    assert "legacy-format unreadable installed_plugins.json" in output
    assert "account-f/device-f/cowork_settings.json" in output
    assert "account-f/device-f/cowork_plugins/installed_plugins.json" in output
    assert "left untouched" in output
    assert _snapshot_tree(support) == before

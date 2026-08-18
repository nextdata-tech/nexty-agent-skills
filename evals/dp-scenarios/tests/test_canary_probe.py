"""Supervisor discovery and command-protocol tests for the canary probe."""

from __future__ import annotations

from pathlib import Path
import subprocess
import json

import pytest

from dp_scenarios.canary import probe


def test_broken_supervisor_symlink_is_rejected_with_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    broken = tmp_path / "nxd-desktop-supervisor"
    broken.symlink_to(tmp_path / "deleted-supervisor")
    monkeypatch.setenv(probe.SUPERVISOR_ENV, str(broken))
    monkeypatch.setenv("PATH", "")

    with pytest.raises(probe.SupervisorNotFoundError, match="broken symlink"):
        probe.resolve_supervisor()


def test_create_always_receives_an_auto_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    closure = tmp_path / "closure"
    closure.mkdir()
    executable = closure / "supervisor"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    commands: list[list[str]] = []

    monkeypatch.setattr(probe, "resolve_supervisor", lambda explicit=None: executable)

    def fake_run(command, *, closure):
        commands.append(list(command))
        if command[1] == "check":
            report = {
                "outcome": "pass",
                "stages": [
                    {
                        "stage": stage,
                        "status": "pass",
                        "checks": [{"code": f"{stage}/ok", "status": "pass"}],
                    }
                    for stage in ("structure", "runtime", "contract", "semantic")
                ],
            }
            return subprocess.CompletedProcess(command, 0, __import__("json").dumps(report), "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)
    preflight, build = probe.run_probe_and_build(closure, supervisor=executable)

    assert len(commands) == 2
    check_dir = commands[0][commands[0].index("--data-dir") + 1]
    build_dir = commands[1][commands[1].index("--data-dir") + 1]
    assert check_dir == build_dir
    assert check_dir != str(closure)
    expected_digest = __import__("hashlib").sha256(executable.read_bytes()).hexdigest()
    assert preflight.supervisor_digest == expected_digest
    assert build is not None and build.supervisor_digest == expected_digest


def test_failed_build_reads_the_run_diagnostic_before_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closure = tmp_path / "closure"
    closure.mkdir()
    executable = closure / "supervisor"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    data_dir = tmp_path / "data"
    monkeypatch.setattr(probe, "resolve_supervisor", lambda explicit=None: executable)

    def fake_run(command, *, closure):
        run_data_dir = Path(command[command.index("--data-dir") + 1])
        diagnostic_dir = run_data_dir / "diagnostics" / "run-fixture"
        diagnostic_dir.mkdir(parents=True)
        (diagnostic_dir / "diagnostic.json").write_text(
            json.dumps(
                {
                    "run_id": "run-fixture",
                    "error": "transform failed",
                    "stderr": {"lines": ["KeyError: 'api_source'"]},
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 1, "", "create failed")

    monkeypatch.setattr(probe, "_run", fake_run)

    result = probe.run_build(closure, supervisor=executable, data_dir=data_dir)

    assert result.returncode == 1
    assert result.diagnostic is not None
    assert result.diagnostic["stderr"]["lines"] == ["KeyError: 'api_source'"]


def test_run_pins_provisioned_python_for_direct_supervisor_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    provisioned = home / ".nxd" / "desktop-venv" / "bin" / "python"
    provisioned.parent.mkdir(parents=True)
    provisioned.write_text("#!/bin/sh\n", encoding="utf-8")
    provisioned.chmod(0o755)
    captured: dict[str, object] = {}

    monkeypatch.setattr(probe.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv(probe.PYTHON_ENV, raising=False)

    def fake_subprocess_run(*args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(probe.subprocess, "run", fake_subprocess_run)
    probe._run(["supervisor", "check"], closure=tmp_path)

    assert captured["env"][probe.PYTHON_ENV] == str(provisioned)


def test_run_uses_only_the_session_allowlist_and_probes_the_installed_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "supervisor"
    executable.write_bytes(b"#!/bin/sh\nversion-a\n")
    executable.chmod(0o755)
    monkeypatch.setenv("HOME", "/outside/home")
    monkeypatch.setenv("PROVIDER_SECRET", "must-not-cross")
    captured: dict[str, object] = {}

    def fake_subprocess_run(*args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(probe.subprocess, "run", fake_subprocess_run)
    probe._run([str(executable), "check"], closure=tmp_path)

    environment = captured["env"]
    assert "PROVIDER_SECRET" not in environment
    assert "HOME" not in environment
    assert probe._supervisor_digest(executable) == __import__("hashlib").sha256(executable.read_bytes()).hexdigest()


def test_json_parser_accepts_wrapped_supervisor_output(tmp_path: Path) -> None:
    report = {"outcome": "pass", "stages": []}

    parsed = probe._parse_json(f"diagnostic prefix\n{json.dumps(report)}\n", closure=tmp_path)

    assert parsed == report


def test_report_shape_rejects_unknown_status(tmp_path: Path) -> None:
    report = {
        "outcome": "pass",
        "stages": [{"stage": "runtime", "status": "future", "checks": []}],
    }

    with pytest.raises(probe.ProbeError, match="unknown status"):
        probe._validate_report_shape(report, closure=tmp_path)

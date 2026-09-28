"""Mocked subprocess contract tests for the Codex CLI operator provider."""

from __future__ import annotations

import json
from pathlib import Path
import signal
import subprocess
from typing import Any

import pytest

from dp_scenarios.operator.driver import DriverBeat, DriverView
from dp_scenarios.operator.openai_driver import DriverConfigError, DriverProviderError
from dp_scenarios.operator import codex_driver
from dp_scenarios.operator.codex_driver import CodexDriverProvider, build_messages


def make_view(**overrides: Any) -> DriverView:
    base = dict(
        turn=4,
        phase=2,
        persona_id="ops-lead",
        persona_label="Head of Operations",
        persona_vocabulary=("shipments", "carrier"),
        persona_behaviors=("impatient",),
        agent_message="Which system holds the shipment records?",
        selected_reply="They live in the carrier portal.",
        prior_operator_messages=("We need a weekly shipment view.",),
        remaining_turns=6,
        prior_agent_messages=("Understood, starting now.",),
        known_facts=(("infra", "Everything is in the carrier portal, exported nightly."),),
        facts_already_stated=("volume",),
        beat=DriverBeat("card-1", ("carrier portal outage", "since Tuesday")),
        forbidden_terms=("late delivery rate",),
        rejection_notice=None,
    )
    base.update(overrides)
    return DriverView(**base)  # type: ignore[arg-type]


class FakeProcess:
    def __init__(self, command: list[str], kwargs: dict[str, object], *, code: int = 0) -> None:
        self.command = command
        self.kwargs = kwargs
        self.returncode = code
        self.communicate_calls: list[dict[str, object]] = []

    @property
    def pid(self) -> int:
        return 4321

    def communicate(self, input: str | None = None, timeout: float | None = None) -> tuple[None, None]:
        self.communicate_calls.append({"input": input, "timeout": timeout})
        if input is not None:
            cwd = Path(self.kwargs["cwd"])
            assert not list(cwd.iterdir()), "Codex must start in an empty temporary directory"
            output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            output_path.write_text("I need the carrier portal records.", encoding="utf-8")
        return None, None

    def wait(self, timeout: float | None = None) -> int:
        raise AssertionError("normal completion does not wait separately")

    def kill(self) -> None:
        self.returncode = -signal.SIGKILL


def test_invokes_codex_with_isolated_flags_prompt_and_minimal_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_driver.shutil, "which", lambda executable: "/fake/bin/codex")
    monkeypatch.setenv("PATH", "/safe/bin")
    monkeypatch.setenv("HOME", "/home/operator")
    monkeypatch.setenv("CODEX_HOME", "/home/operator/.codex")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("TMPDIR", "/tmp/should-not-pass")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret")

    seen: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        seen["command"] = command
        seen["kwargs"] = kwargs
        process = FakeProcess(command, kwargs)
        seen["process"] = process
        return process

    monkeypatch.setattr(codex_driver.subprocess, "Popen", fake_popen)
    provider = CodexDriverProvider(model="gpt-6-luna", effort="high", timeout_seconds=45)

    assert provider(make_view()) == "I need the carrier portal records."

    command = seen["command"]
    assert isinstance(command, list)
    assert command[:2] == ["/fake/bin/codex", "exec"]
    for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check"):
        assert flag in command
    disabled_features = (
        "hooks",
        "plugins",
        "apps",
        "browser_use",
        "in_app_browser",
        "computer_use",
        "image_generation",
        "view_image",
        "skill_search",
        "remote_plugin",
        "shell_tool",
        "unified_exec",
        "shell_snapshot",
        "code_mode_host",
        "web_search_request",
        "multi_agent",
    )
    actual_disabled_features = tuple(
        command[index + 1] for index, value in enumerate(command[:-1]) if value == "--disable"
    )
    assert actual_disabled_features == disabled_features
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--model") + 1] == "gpt-6-luna"
    assert command[command.index("--config") + 1] == 'model_reasoning_effort="high"'
    assert command[-1] == "-"

    kwargs = seen["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["cwd"] == Path(command[command.index("--cd") + 1])
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] == subprocess.PIPE
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL
    environment = kwargs["env"]
    assert isinstance(environment, dict)
    assert environment == {
        "PATH": "/safe/bin",
        "HOME": "/home/operator",
        "CODEX_HOME": "/home/operator/.codex",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    assert "OPENAI_API_KEY" not in environment
    assert "GITHUB_TOKEN" not in environment
    assert "TMPDIR" not in environment

    process = seen["process"]
    assert isinstance(process, FakeProcess)
    prompt = process.communicate_calls[0]["input"]
    assert isinstance(prompt, str)
    assert json.loads(prompt.split("\n\n", 1)[1]) == build_messages(make_view())


def test_constructor_preflights_codex_binary_before_a_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_driver.shutil, "which", lambda _executable: None)

    with pytest.raises(DriverConfigError, match="Codex CLI executable was not found"):
        CodexDriverProvider(model="gpt-6-luna")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"model": " "}, "driver model must be a non-empty string"),
        ({"model": "m", "effort": "extreme"}, "driver effort must be"),
        ({"model": "m", "timeout_seconds": 0}, "driver timeout_seconds must be positive"),
        ({"model": "m", "timeout_seconds": True}, "driver timeout_seconds must be positive"),
    ],
)
def test_constructor_validates_configuration(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, object], message: str
) -> None:
    monkeypatch.setattr(codex_driver.shutil, "which", lambda _executable: "/fake/bin/codex")
    with pytest.raises(DriverConfigError, match=message):
        CodexDriverProvider(**kwargs)  # type: ignore[arg-type]


def test_nonzero_exit_does_not_surface_cli_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_driver.shutil, "which", lambda _executable: "/fake/bin/codex")

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        process = FakeProcess(command, kwargs, code=9)
        process.communicate = lambda **_kwargs: (None, "Bearer secret-token")  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(codex_driver.subprocess, "Popen", fake_popen)
    provider = CodexDriverProvider(model="m")

    with pytest.raises(DriverProviderError, match="Codex CLI exited with status 9") as excinfo:
        provider(make_view())

    assert "secret-token" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


def test_empty_final_message_is_a_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_driver.shutil, "which", lambda _executable: "/fake/bin/codex")

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        process = FakeProcess(command, kwargs)

        def complete(input: str | None = None, timeout: float | None = None) -> tuple[None, None]:
            assert input is not None
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(" \n", encoding="utf-8")
            return None, None

        process.communicate = complete  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(codex_driver.subprocess, "Popen", fake_popen)
    with pytest.raises(DriverProviderError, match="Codex CLI returned no message"):
        CodexDriverProvider(model="m")(make_view())


def test_timeout_kills_the_dedicated_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_driver.shutil, "which", lambda _executable: "/fake/bin/codex")
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(codex_driver.os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    class TimedOutProcess(FakeProcess):
        def communicate(
            self, input: str | None = None, timeout: float | None = None
        ) -> tuple[None, None]:
            self.communicate_calls.append({"input": input, "timeout": timeout})
            if input is not None:
                raise subprocess.TimeoutExpired(self.command, timeout)
            self.returncode = -signal.SIGKILL
            return None, None

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(self.command, timeout)

    def fake_popen(command: list[str], **kwargs: object) -> TimedOutProcess:
        process = TimedOutProcess(command, kwargs)
        return process

    monkeypatch.setattr(codex_driver.subprocess, "Popen", fake_popen)
    provider = CodexDriverProvider(model="m", timeout_seconds=0.01)

    with pytest.raises(DriverProviderError, match="Codex CLI timed out after 0.01 seconds"):
        provider(make_view())

    assert signals == [(4321, signal.SIGTERM), (4321, signal.SIGKILL)]

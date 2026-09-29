"""Deterministic coverage for a terminal stdio session with a local HTTP stub."""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import shlex
import subprocess
import sys
import traceback
from types import SimpleNamespace
import urllib.error
import urllib.request
from pathlib import Path

import pytest

EVALS_DIR = Path(__file__).resolve().parents[1]
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

ds = importlib.import_module("desktop_stdio")
run = importlib.import_module("run")
eb = importlib.import_module("eval_backends")


SUPERVISOR_SCENARIO = (
    EVALS_DIR / "public" / "authenticated-api-source-supervisor"
)

FAKE_SERVER = r"""
import json, sys
for raw in sys.stdin:
    message = json.loads(raw)
    print(json.dumps({
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "result": {"authorization": "Bearer live-token", "echo": message.get("method")},
    }), flush=True)
"""


def _script(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _stdio_spec() -> dict:
    return {
        "server_name": "nxd-desktop",
        "profile_builder": "unused-profile-builder.py",
        "allowed_tools": ["mcp__nxd-desktop__*"],
    }


def test_nex_preflight_stream_summary_normalizes_names_and_preserves_order():
    events = [
        {"kind": "tool_use", "id": "task-1", "name": "Agent"},
        {
            "kind": "tool_use",
            "id": "reader-1",
            "name": "mcp__nxd-desktop__read_review_input",
            "parent_tool_use_id": "task-1",
            "input": {"path": "/private/secret/review-input"},
        },
        {"kind": "tool_result", "id": "reader-1", "is_error": False},
        {"kind": "tool_result", "id": "task-1", "is_error": False},
    ]

    summary = run._nex_preflight_stream_summary(events)

    assert summary == (
        "1:tool_use:Agent@root "
        "2:tool_use:read_review_input@child(task) "
        "3:tool_result:read_review_input:success "
        "4:tool_result:Agent:success"
    )
    assert "/private/secret/review-input" not in summary


def test_nex_canary_prompt_preserves_unmatched_quote_after_argv_sanitizing(tmp_path):
    base_prompt = run._build_nex_security_canary_prompt(
        inside_parent=tmp_path / "parent-inside.txt",
        shell_command="python3 -c " + shlex.quote("print('canary')"),
        source_root=tmp_path / "review-input",
        shared_attempts="Read the review input and report the result.\n",
        nonce="test-nonce",
        denial_lines=f"- outside: `{tmp_path / 'outside.txt'}`",
        shell_marker=tmp_path / "shell-ran.txt",
    )
    prompt = run._nex_canary_prompt_with_quote_probe(base_prompt)

    assert "canary's scope is fixed" in prompt
    for candidate in (prompt, eb.strip_argv_control_chars(prompt)):
        with pytest.raises(ValueError):
            shlex.split(" ".join(("claude", "-p", candidate)))
    with pytest.raises(RuntimeError, match="base canary prompt"):
        run._nex_canary_prompt_with_quote_probe('Run the canary with an "open quote.')


def test_nex_canary_prompt_names_skill_first_and_exact_write_contents(tmp_path):
    prompt = run._build_nex_security_canary_prompt(
        inside_parent=tmp_path / "parent-inside.txt",
        shell_command="python3 -c pass",
        source_root=tmp_path / "review-input",
        shared_attempts="child steps\n",
        nonce="test-nonce",
        denial_lines="- home_alias: `~/probe/home-alias-denied.txt`",
        shell_marker=tmp_path / "shell-ran.txt",
    )

    assert prompt.startswith(
        "First invoke the skill `nex890-preflight:nex890-canary` once with no arguments"
    )
    assert f"exact content `{run._NEX_PREFLIGHT_PARENT_MARKER}`" in prompt
    assert f"exact content `{run._NEX_PREFLIGHT_DENIED_CONTENT}`" in prompt
    assert "Write exactly once for each denied path" in prompt
    assert "never expand or rewrite it" in prompt
    assert "do not retry" in prompt
    assert run._NEX_PREFLIGHT_PARENT_MARKER != run._NEX_PREFLIGHT_CHILD_MARKER


# -- NEX-890 preflight pure helpers ---------------------------------------

_PREFLIGHT_HOOK_PATH = "/ws/.runner-private/nex-write-policy-hook.py"
# An independent copy of the runner-owned deny list; the runner constant and
# the session generator must both match it.
_PREFLIGHT_DENY_LITERAL = (
    "Bash", "BashOutput", "KillShell", "Monitor", "PowerShell",
    "Write(.claude/**)", "Edit(.claude/**)", "MultiEdit(.claude/**)",
    "NotebookEdit(.claude/**)", "Write(.mcp.json)", "Edit(.mcp.json)",
    "MultiEdit(.mcp.json)", "NotebookEdit(.mcp.json)",
)


def _preflight_expectation():
    denied = {label: f"/ws/denied/{label}.txt" for label in run._NEX_PREFLIGHT_LABELS}
    denied["home_alias"] = "~/.nex890-home-preflight-t/home-alias-denied.txt"
    return run._NexPreflightExpectation(
        denied_inputs=denied,
        inside_paths={"parent": "/ws/parent-inside.txt", "child": "/ws/child-inside.txt"},
        inside_markers={
            "parent": run._NEX_PREFLIGHT_PARENT_MARKER,
            "child": run._NEX_PREFLIGHT_CHILD_MARKER,
        },
        source_root="/ws/review-input",
        nonce="n0nce",
        hook_path=_PREFLIGHT_HOOK_PATH,
    )


def _hook_denial(reason):
    return f"PreToolUse:Write hook error: [python3 -I {_PREFLIGHT_HOOK_PATH}]: {reason}"


def _use(identifier, name, tool_input, parent=None):
    return {
        "kind": "tool_use", "id": identifier, "name": name,
        "input": tool_input, "parent_tool_use_id": parent,
    }


def _result(identifier, *, is_error=False, content="ok", truncated=False):
    return {
        "kind": "tool_result", "id": identifier, "malformed_id": False,
        "is_error": is_error, "content": content, "content_truncated": truncated,
    }


def _preflight_events():
    """A passing canary stream; each test breaks exactly one property."""
    expectation = _preflight_expectation()
    events = []

    def call(identifier, name, tool_input, parent=None, **result):
        events.extend([_use(identifier, name, tool_input, parent), _result(identifier, **result)])

    def writes(actor, parent):
        call(
            f"{actor}-inside", "Write",
            {
                "file_path": expectation.inside_paths[actor],
                "content": expectation.inside_markers[actor],
            },
            parent,
        )
        for label in run._NEX_PREFLIGHT_LABELS:
            reason = (
                run._NEX_PREFLIGHT_LITERAL_HOME_REASON if label == "home_alias"
                else run._NEX_PREFLIGHT_DIRECT_REASONS[label]
            )
            call(
                f"{actor}-{label}", "Write",
                {
                    "file_path": expectation.denied_inputs[label],
                    "content": run._NEX_PREFLIGHT_DENIED_CONTENT,
                },
                parent, is_error=True, content=_hook_denial(reason),
            )

    call("skill-1", "Skill", {"skill": run._NEX_PREFLIGHT_SKILL})
    writes("parent", None)
    call(
        "capture-1", "mcp__nxd-desktop__advance_workflow",
        {
            "workflow": "nex890-preflight",
            "authoring_root": expectation.source_root,
            "action": {"type": "capture"},
        },
    )
    events.append(_use("task-1", "Agent", {"prompt": "child", "run_in_background": False}))
    writes("child", "task-1")
    call(
        "reader-1", "mcp__nxd-desktop__read_review_input",
        {"operation": "list", "path": expectation.source_root}, "task-1",
    )
    events.append(_result("task-1"))
    call(
        "report-1", "mcp__nxd-desktop__advance_workflow",
        {
            "workflow": "nex890-preflight",
            "authoring_root": expectation.source_root,
            "action": {"type": "report_requirement", "requirement_id": "review"},
        },
    )
    call("probe-1", "mcp__nxd-desktop__preflight_probe", {"nonce": expectation.nonce})
    events.append({
        "kind": "result", "is_error": False, "subtype": "success",
        "permission_denials_present": True, "permission_denials": [],
    })
    return events


def _find(events, kind, identifier):
    return next(
        event for event in events
        if event["kind"] == kind and event.get("id") == identifier
    )


def _terminal(events):
    return next(event for event in events if event["kind"] == "result")


def _before_terminal(events, *added):
    index = events.index(_terminal(events))
    events[index:index] = list(added)


def _preflight_failures(events):
    return run._nex_preflight_stream_failures(events, _preflight_expectation())


def _cli_denial(events, identifier):
    use = _find(events, "tool_use", identifier)
    _terminal(events)["permission_denials"].append({
        "tool_name": use["name"], "tool_use_id": identifier, "tool_input": use["input"],
    })


def _cli_text(events, identifier, text="Permission to use Write has been denied."):
    _find(events, "tool_result", identifier)["content"] = text


def test_preflight_stream_accepts_the_exact_canary():
    assert _preflight_failures(_preflight_events()) == []


def test_preflight_failure_message_carries_only_sorted_categories():
    assert run._nex_preflight_failure(["write/count", "child/count", "write/count"]) == (
        False, "NEX-890 preflight failed closed: category=child/count,write/count"
    )


def test_preflight_reason_sets_are_shared_and_tilde_accepts_both_spellings():
    hook = run._nex_hook
    assert set(run._NEX_PREFLIGHT_DIRECT_REASONS) == set(run._NEX_PREFLIGHT_LABELS)
    assert set(run._NEX_PREFLIGHT_ACCEPTED_REASONS) == set(run._NEX_PREFLIGHT_LABELS)
    for label in run._NEX_PREFLIGHT_LABELS:
        if label != "home_alias":
            assert run._NEX_PREFLIGHT_ACCEPTED_REASONS[label] == {
                run._NEX_PREFLIGHT_DIRECT_REASONS[label]
            }
    assert run._NEX_PREFLIGHT_DIRECT_REASONS["home_alias"] == hook.REASON_WRITE_OUTSIDE
    assert run._NEX_PREFLIGHT_LITERAL_HOME_REASON == hook.REASON_HOME_RELATIVE
    assert run._NEX_PREFLIGHT_ACCEPTED_REASONS["home_alias"] == {
        hook.REASON_HOME_RELATIVE, hook.REASON_WRITE_OUTSIDE,
    }
    assert run._NEX_PREFLIGHT_CLI_FALLBACK_LABELS.isdisjoint({"private", "plugin"})

    for actor in ("parent", "child"):
        events = _preflight_events()
        _find(events, "tool_result", f"{actor}-home_alias")["content"] = _hook_denial(
            hook.REASON_WRITE_OUTSIDE
        )
        assert _preflight_failures(events) == []

    events = _preflight_events()
    _find(events, "tool_result", "parent-home_alias")["content"] = _hook_denial(
        hook.REASON_WRITE_PROTECTED
    )
    assert _preflight_failures(events) == ["denial/parent-home_alias-wrong-hook-reason"]

    events = _preflight_events()
    _find(events, "tool_result", "child-claude")["content"] = _hook_denial(
        hook.REASON_WRITE_CLAUDE + " BODY-SENTINEL " + hook.REASON_WRITE_MCP
    )
    failures = _preflight_failures(events)
    assert failures == ["denial/child-claude-wrong-hook-reason"]
    assert all("BODY-SENTINEL" not in failure for failure in failures)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda events: _find(events, "tool_use", "skill-1")["input"].update(args=""), []),
        (lambda events: _find(events, "tool_use", "skill-1")["input"].update(args="x"), ["skill/input"]),
        (lambda events: _find(events, "tool_use", "skill-1")["input"].update(args=None), ["skill/input"]),
        (
            lambda events: _find(events, "tool_use", "skill-1")["input"].update(skill="nex890-canary"),
            ["skill/input"],
        ),
        (
            lambda events: _find(events, "tool_use", "skill-1")["input"].update(extra=True),
            ["skill/input"],
        ),
        (lambda events: _find(events, "tool_result", "skill-1").update(is_error=True), ["skill/unsuccessful"]),
        (
            lambda events: _find(events, "tool_use", "skill-1").update(parent_tool_use_id="task-1"),
            ["skill/not-parent"],
        ),
        (
            lambda events: _before_terminal(
                events,
                _use("skill-2", "Skill", {"skill": run._NEX_PREFLIGHT_SKILL}),
                _result("skill-2"),
            ),
            ["skill/count"],
        ),
        (lambda events: events.__delitem__(slice(0, 2)), ["skill/count"]),
    ],
)
def test_preflight_requires_one_exact_parent_skill(mutate, expected):
    events = _preflight_events()
    mutate(events)
    assert _preflight_failures(events) == expected


def test_preflight_skill_must_precede_the_first_write():
    events = _preflight_events()
    skill_events = events[:2]
    del events[:2]
    index = events.index(_find(events, "tool_result", "parent-inside")) + 1
    events[index:index] = skill_events

    assert _preflight_failures(events) == ["skill/after-first-write"]


def test_preflight_counts_task_and_agent_together_as_one_child():
    task_only = _preflight_events()
    _find(task_only, "tool_use", "task-1")["name"] = "Task"
    assert _preflight_failures(task_only) == []

    both = _preflight_events()
    _before_terminal(
        both,
        _use("task-2", "Task", {"prompt": "again", "run_in_background": False}),
        _result("task-2"),
    )
    assert "child/count" in _preflight_failures(both)

    background = _preflight_events()
    _find(background, "tool_use", "task-1")["input"]["run_in_background"] = True
    assert _preflight_failures(background) == ["child/not-foreground"]

    failed = _preflight_events()
    _find(failed, "tool_result", "task-1")["is_error"] = True
    assert _preflight_failures(failed) == ["child/unsuccessful"]


def test_preflight_parent_cli_fallback_needs_its_own_exact_denial_id():
    events = _preflight_events()
    _cli_text(events, "parent-claude")
    _cli_denial(events, "parent-claude")
    assert _preflight_failures(events) == []

    empty = _preflight_events()
    _cli_text(empty, "parent-claude")
    assert _preflight_failures(empty) == ["denial/parent-claude-cli-denial-missing"]

    absent = _preflight_events()
    _cli_text(absent, "parent-claude")
    _terminal(absent).update(permission_denials_present=False, permission_denials=None)
    assert _preflight_failures(absent) == ["denial/parent-claude-cli-denials-absent"]

    # A missing field disables only the fallback; exact hook reasons still pass.
    hook_only = _preflight_events()
    _terminal(hook_only).update(permission_denials_present=False, permission_denials=None)
    assert _preflight_failures(hook_only) == []

    borrowed = _preflight_events()
    _cli_text(borrowed, "parent-claude")
    _cli_text(borrowed, "parent-mcp")
    _cli_denial(borrowed, "parent-mcp")
    assert _preflight_failures(borrowed) == ["denial/parent-claude-cli-denial-missing"]


@pytest.mark.parametrize("label", ["private", "plugin"])
def test_preflight_hook_only_labels_never_use_the_cli_fallback(label):
    events = _preflight_events()
    _cli_text(events, f"parent-{label}")
    _cli_denial(events, f"parent-{label}")
    assert _preflight_failures(events) == [f"denial/parent-{label}-hook-reason-missing"]


def test_preflight_child_fallback_is_anchored_to_the_same_label_parent_denial():
    def fallback_events():
        events = _preflight_events()
        _cli_text(events, "parent-claude")
        _cli_denial(events, "parent-claude")
        _cli_text(events, "child-claude")
        return events

    assert _preflight_failures(fallback_events()) == []

    own_id = fallback_events()
    _cli_denial(own_id, "child-claude")
    assert _preflight_failures(own_id) == []

    wrong_entry = fallback_events()
    _cli_denial(wrong_entry, "child-claude")
    _terminal(wrong_entry)["permission_denials"][-1]["tool_input"] = {
        "file_path": "/elsewhere", "content": "DENIED_CANARY",
    }
    assert _preflight_failures(wrong_entry) == [
        "denials/entry-mismatch-child-claude-file_path_other"
    ]

    parent_hook = _preflight_events()
    _cli_text(parent_hook, "child-claude")
    _cli_denial(parent_hook, "child-claude")
    assert _preflight_failures(parent_hook) == ["denial/child-claude-parent-denial-missing"]

    borrowed = _preflight_events()
    _cli_text(borrowed, "parent-mcp")
    _cli_denial(borrowed, "parent-mcp")
    _cli_text(borrowed, "child-claude")
    assert _preflight_failures(borrowed) == ["denial/child-claude-parent-denial-missing"]

    for text, category in (
        (f"denied by {_PREFLIGHT_HOOK_PATH}", "generic-hook-error"),
        ("PreToolUse hook error: blocked", "generic-hook-error"),
        (run._nex_hook.REASON_WRITE_OUTSIDE, "wrong-hook-reason"),
    ):
        events = fallback_events()
        _cli_text(events, "child-claude", text)
        assert _preflight_failures(events) == [f"denial/child-claude-{category}"]

    truncated = fallback_events()
    _find(truncated, "tool_result", "child-claude")["content_truncated"] = True
    assert _preflight_failures(truncated) == ["denial/child-claude-result-truncated"]

    not_error = fallback_events()
    _find(not_error, "tool_result", "child-claude")["is_error"] = False
    assert _preflight_failures(not_error) == ["denial/child-claude-write-succeeded"]


@pytest.mark.parametrize(
    "denials",
    ["bad", [{"tool_name": "Write"}], [{"tool_use_id": "parent-claude"}] * 2],
)
def test_preflight_malformed_permission_denials_fail_closed(denials):
    events = _preflight_events()
    _terminal(events)["permission_denials"] = denials
    assert "denials/malformed" in _preflight_failures(events)


def test_preflight_denial_ids_must_map_to_denied_writes():
    unknown = _preflight_events()
    _terminal(unknown)["permission_denials"].append({"tool_use_id": "ghost"})
    assert _preflight_failures(unknown) == ["denials/unmatched-id"]

    probe = _preflight_events()
    _cli_denial(probe, "probe-1")
    assert _preflight_failures(probe) == ["denials/unexpected-tool"]


_ENTRY_MISMATCH_IDS = frozenset(
    f"denials/entry-mismatch-{actor}-{label}-{mismatch}"
    for actor in run._NEX_PREFLIGHT_ACTORS
    for label in run._NEX_PREFLIGHT_LABELS
    for mismatch in run._NEX_PREFLIGHT_ENTRY_MISMATCH_CLASSES
)


class _NeverEqualInput(dict):
    """Same keys and values as the Write input, yet compares unequal."""

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return True


def _entry_mismatch_events(identifier):
    events = _preflight_events()
    _cli_text(events, identifier)
    _cli_denial(events, identifier)
    return events, _terminal(events)["permission_denials"][-1]


@pytest.mark.parametrize(
    ("identifier", "mutate", "expected"),
    [
        ("parent-claude", lambda entry: entry.update(tool_name="Edit"), ["tool_name"]),
        ("parent-claude", lambda entry: entry.update(tool_input="x"), ["input_shape"]),
        ("parent-claude", lambda entry: entry["tool_input"].pop("content"), ["input_shape"]),
        ("parent-claude", lambda entry: entry["tool_input"].update(extra=1), ["input_shape"]),
        ("parent-claude", lambda entry: entry["tool_input"].update(content=1), ["input_shape"]),
        ("parent-claude", lambda entry: entry["tool_input"].update(content="x"), ["content"]),
        (
            "parent-claude",
            lambda entry: entry["tool_input"].update(file_path="/elsewhere"),
            ["file_path_other"],
        ),
        (
            "parent-claude",
            lambda entry: entry["tool_input"].update(file_path="/ws/denied/./claude.txt"),
            ["file_path_normalized"],
        ),
        (
            "parent-home_alias",
            lambda entry: entry["tool_input"].update(
                file_path="/home/canary/.nex890-home-preflight-t/../home-alias-denied.txt"
            ),
            ["file_path_other"],
        ),
        (
            "parent-home_alias",
            lambda entry: entry["tool_input"].update(
                file_path="/home/canary/./.nex890-home-preflight-t/home-alias-denied.txt"
            ),
            ["file_path_normalized"],
        ),
        (
            "parent-mcp",
            lambda entry: entry.update(
                tool_name="write",
                tool_input={**entry["tool_input"], "file_path": "/x", "content": "x"},
            ),
            ["content", "file_path_other", "tool_name"],
        ),
        (
            "parent-claude",
            lambda entry: entry.update(tool_input=_NeverEqualInput(entry["tool_input"])),
            ["other"],
        ),
    ],
)
def test_preflight_denial_entry_mismatch_names_actor_label_and_class(
    monkeypatch, identifier, mutate, expected,
):
    monkeypatch.setenv("HOME", "/home/canary")
    events, entry = _entry_mismatch_events(identifier)
    entry["tool_input"] = dict(entry["tool_input"])  # never alias the Write input
    mutate(entry)
    actor, label = identifier.split("-", 1)
    assert _preflight_failures(events) == [
        f"denials/entry-mismatch-{actor}-{label}-{mismatch}" for mismatch in expected
    ]


def test_preflight_id_only_denial_entry_cannot_satisfy_the_cli_fallback():
    events = _preflight_events()
    _cli_text(events, "parent-claude")
    _terminal(events)["permission_denials"].append({"tool_use_id": "parent-claude"})
    failures = _preflight_failures(events)
    assert failures == [
        "denials/entry-mismatch-parent-claude-input_shape",
        "denials/entry-mismatch-parent-claude-tool_name",
    ]
    assert set(failures) <= _ENTRY_MISMATCH_IDS
    rendered = run._nex_preflight_failure(failures)[1]
    for leaked in ("/ws", "/home", "DENIED_CANARY", "claude.txt"):
        assert leaked not in rendered


def test_preflight_denial_entry_mismatch_ids_carry_only_fixed_values(monkeypatch):
    monkeypatch.setenv("HOME", "/home/canary")
    events = _preflight_events()
    # A tool ID that would be recognisable if it leaked into a category.
    for kind in ("tool_use", "tool_result"):
        _find(events, kind, "child-claude_case")["id"] = "toolu_SENTINEL_ID"
    _cli_text(events, "parent-claude_case")
    _cli_denial(events, "parent-claude_case")
    _cli_text(events, "toolu_SENTINEL_ID")
    _cli_denial(events, "toolu_SENTINEL_ID")
    parent_entry, child_entry = _terminal(events)["permission_denials"]
    parent_entry.update(
        tool_name="SENTINEL_TOOL",
        tool_input={"file_path": "/SENTINEL_PATH", "content": "SENTINEL_CONTENT"},
        SENTINEL_FIELD="SENTINEL_VALUE",
    )
    child_entry["tool_input"] = {"SENTINEL_KEY": "SENTINEL_VALUE"}

    failures = _preflight_failures(events)
    assert failures == [
        "denials/entry-mismatch-child-claude_case-input_shape",
        "denials/entry-mismatch-parent-claude_case-content",
        "denials/entry-mismatch-parent-claude_case-file_path_other",
        "denials/entry-mismatch-parent-claude_case-tool_name",
    ]
    assert set(failures) <= _ENTRY_MISMATCH_IDS
    rendered = run._nex_preflight_failure(failures)[1]
    for leaked in ("SENTINEL", "/ws", "/home", "DENIED_CANARY", "claude_case.txt"):
        assert leaked not in rendered


def test_preflight_failure_message_keeps_every_entry_mismatch_past_the_cap():
    # Repeated denied Writes in one slot each carry their own denial ID, so a
    # single run can legally raise every actor x label x class mismatch at once.
    crowd = [
        f"denial/{actor}-{label}-{suffix}"
        for actor in run._NEX_PREFLIGHT_ACTORS
        for label in run._NEX_PREFLIGHT_LABELS
        for suffix in (
            "count", "write-succeeded", "result-truncated", "result-malformed",
            "wrong-hook-reason", "generic-hook-error", "hook-reason-missing",
            "cli-denials-absent", "cli-denial-missing", "parent-denial-missing",
            "parent-input-mismatch",
        )
    ]
    forged = "denials/entry-mismatch-parent-claude-SENTINEL_VALUE"
    passed, message = run._nex_preflight_failure(
        [*sorted(_ENTRY_MISMATCH_IDS), *crowd, forged]
    )

    assert passed is False
    head, separator, tail = message.partition("; entry_mismatch=")
    assert separator
    prefix = "NEX-890 preflight failed closed: category="
    assert head.startswith(prefix)
    assert len(head) - len(prefix) == 600  # the other categories stay capped
    slots = tail.split(",")
    assert len(slots) == len(run._NEX_PREFLIGHT_ACTORS) * len(run._NEX_PREFLIGHT_LABELS)
    rendered = set()
    for slot in slots:
        actor_label, classes = slot.split(":")
        actor, label = actor_label.split("-", 1)
        rendered.update(
            f"denials/entry-mismatch-{actor}-{label}-{mismatch}"
            for mismatch in classes.split("+")
        )
    assert rendered == _ENTRY_MISMATCH_IDS
    assert "SENTINEL" not in tail


def test_preflight_denial_entry_mismatch_classes_are_fixed_and_exact_match_passes():
    use = {"name": "Write", "input": {"file_path": "/ws/a.txt", "content": "c"}}
    # Missing fields are mismatches, never an exact match.
    assert run._nex_preflight_entry_mismatch_classes({}, use) == {
        "tool_name", "input_shape",
    }
    assert run._nex_preflight_entry_mismatch_classes(
        {"tool_input": {"file_path": "/ws/a.txt", "content": "c"}}, use,
    ) == {"tool_name"}
    assert run._nex_preflight_entry_mismatch_classes(
        {"tool_name": "Write"}, use,
    ) == {"input_shape"}
    assert run._nex_preflight_entry_mismatch_classes(
        {"tool_name": "Write", "tool_input": None}, use,
    ) == {"input_shape"}
    assert run._nex_preflight_entry_mismatch_classes(
        {"tool_name": "Write", "tool_input": {"file_path": "/ws/a.txt", "content": "c"}},
        use,
    ) == set()
    # Normalizing never turns a changed input into a pass.
    assert run._nex_preflight_entry_mismatch_classes(
        {"tool_name": "Write", "tool_input": {"file_path": "/ws//a.txt", "content": "c"}},
        use,
    ) == {"file_path_normalized"}
    assert all(
        mismatch.replace("_", "").isalpha() and mismatch.islower()
        for mismatch in run._NEX_PREFLIGHT_ENTRY_MISMATCH_CLASSES
    )
    assert not any("-" in label for label in run._NEX_PREFLIGHT_LABELS)


def test_preflight_denial_entry_accepts_only_a_one_side_home_expansion(monkeypatch):
    monkeypatch.setenv("HOME", "/home/canary")
    classes = run._nex_preflight_entry_mismatch_classes
    tilde = {"name": "Write", "input": {"file_path": "~/d/a.txt", "content": "c"}}
    absolute = {"name": "Write", "input": {"file_path": "/home/canary/d/a.txt", "content": "c"}}

    def entry(file_path, content="c", tool_name="Write", **extra):
        return {
            "tool_name": tool_name,
            "tool_input": {"file_path": file_path, "content": content, **extra},
        }

    # Either side may be the expanded one.
    assert classes(entry("/home/canary/d/a.txt"), tilde) == set()
    assert classes(entry("~/d/a.txt"), absolute) == set()
    # The alias never excuses any other difference.
    assert classes({"tool_input": entry("/home/canary/d/a.txt")["tool_input"]}, tilde) == {
        "tool_name",
    }
    assert classes(entry("/home/canary/d/a.txt", tool_name="write"), tilde) == {"tool_name"}
    assert classes(entry("/home/canary/d/a.txt", content="c\n"), tilde) == {"content"}
    assert classes(entry("/home/canary/d/a.txt", content=b"c"), tilde) == {"input_shape"}
    assert classes(entry("/home/canary/d/a.txt", extra=1), tilde) == {"input_shape"}
    assert classes(entry("/home/other/d/a.txt"), tilde) == {"file_path_other"}
    # normpath-only differences, with or without the expansion, still fail.
    for normalized, use in (
        ("/home/canary/./d/a.txt", tilde),
        ("/home/canary/d//a.txt", tilde),
        ("/home/canary/d/../d/a.txt", tilde),
        ("/home/canary/d/a.txt/", tilde),
        ("~/./d/a.txt", tilde),
        ("~/./d/a.txt", absolute),
        ("/home/canary/./d/a.txt", absolute),
    ):
        assert classes(entry(normalized), use) == {"file_path_normalized"}
    assert "file_path_expanduser" not in run._NEX_PREFLIGHT_ENTRY_MISMATCH_CLASSES


_HOME_ALIAS_EXPANDED = "/home/canary/.nex890-home-preflight-t/home-alias-denied.txt"


def _home_alias_fallback_events(changed_actors, **entry_changes):
    """Both actors use the CLI fallback for home_alias; some entries differ."""
    events = _preflight_events()
    for actor in run._NEX_PREFLIGHT_ACTORS:
        identifier = f"{actor}-home_alias"
        _cli_text(events, identifier)
        _cli_denial(events, identifier)
        entry = _terminal(events)["permission_denials"][-1]
        entry["tool_input"] = dict(entry["tool_input"])  # never alias the Write input
        if actor in changed_actors:
            tool_name = entry_changes.get("tool_name", entry["tool_name"])
            entry["tool_name"] = tool_name
            entry["tool_input"].update(
                {key: value for key, value in entry_changes.items() if key != "tool_name"}
            )
    return events


@pytest.mark.parametrize(
    "changed_actors", [("parent",), ("child",), ("parent", "child")],
)
def test_preflight_stream_accepts_expanded_home_alias_denial_entries(
    monkeypatch, changed_actors,
):
    monkeypatch.setenv("HOME", "/home/canary")
    events = _home_alias_fallback_events(changed_actors, file_path=_HOME_ALIAS_EXPANDED)
    assert _preflight_failures(events) == []


@pytest.mark.parametrize("actor", ["parent", "child"])
@pytest.mark.parametrize(
    ("changes", "mismatch"),
    [
        (
            {"file_path": "/home/canary/./.nex890-home-preflight-t/home-alias-denied.txt"},
            "file_path_normalized",
        ),
        (
            {"file_path": "~/./.nex890-home-preflight-t/home-alias-denied.txt"},
            "file_path_normalized",
        ),
        (
            {"file_path": "/home/other/.nex890-home-preflight-t/home-alias-denied.txt"},
            "file_path_other",
        ),
        ({"file_path": _HOME_ALIAS_EXPANDED, "content": "DENIED_CANARY\n"}, "content"),
        ({"file_path": _HOME_ALIAS_EXPANDED, "tool_name": "write"}, "tool_name"),
        ({"file_path": _HOME_ALIAS_EXPANDED, "content": 1}, "input_shape"),
    ],
)
def test_preflight_stream_home_alias_expansion_never_excuses_another_difference(
    monkeypatch, actor, changes, mismatch,
):
    monkeypatch.setenv("HOME", "/home/canary")
    events = _home_alias_fallback_events((actor,), **changes)
    failures = _preflight_failures(events)
    assert failures == [f"denials/entry-mismatch-{actor}-home_alias-{mismatch}"]
    assert set(failures) <= _ENTRY_MISMATCH_IDS
    rendered = run._nex_preflight_failure(failures)[1]
    for leaked in ("/home", "~/", "nex890-home-preflight", "DENIED_CANARY"):
        assert leaked not in rendered


def test_preflight_home_alias_expansion_keeps_id_correlation(monkeypatch):
    monkeypatch.setenv("HOME", "/home/canary")
    # An expanded entry under a foreign ID never stands in for the Write's own.
    events = _preflight_events()
    _cli_text(events, "parent-home_alias")
    use = _find(events, "tool_use", "parent-home_alias")
    _terminal(events)["permission_denials"].append({
        "tool_name": "Write", "tool_use_id": "ghost",
        "tool_input": {**use["input"], "file_path": _HOME_ALIAS_EXPANDED},
    })
    assert _preflight_failures(events) == [
        "denial/parent-home_alias-cli-denial-missing", "denials/unmatched-id",
    ]

    # An exact expansion aimed at another label's slot is that slot's path mismatch.
    events = _preflight_events()
    _cli_text(events, "parent-outside")
    _cli_denial(events, "parent-outside")
    entry = _terminal(events)["permission_denials"][-1]
    entry["tool_input"] = {**entry["tool_input"], "file_path": _HOME_ALIAS_EXPANDED}
    assert _preflight_failures(events) == [
        "denials/entry-mismatch-parent-outside-file_path_other",
    ]


@pytest.mark.parametrize("actor", ["parent", "child"])
def test_preflight_inside_marker_denial_contradicts_the_boundary(actor):
    errored = _preflight_events()
    _find(errored, "tool_result", f"{actor}-inside")["is_error"] = True
    assert _preflight_failures(errored) == [f"write/{actor}-inside-denied"]

    listed = _preflight_events()
    _cli_denial(listed, f"{actor}-inside")
    assert f"write/{actor}-inside-denied" in _preflight_failures(listed)

    newline = _preflight_events()
    _find(newline, "tool_use", f"{actor}-inside")["input"]["content"] += "\n"
    assert _preflight_failures(newline) == []

    wrong = _preflight_events()
    _find(wrong, "tool_use", f"{actor}-inside")["input"]["content"] = "OTHER"
    assert _preflight_failures(wrong) == ["write/inside-wrong-content"]


def test_preflight_rejects_retries_wrong_paths_and_successful_denied_writes():
    retry = _preflight_events()
    use = _find(retry, "tool_use", "parent-outside")
    _before_terminal(
        retry,
        _use("parent-outside-2", "Write", dict(use["input"])),
        _result("parent-outside-2", is_error=True, content=_hook_denial(
            run._nex_hook.REASON_WRITE_OUTSIDE
        )),
    )
    assert _preflight_failures(retry) == ["denial/parent-outside-count", "write/count"]

    content = _preflight_events()
    _find(content, "tool_use", "parent-outside")["input"]["content"] = "DENIED_CANARY\n"
    assert _preflight_failures(content) == ["write/denied-wrong-content"]

    expanded = _preflight_events()
    _find(expanded, "tool_use", "child-home_alias")["input"]["file_path"] = (
        "/Users/someone/.nex890-home-preflight-t/home-alias-denied.txt"
    )
    failures = _preflight_failures(expanded)
    assert "write/unexpected-path" in failures
    assert "denial/child-home_alias-count" in failures

    succeeded = _preflight_events()
    _find(succeeded, "tool_result", "parent-mcp_case").update(is_error=False, content="ok")
    assert _preflight_failures(succeeded) == ["denial/parent-mcp_case-write-succeeded"]

    malformed = _preflight_events()
    _find(malformed, "tool_use", "parent-mcp")["input"]["mode"] = "overwrite"
    assert "write/malformed-input" in _preflight_failures(malformed)


def test_preflight_optional_reads_pair_but_never_decide():
    events = _preflight_events()
    _before_terminal(
        events,
        _use("read-1", "Read", {"file_path": "/etc/hosts"}),
        _result("read-1", is_error=True, content=_hook_denial(run._nex_hook.REASON_READ_OUTSIDE)),
        _use("search-1", "ToolSearch", {"query": "select:Write"}),
        _result("search-1"),
        _use("ls-1", "LS", {"path": "/ws"}, "task-1"),
        _result("ls-1", is_error=True),
        _use("list-1", "ListMcpResourcesTool", {}),
        _result("list-1"),
    )
    _cli_denial(events, "ls-1")
    assert _preflight_failures(events) == []

    unpaired = _preflight_events()
    _before_terminal(unpaired, _use("glob-1", "Glob", {"pattern": "*"}))
    assert _preflight_failures(unpaired) == ["stream/missing-tool-result"]


@pytest.mark.parametrize(
    ("added", "expected"),
    [
        ([_use("edit-1", "Edit", {}), _result("edit-1")], "mutation/unexpected-tool"),
        ([_use("nb-1", "NotebookEdit", {}), _result("nb-1")], "mutation/unexpected-tool"),
        ([_use("bash-1", "Bash", {"command": "true"}), _result("bash-1")], "shell/tool-used"),
        ([_use("fetch-1", "WebFetch", {}), _result("fetch-1")], "tool/unknown"),
        ([_use("other-1", "mcp__other__x", {}), _result("other-1")], "mcp/unexpected-call"),
        (
            [_use("probe-2", "mcp__nxd-desktop__preflight_probe", {"nonce": "n0nce"}), _result("probe-2")],
            "mcp/probe-count",
        ),
        (
            [
                _use("reader-2", "mcp__nxd-desktop__read_review_input",
                     {"operation": "list", "path": "/ws/review-input"}),
                _result("reader-2"),
            ],
            "mcp/unexpected-call",
        ),
    ],
)
def test_preflight_rejects_extra_calls_and_mutators(added, expected):
    events = _preflight_events()
    _before_terminal(events, *added)
    assert _preflight_failures(events) == [expected]


def test_preflight_required_mcp_calls_must_succeed():
    events = _preflight_events()
    _find(events, "tool_result", "capture-1")["is_error"] = True
    assert _preflight_failures(events) == ["mcp/capture-unsuccessful"]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda events: _before_terminal(events, _result("probe-1")), "stream/duplicate-tool-result"),
        (lambda events: _before_terminal(events, _result("ghost")), "stream/unmatched-tool-result"),
        (
            lambda events: events.remove(_find(events, "tool_result", "probe-1")),
            "stream/missing-tool-result",
        ),
        (
            lambda events: _before_terminal(
                events, {**_result("x"), "id": None, "malformed_id": True}
            ),
            "stream/malformed-tool-result-id",
        ),
        (
            lambda events: _before_terminal(events, _use("probe-1", "Read", {})),
            "stream/duplicate-tool-use-id",
        ),
        (lambda events: events.remove(_terminal(events)), "stream/terminal-result-count"),
        (lambda events: events.append(dict(_terminal(events))), "stream/terminal-result-count"),
        (
            lambda events: events.insert(0, events.pop(events.index(_find(events, "tool_result", "probe-1")))),
            "stream/result-before-use",
        ),
    ],
)
def test_preflight_result_correlation_defects_fail_closed(mutate, expected):
    events = _preflight_events()
    mutate(events)
    assert expected in _preflight_failures(events)


def test_preflight_targets_check_both_tilde_candidates_and_inside_markers(tmp_path):
    absolute = tmp_path / "home" / "probe" / "home-alias-denied.txt"
    literal = tmp_path / "workspace" / "~" / "probe" / "home-alias-denied.txt"
    inside = tmp_path / "parent-inside.txt"
    marker = run._NEX_PREFLIGHT_PARENT_MARKER
    inside.write_text(marker + "\n", encoding="utf-8")

    def failures():
        return run._nex_preflight_target_failures(
            denied_targets={"home_alias": (absolute, literal)},
            inside_targets=(("parent", inside, marker),),
        )

    assert failures() == []
    for candidate in (absolute, literal):
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("DENIED_CANARY", encoding="utf-8")
        assert failures() == ["target/home_alias-present"]
        candidate.unlink()
    inside.write_text(marker + "\n\n", encoding="utf-8")
    assert failures() == ["target/parent-inside-content"]
    inside.unlink()
    assert failures() == ["target/parent-inside-missing"]


def _nex_policy_session(tmp_path):
    workspace = tmp_path / "workspace"
    plugin_root = workspace / ".canary-plugin"
    session_root = workspace / ".runner-private"
    for path in (plugin_root, session_root):
        path.mkdir(parents=True)
    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"],
        root=session_root,
        nex_mode=True,
        nex_preflight_mode=True,
        nex_workspace=workspace,
        nex_protected_paths=[plugin_root],
    )
    session._root = session_root
    session._prepare_nex_security_files()
    argv = run._nex_preflight_expected_hook_argv(
        hook_path=session_root / "nex-write-policy-hook.py",
        workspace=workspace,
        session_root=session_root,
        plugin_roots=[plugin_root],
    )
    return session, argv


def test_preflight_policy_gate_accepts_generated_settings_and_independent_deny_literal(tmp_path):
    session, argv = _nex_policy_session(tmp_path)

    assert argv is not None and os.path.isabs(argv[0]) and argv[1] == "-I"
    assert run._nex_preflight_policy_failure(session, argv) is None
    assert run._NEX_EXPECTED_SETTINGS_DENY == _PREFLIGHT_DENY_LITERAL
    settings = json.loads(session.nex_settings_path.read_bytes())
    assert settings["permissions"]["deny"] == list(_PREFLIGHT_DENY_LITERAL)


def test_preflight_policy_gate_fails_on_false_verify_and_missing_hash_entry(tmp_path, monkeypatch):
    session, argv = _nex_policy_session(tmp_path)
    monkeypatch.setattr(session, "verify_nex_security_files", lambda: False)
    assert run._nex_preflight_policy_failure(session, argv) == "policy/verify-failed"

    monkeypatch.setattr(session, "verify_nex_security_files", lambda: True)
    session._nex_policy_hashes.pop(session.nex_settings_path)
    assert run._nex_preflight_policy_failure(session, argv) == "settings/hash-entry-missing"
    assert run._nex_preflight_policy_failure(session, None) == "settings/interpreter-not-absolute"


def test_preflight_policy_gate_reads_settings_once_and_hashes_those_bytes(tmp_path, monkeypatch):
    session, argv = _nex_policy_session(tmp_path)
    settings_path = session.nex_settings_path
    monkeypatch.setattr(session, "verify_nex_security_files", lambda: True)
    original_read_bytes = Path.read_bytes
    reads = []

    def counting_read_bytes(path):
        if path == settings_path:
            reads.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    assert run._nex_preflight_policy_failure(session, argv) is None
    assert len(reads) == 1

    # A swap after verification is caught by hashing the bytes actually parsed.
    settings_path.chmod(0o600)
    tampered = json.loads(original_read_bytes(settings_path))
    tampered["permissions"]["deny"] = []
    settings_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert run._nex_preflight_policy_failure(session, argv) == "settings/hash-mismatch"


def test_preflight_expected_hook_argv_requires_an_absolute_interpreter(tmp_path, monkeypatch):
    kwargs = {
        "hook_path": tmp_path / "hook.py",
        "workspace": tmp_path,
        "session_root": tmp_path / "private",
        "plugin_roots": [tmp_path / "plugin"],
    }
    monkeypatch.setattr(run.shutil, "which", lambda _name: "bin/python3")
    assert run._nex_preflight_expected_hook_argv(**kwargs) is None
    monkeypatch.setattr(run.shutil, "which", lambda _name: None)
    argv = run._nex_preflight_expected_hook_argv(**kwargs)
    assert argv[0] == sys.executable
    assert argv[-2:] == ["--plugin-root", str((tmp_path / "plugin").resolve())]


def _settings_variant(settings, change):
    variant = json.loads(json.dumps(settings))
    change(variant)
    return json.dumps(variant).encode("utf-8")


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda s: s.update(env={}), "settings/top-level-keys"),
        (lambda s: s["permissions"].update(allow=["Bash"]), "settings/permission-keys"),
        (lambda s: s["permissions"]["deny"].reverse(), "settings/deny-list"),
        (lambda s: s["permissions"]["deny"].pop(), "settings/deny-list"),
        (lambda s: s["hooks"].update(PostToolUse=[]), "settings/hook-events"),
        (lambda s: s["hooks"]["PreToolUse"].append(s["hooks"]["PreToolUse"][0]), "settings/pretooluse-count"),
        (lambda s: s["hooks"]["PreToolUse"][0].update(matcher="Write"), "settings/matcher"),
        (
            lambda s: s["hooks"]["PreToolUse"][0]["hooks"].append(s["hooks"]["PreToolUse"][0]["hooks"][0]),
            "settings/hook-count",
        ),
        (lambda s: s["hooks"]["PreToolUse"][0]["hooks"][0].update(timeout=5), "settings/hook-shape"),
        (
            lambda s: s["hooks"]["PreToolUse"][0]["hooks"][0].update(command="python3 'unterminated"),
            "settings/hook-command-unparseable",
        ),
        (
            lambda s: s["hooks"]["PreToolUse"][0]["hooks"][0].update(
                command=s["hooks"]["PreToolUse"][0]["hooks"][0]["command"].replace(" -I ", " ")
            ),
            "settings/hook-argv",
        ),
    ],
)
def test_preflight_settings_structure_is_exact(tmp_path, change, expected):
    session, argv = _nex_policy_session(tmp_path)
    settings = json.loads(session.nex_settings_path.read_bytes())
    data = _settings_variant(settings, change)

    assert run._nex_preflight_settings_failure(
        data, hashlib.sha256(data).hexdigest(), argv
    ) == expected


def test_preflight_settings_reject_duplicate_keys_and_foreign_workspace(tmp_path):
    session, argv = _nex_policy_session(tmp_path)
    good = session.nex_settings_path.read_bytes()
    duplicate = b'{"hooks":{},' + good[1:]
    assert run._nex_preflight_settings_failure(
        duplicate, hashlib.sha256(duplicate).hexdigest(), argv
    ) == "settings/unparseable"

    foreign = list(argv)
    foreign[foreign.index("--workspace") + 1] = str(tmp_path / "other")
    assert run._nex_preflight_settings_failure(
        good, hashlib.sha256(good).hexdigest(), foreign
    ) == "settings/hook-argv"


def test_preflight_argv_validates_the_launched_allowlist_and_skill_permission(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    mcp_config = tmp_path / "mcp.json"
    mcp_config.write_text("{}", encoding="utf-8")
    raw = "Read,Write,Task," + run._NEX_PREFLIGHT_SKILL_PERMISSION + ",mcp__other__danger"

    def argv_for(tools):
        return eb.ClaudeBackend()._agent_command(
            tmp_path, "opus", extra_dirs=[], effort="medium", skill_pack_dir=None,
            allowed_tools=tools, mcp_config=mcp_config, strict_mcp_config=True,
            nex_mode=True, nex_settings_path=settings,
        )

    def failure(argv, tools=raw):
        return run._nex_preflight_argv_failure(
            argv, settings_path=settings, allowed_tools=tools
        )

    launched = eb.isolated_mcp_allowed_tools(raw, server_name="nxd-desktop")
    assert "mcp__other__danger" not in launched
    good = argv_for(launched)
    assert failure(good) is None
    assert failure(argv_for(raw)) == "argv/allowed-tools"
    for tools in (
        "Read,Write,Task",
        "Skill," + raw,
        raw + ",Skill(other:skill)",
    ):
        normalized = eb.isolated_mcp_allowed_tools(tools, server_name="nxd-desktop")
        assert failure(argv_for(normalized), tools) == "argv/skill-permission"
    assert failure([*good, "--settings", str(settings)]) == "argv/settings"
    wrong_deny = list(good)
    wrong_deny[wrong_deny.index("--disallowedTools") + 1] = "Bash"
    assert failure(wrong_deny) == "argv/disallowed-tools"
    assert failure([item for item in good if item != "--strict-mcp-config"]) == (
        "argv/strict-mcp-config"
    )
    wrong_sources = list(good)
    wrong_sources[wrong_sources.index("--setting-sources") + 1] = "user,project"
    assert failure(wrong_sources) == "argv/setting-sources"


def test_preflight_hook_probe_classification_is_exact():
    reason = run._nex_hook.REASON_WRITE_OUTSIDE
    classify = run._nex_preflight_hook_probe_failure
    assert classify("inside", None, 0, "") is None
    assert classify("inside", None, 0, "note\n") == "hook-probe/inside-not-allowed"
    assert classify("inside", None, 2, reason + "\n") == "hook-probe/inside-not-allowed"
    assert classify("outside", reason, 2, reason + "\n") is None
    for returncode, stderr in (
        (1, reason + "\n"), (2, reason), (2, reason + " extra\n"),
        (2, run._nex_hook.REASON_WRITE_PROTECTED + "\n"), (0, ""),
    ):
        assert classify("outside", reason, returncode, stderr) == "hook-probe/outside-wrong-denial"


def test_preflight_direct_hook_probes_cover_every_label_and_tilde_spelling(tmp_path):
    root = tmp_path.resolve()
    workspace = root / "workspace"
    plugin_root = workspace / ".canary-plugin"
    session_root = workspace / ".runner-private"
    for path in (plugin_root, session_root, root / "outside"):
        path.mkdir(parents=True)
    alias_text = str(session_root / "private-alias-denied.txt")
    home_name = ".nex890-home-preflight-probe-test"
    denied_paths = {
        "outside": str(root / "outside" / "outside-denied.txt"),
        "private": str(session_root / "private-denied.txt"),
        "plugin": str(plugin_root / "plugin-denied.txt"),
        "claude": str(workspace / ".claude" / "denied-canary.txt"),
        "claude_case": str(workspace / ".ClAuDe" / "denied-canary.txt"),
        "mcp": str(workspace / ".mcp.json"),
        "mcp_case": str(workspace / ".MCP.JSON"),
        "private_alias": (
            alias_text[len("/private"):] if alias_text.startswith("/private/") else alias_text
        ),
        "home_alias": str(Path.home() / home_name / "home-alias-denied.txt"),
    }
    cases = run._nex_preflight_hook_probe_cases(
        inside_path=workspace / "parent-inside.txt",
        denied_paths=denied_paths,
        home_alias_relative=f"~/{home_name}/home-alias-denied.txt",
    )
    assert [case[0] for case in cases] == [
        "inside", *run._NEX_PREFLIGHT_LABELS, "home_alias_literal",
    ]
    assert cases[-1][2] == run._nex_hook.REASON_HOME_RELATIVE
    assert dict((case[0], case[2]) for case in cases)["home_alias"] == (
        run._nex_hook.REASON_WRITE_OUTSIDE
    )
    argv = run._nex_preflight_expected_hook_argv(
        hook_path=Path(run._nex_hook.__file__),
        workspace=workspace,
        session_root=session_root,
        plugin_roots=[plugin_root],
    )
    if not alias_text.startswith("/private/"):
        # Only macOS exposes the /private alias this label exercises.
        cases = [case for case in cases if case[0] != "private_alias"]
    assert run._nex_preflight_run_hook_probes(argv, cases) is None

    swapped = [
        (case_id, tool_input, run._nex_hook.REASON_WRITE_PROTECTED if case_id == "outside" else reason)
        for case_id, tool_input, reason in cases
    ]
    assert run._nex_preflight_run_hook_probes(argv, swapped) == "hook-probe/outside-wrong-denial"
    assert run._nex_preflight_run_hook_probes(
        [str(root / "missing-python")], cases
    ) == "hook-probe/inside-unavailable"


def test_stdio_activation_uses_shared_state_and_minimal_env(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    (scenario / "fixtures").mkdir(parents=True)
    bundle = tmp_path / "activation.json"
    bundle.write_text('{"schema":"test"}\n', encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_tmp = tmp_path / "runtime"
    runtime_tmp.mkdir()
    bin_dir = runtime_tmp / "bin"
    bin_dir.mkdir()
    log = tmp_path / "activation-argv.json"
    _script(
        bin_dir / "nxd-desktop-supervisor",
        (
            "import json, os, sys\n"
            f"open({str(log)!r}, 'w').write(json.dumps(sys.argv[1:]) + '\\n' + json.dumps('NXD_EVAL_SOURCE_TOKEN' in os.environ))\n"
            "print(json.dumps({'activated': True}), flush=True)\n"
        ),
    )
    _script(bin_dir / "nxd-desktop-kernel-host", "pass\n")

    monkeypatch.setattr(
        run,
        "_desktop_runtime",
        lambda _scenario, _tmp: (bin_dir, {}, sys.executable),
    )
    monkeypatch.setattr(
        run,
        "_prepare_stdio_profile",
        lambda _scenario, _spec, _workspace, output, _python: output.write_text("{}\n", encoding="utf-8"),
    )
    monkeypatch.setenv("NXD_EVAL_SOURCE_TOKEN", "should-not-cross-boundary")

    class FakeSession:
        def __init__(self, argv, **kwargs):
            self.argv = argv
            self.kwargs = kwargs

    monkeypatch.setattr(run, "DesktopStdioSession", FakeSession)
    spec = {"workflow_activation_bundle": "../activation.json"}
    _bin, _env, _python, session = run._desktop_stdio_session(
        scenario, spec, workspace, runtime_tmp
    )
    logged_args, inherited_secret = log.read_text(encoding="utf-8").splitlines()
    assert json.loads(logged_args) == [
        "--data-dir", str(runtime_tmp / "stdio-state"),
        "workflow", "activate", "--bundle", str(bundle.resolve()),
    ]
    assert json.loads(inherited_secret) is False
    assert session.argv[1:3] == ["--data-dir", str(runtime_tmp / "stdio-state")]
    assert session.argv[3:5] == ["mcp", "serve"]


def test_stdio_activation_failure_is_redacted(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    (scenario / "fixtures").mkdir(parents=True)
    bundle = tmp_path / "activation.json"
    bundle.write_text('{}\n', encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_tmp = tmp_path / "runtime"
    runtime_tmp.mkdir()
    bin_dir = runtime_tmp / "bin"
    bin_dir.mkdir()
    _script(
        bin_dir / "nxd-desktop-supervisor",
        "import sys\nprint('authorization=activation-secret', file=sys.stderr)\nsys.exit(1)\n",
    )
    _script(bin_dir / "nxd-desktop-kernel-host", "pass\n")
    monkeypatch.setattr(
        run,
        "_desktop_runtime",
        lambda _scenario, _tmp: (bin_dir, {}, sys.executable),
    )
    monkeypatch.setattr(
        run,
        "_prepare_stdio_profile",
        lambda _scenario, _spec, _workspace, output, _python: output.write_text("{}\n", encoding="utf-8"),
    )
    with pytest.raises(RuntimeError, match="activation failed") as caught:
        run._desktop_stdio_session(
            scenario, {"workflow_activation_bundle": "../activation.json"}, workspace, runtime_tmp
        )
    assert "activation-secret" not in str(caught.value)


def test_combined_runtime_owns_endpoint_trace_and_cleanup(tmp_path, monkeypatch):
    """The two runner-owned transports share one run without sharing state."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_tmp = tmp_path / "runtime"
    runtime_tmp.mkdir()
    bin_dir = runtime_tmp / "bin"
    bin_dir.mkdir()
    _script(bin_dir / "nxd-desktop-supervisor", FAKE_SERVER)

    monkeypatch.setattr(
        run,
        "_desktop_runtime",
        lambda _scenario, _tmp: (bin_dir, {}, sys.executable),
    )

    def prepare_profile(_scenario, _spec, _workspace, output, _python):
        output.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(run, "_prepare_stdio_profile", prepare_profile)
    http_spec = run.scenario_needs_http_stub(SUPERVISOR_SCENARIO)
    assert http_spec is not None
    before_observation_env = os.environ.get(run.STUB_OBSERVATIONS_ENV)
    proxy = None

    with run.desktop_stdio_runtime(
        SUPERVISOR_SCENARIO,
        workspace,
        runtime_tmp,
        _stdio_spec(),
        http_spec,
        "claude",
    ) as (_bin_dir, _env, _python, session, observations):
        assert session.setup_result.status == "passed"
        assert observations is not None
        assert workspace.joinpath("ENDPOINT_URL").read_text().strip().startswith(
            "http://127.0.0.1:"
        )
        assert os.environ.get(run.STUB_OBSERVATIONS_ENV) == before_observation_env
        assert not observations.is_relative_to(workspace)

        proxy = subprocess.Popen(
            [
                sys.executable,
                str(ds.PROXY_MODULE),
                "--proxy",
                "--spec",
                str(session.root / "server-spec.json"),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        session.attach_process(proxy)
        assert proxy.stdin is not None and proxy.stdout is not None
        proxy.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"authorization": "Bearer live-token"},
                }
            )
            + "\n"
        )
        proxy.stdin.flush()
        assert json.loads(proxy.stdout.readline())["result"]["echo"] == "initialize"

        endpoint = workspace.joinpath("ENDPOINT_URL").read_text().strip()
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(endpoint + "/v1/monitors", timeout=5)
        trace = session.trace_path.read_text(encoding="utf-8")
        assert "live-token" not in trace
        assert ds.REDACTED in trace
        assert observations.read_text(encoding="utf-8").count("authorized") == 1

    assert proxy is not None and proxy.poll() is not None
    assert not (runtime_tmp / "stdio-session" / "mcp-config.json").exists()


def test_combined_http_setup_failure_stays_setup_failure(tmp_path, monkeypatch):
    """A bad HTTP fixture must not be reported as an agent or server failure."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_tmp = tmp_path / "runtime"
    runtime_tmp.mkdir()
    called = False

    def unexpected_stdio_setup(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("stdio setup ran after HTTP setup failed")

    monkeypatch.setattr(run, "_desktop_stdio_session", unexpected_stdio_setup)
    bad_http_spec = {
        "module": "missing-fixture",
        "start": "start_server",
        "stop": "stop_server",
        "endpoint_file": "ENDPOINT_URL",
    }

    with (
        pytest.raises(run.HttpStubSetupError, match="module not found"),
        run.desktop_stdio_runtime(
            SUPERVISOR_SCENARIO,
            workspace,
            runtime_tmp,
            _stdio_spec(),
            bad_http_spec,
            "claude",
        ),
    ):
        pass
    assert called is False


def test_http_stub_wraps_module_and_start_failures_as_setup(tmp_path):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    module = fixtures / "broken.py"
    module.write_text(
        "raise RuntimeError('module boom')\n",
        encoding="utf-8",
    )
    with pytest.raises(run.HttpStubSetupError, match="RuntimeError: module boom"):
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass

    module.write_text(
        "def start_server():\n"
        "    raise OSError('bind boom')\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    pass\n",
        encoding="utf-8",
    )
    with pytest.raises(run.HttpStubSetupError, match="OSError: bind boom"):
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass


def test_http_stub_wraps_stop_failure_as_teardown(tmp_path):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(
        "def start_server():\n"
        "    return object(), 43210, object()\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    raise RuntimeError('authorization=stop-secret')\n",
        encoding="utf-8",
    )

    with pytest.raises(run.HttpStubTeardownError, match="RuntimeError: authorization=<redacted>") as caught:
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass
    assert "stop-secret" not in "".join(traceback.format_exception(caught.value))


def test_http_stub_does_not_use_stale_outer_exception_for_teardown(tmp_path):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(
        "def start_server():\n"
        "    return object(), 43210, object()\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    raise RuntimeError('stop boom')\n",
        encoding="utf-8",
    )

    # Keep an unrelated exception active in an outer handler while the context
    # exits. The context must track its own body exception state rather than
    # consulting the ambient sys.exc_info().
    try:
        raise ValueError("unrelated")
    except ValueError:
        with pytest.raises(run.HttpStubTeardownError, match="stop boom"):
            with run.http_stub_server(
                scenario, workspace, {"module": "broken"}, "claude"
            ):
                pass


def test_http_stub_endpoint_setup_failure_keeps_teardown_failure_attached(tmp_path):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    endpoint_target = workspace / "ENDPOINT_URL"
    endpoint_target.mkdir()
    (fixtures / "broken.py").write_text(
        "def start_server():\n"
        "    return object(), 43210, object()\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    raise RuntimeError('stop boom')\n",
        encoding="utf-8",
    )

    with pytest.raises(run.HttpStubSetupError, match="IsADirectoryError") as caught:
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass

    assert any("stop boom" in note for note in caught.value.__notes__)


def test_http_stub_setup_cleanup_does_not_mask_original_failure(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(
        "def set_observations_path(_path):\n"
        "    pass\n"
        "\n"
        "def start_server():\n"
        "    raise RuntimeError('authorization=setup-secret')\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    pass\n",
        encoding="utf-8",
    )

    class BrokenTemporaryDirectory:
        def __init__(self, **_kwargs):
            self.name = str(tmp_path / "observations")
            Path(self.name).mkdir()

        def cleanup(self):
            raise RuntimeError("authorization=cleanup-secret")

    monkeypatch.setattr(run.tempfile, "TemporaryDirectory", BrokenTemporaryDirectory)

    with pytest.raises(run.HttpStubSetupError) as caught:
        with run.http_stub_server(
            scenario,
            workspace,
            {"module": "broken", "observations": True},
            "claude",
            ):
                pass
    assert "setup-secret" not in str(caught.value)
    assert "authorization=<redacted>" in str(caught.value)
    assert caught.value.__cause__ is None
    assert "cleanup-secret" not in "".join(traceback.format_exception(caught.value))
    assert any("cleanup failed" in note for note in caught.value.__notes__)


def test_http_stub_control_flow_keeps_cleanup_failure_note(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(
        "def set_observations_path(_path):\n"
        "    pass\n"
        "\n"
        "def start_server():\n"
        "    raise GeneratorExit('setup exit')\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    pass\n",
        encoding="utf-8",
    )

    class BrokenTemporaryDirectory:
        def __init__(self, **_kwargs):
            self.name = str(tmp_path / "observations")
            Path(self.name).mkdir()

        def cleanup(self):
            raise RuntimeError("authorization=cleanup-secret")

    monkeypatch.setattr(run.tempfile, "TemporaryDirectory", BrokenTemporaryDirectory)

    with pytest.raises(GeneratorExit) as caught:
        with run.http_stub_server(
            scenario, workspace, {"module": "broken", "observations": True}, "claude"
        ):
            pass

    assert any("cleanup failed" in note for note in caught.value.__notes__)
    assert "cleanup-secret" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("raise KeyboardInterrupt('import interrupt')", KeyboardInterrupt),
        (
            "def start_server():\n"
            "    raise SystemExit('start exit')\n"
            "\n"
            "def stop_server(_server, _thread):\n"
            "    pass\n",
            SystemExit,
        ),
    ],
)
def test_http_stub_preserves_control_flow_during_setup(tmp_path, failure, expected):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(failure, encoding="utf-8")

    with pytest.raises(expected):
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass


def test_http_stub_preserves_control_flow_during_teardown(tmp_path):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(
        "def start_server():\n"
        "    return object(), 43210, object()\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    raise KeyboardInterrupt('stop interrupt')\n",
        encoding="utf-8",
    )

    with pytest.raises(KeyboardInterrupt):
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass


def _run_one_args():
    return SimpleNamespace(
        agent_backend="fake",
        judge_backend="codex",
        agent_model="fake-agent",
        judge_model="fake-judge",
        agent_effort="",
        judge_effort="",
        _agent_effort_explicit=False,
        _judge_effort_explicit=False,
        _judge_backend_explicit=False,
        _judge_model_explicit=False,
        agent_timeout=1,
        judge_timeout=1,
        docs_base="https://docs.example/",
        cache_dir=None,
    )


def test_codex_app_server_route_is_opt_in_only_for_codex_backend(tmp_path):
    scenario = tmp_path / "terminal-authenticated-dlt-api-ingestion"
    spec = {
        "codex_app_server_route": "terminal_workflow_review_v1",
        "workflow_activation_bundle": "activation.json",
        "workflow_action_guard": True,
    }

    claude_spec = run._desktop_stdio_spec_for_backend(scenario, spec, "claude")
    assert "codex_app_server_route" not in claude_spec
    assert claude_spec["workflow_action_guard"] is False
    assert "workflow_activation_bundle" not in claude_spec

    codex_spec = run._desktop_stdio_spec_for_backend(scenario, spec, "codex")
    assert codex_spec["codex_app_server_route"] == "terminal_workflow_review_v1"
    assert codex_spec["workflow_action_guard"] is True
    assert codex_spec["workflow_activation_bundle"] == "activation.json"

    nex_spec = run._desktop_stdio_spec_for_backend(
        scenario, {**spec, "nex_mode": True}, "claude"
    )
    assert "codex_app_server_route" not in nex_spec
    assert nex_spec["workflow_action_guard"] is True
    assert nex_spec["workflow_activation_bundle"] == "activation.json"


def test_claude_run_reaches_existing_backend_with_codex_route_marker(
    tmp_path, monkeypatch
):
    scenario = tmp_path / "terminal-authenticated-dlt-api-ingestion"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text(
        "# Scenario\n\n## Task for the agent\n\nImplement the task.\n",
        encoding="utf-8",
    )
    (scenario / "checks.json").write_text("{}\n", encoding="utf-8")
    (fixtures / "desktop_stdio.json").write_text(
        json.dumps({
            "codex_app_server_route": "terminal_workflow_review_v1",
            "workflow_action_guard": True,
            "supported_agent_backends": ["claude"],
        }),
        encoding="utf-8",
    )
    trace_path = tmp_path / "runner-trace.jsonl"
    trace_path.write_text("{}\n", encoding="utf-8")
    session = SimpleNamespace(trace_path=trace_path, nex_mode=False)
    seen = {}

    class FakeClaudeBackend:
        name = "claude"
        supports_multi_turn = False

        def check_dependencies(self):
            pass

        def run_agent(self, *_args, **kwargs):
            seen["called"] = True
            assert kwargs["stdio_session"] is session
            return True, "agent trace", {"final_answer": "done"}

    class FakeJudgeBackend:
        def check_dependencies(self):
            pass

    @contextlib.contextmanager
    def fake_runtime(_scenario, _workspace, _tmp, spec, _http, backend_name, **_kwargs):
        effective = run._desktop_stdio_spec_for_backend(
            scenario, spec, backend_name
        )
        seen["route"] = effective.get("codex_app_server_route")
        seen["guard"] = effective["workflow_action_guard"]
        yield tmp_path / "bin", {}, sys.executable, session, None

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeClaudeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: FakeJudgeBackend())
    monkeypatch.setattr(run, "desktop_stdio_runtime", fake_runtime)
    monkeypatch.setattr(run, "_nex_security_preflight", lambda: (True, "passed"))
    monkeypatch.setattr(run, "_load_nex890_checker", lambda *_args: object())
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    result = run.run_one(run.SkillSet("none", "", []), scenario, _run_one_args())

    assert result.ok is True
    assert seen == {"called": True, "route": None, "guard": False}


def test_run_one_combined_runtime_passes_http_marker_and_checks_in_context(
    tmp_path, monkeypatch
):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text(
        "# Scenario\n\n## Task for the agent\n\nDo the thing.\n",
        encoding="utf-8",
    )
    (scenario / "checks.json").write_text(
        json.dumps({"deterministic_check": {"script": "unused.py", "deps": []}}),
        encoding="utf-8",
    )
    http_marker = {
        "module": "stub",
        "start": "start_server",
        "stop": "stop_server",
        "endpoint_file": "ENDPOINT_URL",
    }
    (fixtures / "desktop_stdio.json").write_text("{}\n", encoding="utf-8")
    (fixtures / "http_stub.json").write_text(
        json.dumps(http_marker), encoding="utf-8"
    )

    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("{}\n", encoding="utf-8")
    session = SimpleNamespace(trace_path=trace_path, nex_mode=False)
    seen: dict[str, object] = {}

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, _ws, _prompt, _model, _timeout, **kwargs):
            assert kwargs["stdio_session"] is session
            return True, "agent trace", {"final_answer": "done"}

    @contextlib.contextmanager
    def fake_runtime(
        _scenario, _workspace, _tmp, _desktop_spec, http_spec, _backend, **_kwargs
    ):
        seen["http_spec"] = http_spec
        seen["active"] = True
        observations = tmp_path / "observations.jsonl"
        observations.write_text("{}\n", encoding="utf-8")
        try:
            yield tmp_path / "bin", {}, sys.executable, session, observations
        finally:
            seen["active"] = False

    def fake_deterministic_check(_scenario, _ws, _cfg, _trace, *, env_overrides=None):
        assert seen["active"] is True
        assert env_overrides == {run.STUB_OBSERVATIONS_ENV: str(tmp_path / "observations.jsonl")}
        seen["checked"] = True
        return run.DETERMINISTIC_CHECK_PREFIX + json.dumps({"passed": True})

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(run, "desktop_stdio_runtime", fake_runtime)
    monkeypatch.setattr(run, "deterministic_check_fact", fake_deterministic_check)
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    result = run.run_one(run.SkillSet("none", "", []), scenario, _run_one_args())

    assert result.ok is True
    assert result.metrics["deterministic_check"] == "passed"
    assert "runner_mcp_trace" not in result.metrics
    assert seen == {
        "http_spec": http_marker,
        "active": False,
        "checked": True,
    }


def test_terminal_route_maps_fixture_credential_only_into_trusted_server(
    tmp_path, monkeypatch
):
    scenario = tmp_path / "terminal-authenticated-dlt-api-ingestion"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    desktop_spec = {
        "server_name": "nxd-desktop",
        "profile_builder": "unused.py",
        "workflow_action_guard": True,
        "codex_app_server_route": "terminal_workflow_review_v1",
        "supported_agent_backends": ["claude"],
    }
    (fixtures / "desktop_stdio.json").write_text(json.dumps(desktop_spec), encoding="utf-8")
    (fixtures / "http_stub.json").write_text(json.dumps({"module": "stub"}), encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_tmp = tmp_path / "runtime"
    runtime_tmp.mkdir()
    bin_dir = runtime_tmp / "bin"
    bin_dir.mkdir()
    source_secret = "fixture-source-secret"
    monkeypatch.setattr(run, "http_stub_server", lambda *_args, **_kwargs: contextlib.nullcontext((None, None)))
    monkeypatch.setattr(
        run,
        "_http_stub_agent_env",
        lambda *_args, **_kwargs: {
            "NXD_EVAL_SOURCE_TOKEN": source_secret,
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": "caller=wrong",
        },
    )
    monkeypatch.setattr(run, "_desktop_runtime", lambda *_args: (bin_dir, {"PATH": str(bin_dir)}, sys.executable))
    monkeypatch.setattr(run, "_prepare_stdio_profile", lambda *_args: None)
    monkeypatch.setattr(run, "_stdio_activation_bundle", lambda *_args: None)

    with run.desktop_stdio_runtime(
        scenario, workspace, runtime_tmp, desktop_spec, {"module": "stub"}, "codex"
    ) as (_bin, agent_env, _python, session, _observations):
        assert agent_env.get("NXD_EVAL_SOURCE_TOKEN") is None
        assert session.server_env["NXD_EVAL_SOURCE_TOKEN"] == source_secret
        assert session.server_env["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"] == (
            "api-source=NXD_EVAL_SOURCE_TOKEN"
        )
        assert "caller=wrong" not in session.server_env["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"]
        assert source_secret not in session.config_path.read_text(encoding="utf-8")
        assert source_secret not in (session.root / "server-spec.json").read_text(encoding="utf-8")
        assert "NXD_EVAL_SOURCE_TOKEN" not in (session.root / "server-spec.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("nex_mode", "credential_is_trusted"), [(True, True), (False, False)]
)
def test_nex890_claude_runner_maps_source_credential_only_in_nex_mode(
    tmp_path, monkeypatch, nex_mode, credential_is_trusted
):
    """Claude must give the source token to the runner-owned supervisor only."""
    scenario = EVALS_DIR / "public" / "terminal-authenticated-dlt-api-ingestion"
    desktop_spec = json.loads(
        (scenario / "fixtures" / "desktop_stdio.json").read_text(encoding="utf-8")
    )
    desktop_spec["nex_mode"] = nex_mode
    http_spec = run.scenario_needs_http_stub(scenario)
    assert http_spec is not None

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_tmp = tmp_path / "runtime"
    runtime_tmp.mkdir()
    bin_dir = runtime_tmp / "bin"
    bin_dir.mkdir()

    monkeypatch.setattr(
        run,
        "http_stub_server",
        lambda *_args, **_kwargs: contextlib.nullcontext(
            ("http://127.0.0.1:43210", None)
        ),
    )
    monkeypatch.setattr(
        run,
        "_http_stub_trusted_server_env",
        lambda *_args: {"NXD_EVAL_SOURCE_TOKEN": "fixture-source-secret"},
    )
    monkeypatch.setattr(
        run,
        "_desktop_runtime",
        lambda *_args: (bin_dir, {"PATH": str(bin_dir)}, sys.executable),
    )
    monkeypatch.setattr(
        run,
        "_prepare_stdio_profile",
        lambda _scenario, _spec, _workspace, output, _python: output.write_text(
            "{}\n", encoding="utf-8"
        ),
    )
    monkeypatch.setattr(run, "_stdio_activation_bundle", lambda *_args: None)

    with run.desktop_stdio_runtime(
        scenario, workspace, runtime_tmp, desktop_spec, http_spec, "claude"
    ) as (_bin, agent_env, _python, session, _observations):
        assert session.nex_mode is nex_mode
        assert "NXD_EVAL_SOURCE_TOKEN" not in agent_env
        assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in agent_env
        token = session.server_env.get("NXD_EVAL_SOURCE_TOKEN")
        mapping = session.server_env.get("NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS")
        assert bool(token) is credential_is_trusted
        assert mapping == (
            "api-source=NXD_EVAL_SOURCE_TOKEN" if credential_is_trusted else None
        )
        if token:
            for path in session.root.iterdir():
                if path.is_file():
                    assert token not in path.read_text(encoding="utf-8")


def test_nex890_secret_leaks_fail_the_deterministic_grade():
    clean = {"passed": True, "failures": []}

    agent_leak = run._nex890_apply_secret_leak_failures(
        clean, agent_leak=True, bridge_leak=False
    )
    bridge_leak = run._nex890_apply_secret_leak_failures(
        clean, agent_leak=False, bridge_leak=True
    )

    assert agent_leak["passed"] is False
    assert agent_leak["failures"] == [
        "redaction/protected-secret-in-agent-artifacts"
    ]
    assert bridge_leak["passed"] is False
    assert bridge_leak["failures"] == [
        "redaction/source-credential-in-bridge-message"
    ]
    checker_error = run._nex890_apply_secret_leak_failures(
        {
            "passed": False,
            "failures": ["runner/in-process-checker-error"],
            "infrastructure_error": "checker unavailable",
        },
        agent_leak=True,
        bridge_leak=False,
    )
    assert checker_error["passed"] is False
    assert "infrastructure_error" not in checker_error
    assert checker_error["secondary_infrastructure_error"] == "checker unavailable"


def test_nex890_followup_turns_are_rejected_before_preflight(tmp_path, monkeypatch):
    scenario = tmp_path / "terminal-authenticated-dlt-api-ingestion"
    scenario.mkdir()
    (scenario / "checks.json").write_text(
        json.dumps({"turns": [{"text": "Continue the task."}]}),
        encoding="utf-8",
    )
    (scenario / "prompt.md").write_text("# Task\n\n## Task for the agent\nDo it.\n", encoding="utf-8")
    backend = SimpleNamespace(name="claude")
    monkeypatch.setattr(run, "get_agent_backend", lambda _name: backend)
    monkeypatch.setattr(
        run,
        "_nex_security_preflight",
        lambda: (_ for _ in ()).throw(AssertionError("preflight must not run")),
    )

    result = run.run_one(
        run.SkillSet("none", "", []),
        scenario,
        SimpleNamespace(agent_backend="claude", agent_effort=""),
    )

    assert result.metrics["status"] == "UNSUPPORTED"
    assert "one turn only" in result.metrics["reason"]


def test_nex_preflight_retries_after_a_failed_canary(monkeypatch):
    monkeypatch.setattr(run, "_NEX_PREFLIGHT_RESULTS", {})
    monkeypatch.setattr(run.shutil, "which", lambda _name: "/tmp/fake-claude")
    monkeypatch.setattr(
        run.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="Claude Code 2.1.test", stderr=""
        ),
    )
    monkeypatch.setattr(run, "get_agent_backend", lambda _name: eb.ClaudeBackend())
    outcomes = iter([(False, "transient canary failure"), (True, "passed")])
    calls = []

    def canary(_executable):
        calls.append(True)
        return next(outcomes)

    monkeypatch.setattr(run, "_run_nex_security_canary", canary)

    assert run._nex_security_preflight() == (False, "transient canary failure")
    assert run._nex_security_preflight() == (True, "passed")
    assert run._nex_security_preflight() == (True, "passed")
    assert len(calls) == 2


def test_nex890_redaction_detects_secret_after_truncated_tool_result():
    """A token past the judge trace cap must still fail the raw-stream audit."""
    token = "synthetic-source-token-after-trace-cap"
    stream = json.dumps({
        "type": "user",
        "message": {
            "content": [{
                "type": "tool_result",
                "content": ("x" * eb.TOOL_RESULT_HEAD_CHARS) + token,
            }]
        },
    }) + "\n" + json.dumps({"type": "result", "result": "finished"}) + "\n"

    trace, _metrics = eb.ClaudeBackend._trace_from_stream(stream)
    assert token not in trace

    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"],
        nex_mode=True,
        server_env={
            "NXD_EVAL_SOURCE_TOKEN": token,
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": "api-source=NXD_EVAL_SOURCE_TOKEN",
        },
    )
    redacted_stream, raw_stream_leaked = session.redact_nex_text(stream)
    assert raw_stream_leaked is True
    assert token not in redacted_stream

    safe_trace, safe_metrics, leaked = run._redact_agent_artifacts(
        trace, {"nex_agent_stream_secret_leak": raw_stream_leaked}, (token,)
    )
    assert leaked is True
    assert token not in safe_trace
    assert token not in json.dumps(safe_metrics)


def test_runtime_secret_redaction_cleans_metric_keys():
    token = "synthetic-secret-as-metric-key"

    safe_trace, safe_metrics, leaked = run._redact_agent_artifacts(
        "clean trace", {token: "unexpected output"}, (token,)
    )

    assert leaked is True
    assert token not in safe_trace
    assert token not in json.dumps(safe_metrics)
    assert "<redacted>" in safe_metrics


@pytest.mark.parametrize("leak_kind", [None, "agent", "bridge"])
def test_nex890_run_one_keeps_trusted_source_credential_out_of_claude_env(
    tmp_path, monkeypatch, leak_kind
):
    scenario = EVALS_DIR / "public" / "terminal-authenticated-dlt-api-ingestion"
    token = "synthetic-source-credential-run-one"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    seen = {}

    class FakeSession:
        nex_mode = True

        def __init__(self, server_env):
            self.server_env = server_env

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def finish_nex_cell(self):
            return [], None

        def result_metrics(self):
            return {"nex_bridge_secret_leak": leak_kind == "bridge"}

        def verify_nex_security_files(self):
            pass

        def nex_file_snapshots(self):
            return {}

    class FakeEvidenceModule:
        @staticmethod
        def freeze_observations():
            return []

    evidence = run._NexHTTPStubEvidence(
        FakeEvidenceModule(), object(), object(), lambda *_args: None
    )

    class FakeClaudeBackend:
        name = "claude"
        supports_multi_turn = False

        def check_dependencies(self):
            pass

        def run_agent(self, _workspace, _prompt, model, _timeout, **kwargs):
            seen["model"] = model
            seen["agent_env"] = dict(kwargs["env_overrides"])
            if leak_kind is None:
                return True, "[assistant] finished", {"final_answer": "finished"}
            return False, "[assistant] partial", {
                "status": "INCOMPLETE",
                "error": "agent stopped early",
                "nex_agent_stream_secret_leak": leak_kind == "agent",
            }

    class FakeJudgeBackend:
        def check_dependencies(self):
            pass

    def fake_run_judge(*_args, **kwargs):
        seen["judge_effort"] = kwargs["effort"]
        return {"overall_pass": True}

    def fake_desktop_stdio_session(*_args, **kwargs):
        server_env = kwargs["trusted_server_env"]
        seen["server_env"] = dict(server_env)
        seen["nex_expected_base_url"] = kwargs["nex_expected_base_url"]
        return bin_dir, {"PATH": str(bin_dir)}, sys.executable, FakeSession(server_env)

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeClaudeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: FakeJudgeBackend())
    monkeypatch.setattr(run, "_nex_security_preflight", lambda: (True, "passed"))
    monkeypatch.setattr(
        run, "_load_nex890_checker",
        lambda *_args: lambda *_checks: {"passed": True, "failures": []},
    )
    monkeypatch.setattr(
        run, "_http_stub_trusted_server_env",
        lambda *_args: {"NXD_EVAL_SOURCE_TOKEN": token},
    )
    monkeypatch.setattr(
        run, "http_stub_server",
        lambda *_args, **_kwargs: contextlib.nullcontext(("http://127.0.0.1:43210", evidence)),
    )
    monkeypatch.setattr(
        run,
        "_desktop_runtime",
        lambda *_args: (bin_dir, {}, sys.executable),
    )
    monkeypatch.setattr(run, "_desktop_stdio_session", fake_desktop_stdio_session)
    monkeypatch.setattr(run, "run_judge", fake_run_judge)

    args = _run_one_args()
    args.agent_backend = "claude"
    args.agent_model = "sonnet"
    args._judge_effort_explicit = True
    result = run.run_one(run.SkillSet("none", "", []), scenario, args)

    assert result.ok is True
    assert result.verdict["overall_pass"] is (leak_kind is None)
    assert seen["model"] == "opus"
    assert seen["server_env"] == {
        "NXD_EVAL_SOURCE_TOKEN": token,
        "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": "api-source=NXD_EVAL_SOURCE_TOKEN",
    }
    assert "NXD_EVAL_SOURCE_TOKEN" not in seen["agent_env"]
    assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in seen["agent_env"]
    assert token not in json.dumps(result.metrics)
    if leak_kind is None:
        assert seen["judge_effort"] == "medium"
    else:
        assert "judge_effort" not in seen
        assert result.metrics["status"] == "FAILED"
        assert result.metrics["agent_completion_status"] == "INCOMPLETE"
        assert result.metrics["deterministic_check"] == "failed"
        assert any("PROTECTED CREDENTIAL EXPOSURE: FAIL" in fact for fact in result.facts)


def test_incomplete_terminal_route_never_judges_or_caches(tmp_path, monkeypatch):
    scenario = tmp_path / "terminal-authenticated-dlt-api-ingestion"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text(
        "# Scenario\n\n## Task for the agent\n\nImplement the task.\n", encoding="utf-8"
    )
    (scenario / "checks.json").write_text("{}\n", encoding="utf-8")
    (fixtures / "desktop_stdio.json").write_text(
        json.dumps({
            "codex_app_server_route": "terminal_workflow_review_v1",
            "workflow_action_guard": True,
            "supported_agent_backends": ["claude"],
        }),
        encoding="utf-8",
    )
    trace_path = tmp_path / "mcp-trace.jsonl"
    trace_path.write_text("{}\n", encoding="utf-8")
    session = SimpleNamespace(trace_path=trace_path, nex_mode=False)
    cache_dir = tmp_path / "cache"
    cleanup_called = []

    class IncompleteBackend:
        name = "claude"
        supports_multi_turn = False

        def check_dependencies(self):
            pass

        def run_agent(self, *_args, **_kwargs):
            return False, "partial route output", {
                "error": "review evidence incomplete", "timed_out": True
            }

    class FakeJudgeBackend:
        def check_dependencies(self):
            pass

    @contextlib.contextmanager
    def fake_runtime(*_args, **_kwargs):
        try:
            yield tmp_path / "bin", {}, sys.executable, session, None
        finally:
            cleanup_called.append(True)

    judge_calls = []
    monkeypatch.setattr(run, "get_agent_backend", lambda _name: IncompleteBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: FakeJudgeBackend())
    monkeypatch.setattr(run, "desktop_stdio_runtime", fake_runtime)
    monkeypatch.setattr(run, "_nex_security_preflight", lambda: (True, "passed"))
    monkeypatch.setattr(run, "_load_nex890_checker", lambda *_args: object())
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: judge_calls.append(True))

    result = run.run_one(
        run.SkillSet("none", "", []),
        scenario,
        SimpleNamespace(
            agent_backend="claude", judge_backend="codex", agent_model="opus",
            judge_model="sol", agent_effort="medium", judge_effort="medium",
            _agent_effort_explicit=False, _judge_effort_explicit=False,
            _judge_backend_explicit=False, _judge_model_explicit=False,
            agent_timeout=1, judge_timeout=1, docs_base="https://docs.example/",
            cache_dir=str(cache_dir),
        ),
    )
    assert result.ok is False
    assert result.error == "review evidence incomplete"
    assert judge_calls == []
    assert not cache_dir.exists() or list(cache_dir.iterdir()) == []
    assert cleanup_called == [True]


def test_codex_app_server_route_fails_closed_when_source_audit_markers_are_requested():
    backend = eb.CodexBackend()
    session = SimpleNamespace(
        codex_app_server_route="terminal_workflow_review_v1",
        workflow_action_guard=True,
        result_metrics=lambda: {"agent_status": "not_started"},
    )
    ok, trace, metrics = backend.run_agent(
        Path("/workspace"),
        "task",
        "gpt-6-luna",
        30,
        source_audit_markers=[("marker-1", "protected value")],
        stdio_session=session,
    )
    assert ok is False
    assert trace == ""
    assert "source-isolation markers without raw marker audit" in metrics["error"]
    assert metrics["agent_status"] == "not_started"


def test_codex_terminal_route_audit_requires_version_receiver_and_matching_reader_trace():
    audit = {
        "review_verified": True,
        "codex_version": "codex-cli 0.155.1",
        "spawned_receiver_ids": ["receiver-1"],
        "review_receiver_ids": ["receiver-1"],
        "review_report_count": 1,
        "child_reader_paths": ["/capture/transform.py"],
        "child_reader_receivers": ["receiver-1"],
        "child_success_receivers": ["receiver-1"],
        "child_message_receivers": ["receiver-1"],
        "successful_root_tools": [
            "get_workflow_capabilities", "check_data_product", "prepare_workflow",
            "advance_workflow", "inspect_workflow", "inspect_run",
            "list_data_products", "resume_data_product", "describe_models",
            "run_semantic_query", "export_data_product",
        ],
        "completion_tools": [
            "advance_workflow", "inspect_workflow", "inspect_run",
            "list_data_products", "resume_data_product", "describe_models",
            "run_semantic_query", "export_data_product",
        ],
        "completion_verified": True,
        "violations": [],
        "unattributed_events": 0,
        "pending_child_event_count": 0,
        "turn_count": 5,
    }

    assert eb.CodexBackend._terminal_route_audit_evidence(
        audit, "codex-cli 0.155.1", {"/capture/transform.py"}
    ) == (True, True)
    assert eb.CodexBackend._terminal_route_audit_evidence(
        audit, "codex-cli 0.155.1", {"/capture/other.py"}
    ) == (False, False)

    wrong_version = {**audit, "codex_version": "codex-cli other"}
    assert not eb.CodexBackend._terminal_route_audit_evidence(
        wrong_version, "codex-cli 0.155.1", {"/capture/transform.py"}
    )[0]
    unknown_receiver = {**audit, "spawned_receiver_ids": ["other-receiver"]}
    assert not eb.CodexBackend._terminal_route_audit_evidence(
        unknown_receiver, "codex-cli 0.155.1", {"/capture/transform.py"}
    )[0]
    missing_completion = {**audit, "completion_verified": False}
    assert not eb.CodexBackend._terminal_route_audit_evidence(
        missing_completion, "codex-cli 0.155.1", {"/capture/transform.py"}
    )[0]


def test_codex_terminal_route_reader_trace_parser_requires_successful_proxy_response(
    tmp_path,
):
    trace = tmp_path / "mcp-trace.jsonl"
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "read_review_input",
        "arguments": {"path": "/capture/transform.py", "operation": "read"},
    }}
    response = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "source"}]}}
    trace.write_text(
        json.dumps({"direction": "request", "message": request}) + "\n"
        + json.dumps({"direction": "response", "message": response,
                      "synthetic": True, "review_reader": True}) + "\n",
        encoding="utf-8",
    )
    assert eb.CodexBackend._review_reader_trace_paths(trace) == {
        "/capture/transform.py"
    }
    response["result"]["isError"] = True
    trace.write_text(
        json.dumps({"direction": "request", "message": request}) + "\n"
        + json.dumps({"direction": "response", "message": response,
                      "synthetic": True, "review_reader": True}) + "\n",
        encoding="utf-8",
    )
    assert eb.CodexBackend._review_reader_trace_paths(trace) == set()


def test_route_audit_reader_recovers_events_after_last_state_checkpoint(tmp_path):
    audit_path = tmp_path / "codex-app-server-audit.json"
    audit_path.write_text(json.dumps({"turn_count": 1, "event_count": 0}), encoding="utf-8")
    event_path = tmp_path / "codex-app-server-events.jsonl"
    event_path.write_text(
        json.dumps({"event": "item.completed", "attribution": "root"}) + "\n",
        encoding="utf-8",
    )
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write('{"truncated":')

    audit = eb.CodexBackend._read_route_audit(audit_path)

    assert audit["turn_count"] == 1
    assert audit["event_count"] == 1
    assert audit["events"] == [{"event": "item.completed", "attribution": "root"}]


def test_codex_exec_stdio_nonzero_exit_uses_collected_text_output(tmp_path, monkeypatch):
    calls = []

    class FailedProcess:
        pid = 123
        returncode = 2
        stdout = object()
        stderr = object()

        def communicate(self, **_kwargs):
            return "", "codex failed during stdio startup"

    class Session:
        codex_app_server_route = None
        server_name = "nxd-desktop"
        root = tmp_path / "session"
        config_path = tmp_path / "session" / "mcp-config.json"

        def ensure_started(self):
            return None

        def attach_process(self, process):
            assert process is fake_process

        def record_agent(self, **kwargs):
            calls.append(kwargs)

        def result_metrics(self):
            return {}

    fake_process = FailedProcess()
    monkeypatch.setattr(eb.subprocess, "Popen", lambda *_args, **_kwargs: fake_process)
    backend = eb.CodexBackend()
    ok, _trace, metrics = backend.run_agent(
        tmp_path, "task", "gpt-6-luna", 10,
        executable="/bin/true", stdio_session=Session(),
    )

    assert ok is False
    assert "codex failed during stdio startup" in metrics["error"]
    assert calls == [{"status": "failed", "error": metrics["error"]}]


def test_codex_route_timeout_kills_adapter_after_grace_and_keeps_partial_evidence(
    tmp_path, monkeypatch
):
    audit = {"codex_version": "codex-cli 0.155.1", "events": [{"event": "partial"}]}
    partial = json.dumps({"result": {
        "agent_message": "partial answer", "transcript_delta": "partial trace",
        "input_tokens": 4, "output_tokens": 6, "provider_model_calls": 2,
        "terminal_result_count": 1,
    }, "route_audit": audit}) + "\n"
    communicate_timeouts = []
    signals = []

    class Pipe:
        closed = False

        def close(self):
            self.closed = True

    class TimedOutProcess:
        pid = 321
        returncode = None
        stdout = Pipe()
        stderr = Pipe()

        def communicate(self, **kwargs):
            communicate_timeouts.append(kwargs.get("timeout"))
            raise subprocess.TimeoutExpired(
                "adapter", kwargs.get("timeout"), output=partial.encode(),
                stderr=b"partial adapter diagnostic",
            )

    process = TimedOutProcess()
    session_calls = []
    session_root = tmp_path / "session"
    session_root.mkdir()
    trace_path = tmp_path / "mcp-trace.jsonl"
    trace_path.write_text("{}\n", encoding="utf-8")

    class Session:
        codex_app_server_route = "terminal_workflow_review_v1"
        workflow_action_guard = True
        root = session_root
        config_path = tmp_path / "mcp-config.json"
        server_name = "nxd-desktop"
        desktop_supervisor = Path("/bin/true")
        desktop_python = Path(sys.executable)
        supervisor_data_dir = tmp_path
        idle_timeout_seconds = 180

        def ensure_started(self):
            return None

        def attach_process(self, child):
            assert child is process

        def record_agent(self, **kwargs):
            session_calls.append(kwargs)

        def result_metrics(self):
            return {}

    Session.trace_path = trace_path

    monkeypatch.setattr(
        eb.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="codex-cli 0.155.1\n", stderr=""
        ),
    )
    monkeypatch.setattr(eb.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(eb.os, "kill", lambda pid, sig: signals.append(("pid", pid, sig)))
    monkeypatch.setattr(eb.os, "killpg", lambda pid, sig: signals.append(("pg", pid, sig)))

    ok, trace, metrics = eb.CodexBackend()._run_codex_app_server_route(
        tmp_path, "task", "gpt-6-luna", 1, effort="medium",
        env_overrides={}, path_prepend=None, executable="/bin/true",
        source_audit_markers=None, stdio_session=Session(),
    )

    assert ok is False
    assert trace == "partial trace"
    assert metrics["timed_out"] is True
    assert metrics["final_answer"] == "partial answer"
    assert metrics["input_tokens"] == 4
    assert metrics["output_tokens"] == 6
    assert metrics["provider_model_calls"] == 2
    assert metrics["route_audit"] == audit
    assert communicate_timeouts == [10, 8, 3]
    assert signals == [
        ("pid", 321, eb.signal.SIGTERM),
        ("pid", 321, eb.signal.SIGKILL),
        ("pg", 321, eb.signal.SIGKILL),
    ]
    assert session_calls == [{
        "status": "timeout",
        "error": "Codex app-server route exceeded its outer wall-clock deadline",
    }]


def test_a_leaked_fixture_literal_is_reported_and_never_cached(tmp_path, monkeypatch):
    """A redaction failure must not be laundered by the agent cache.

    What lands in the cache is the REDACTED transcript, so a later cache hit
    finds no literal and would replay the run as clean — turning a real
    redaction failure into a pass on the second run.
    """
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    (scenario / "checks.json").write_text(
        json.dumps({
            "deterministic_check": {
                "script": "unused.py",
                "deps": [],
                "redaction_markers": ["synthetic-secret-marker"],
            }
        }),
        encoding="utf-8",
    )
    (fixtures / "desktop_stdio.json").write_text("{}\n", encoding="utf-8")

    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("{}\n", encoding="utf-8")
    session = SimpleNamespace(trace_path=trace_path, nex_mode=False)

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            return True, "echoed synthetic-secret-marker", {"final_answer": "done"}

    @contextlib.contextmanager
    def fake_runtime(
        _scenario, _workspace, _tmp, _desktop_spec, _http_spec, _backend, **_kwargs
    ):
        yield tmp_path / "bin", {}, sys.executable, session, None

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(run, "desktop_stdio_runtime", fake_runtime)
    monkeypatch.setattr(
        run, "deterministic_check_fact",
        lambda *_args, **_kwargs: run.DETERMINISTIC_CHECK_PREFIX + json.dumps({"passed": True}),
    )
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    cache_dir = tmp_path / "cache"
    args = _run_one_args()
    args.cache_dir = str(cache_dir)

    result = run.run_one(run.SkillSet("none", "", []), scenario, args)

    assert "synthetic-secret-marker" not in result.transcript
    assert "<redacted>" in result.transcript
    assert any("AGENT FIXTURE REDACTION: FAIL" in fact for fact in result.facts)
    assert not cache_dir.exists() or not list(cache_dir.glob("agent-*.json"))


def test_marker_redaction_applies_to_a_fresh_non_stdio_run(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    marker = "synthetic-non-stdio-marker"
    (scenario / "checks.json").write_text(
        json.dumps({
            "deterministic_check": {
                "script": "unused.py",
                "deps": [],
                "redaction_markers": [marker],
            }
        }),
        encoding="utf-8",
    )

    calls = 0

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            return True, f"echoed {marker}", {"final_answer": marker}

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(
        run,
        "deterministic_check_fact",
        lambda *_args, **_kwargs: run.DETERMINISTIC_CHECK_PREFIX + json.dumps(
            {"passed": True}
        ),
    )
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    cache_dir = tmp_path / "cache"
    args = _run_one_args()
    args.cache_dir = str(cache_dir)

    first = run.run_one(run.SkillSet("none", "", []), scenario, args)
    second = run.run_one(run.SkillSet("none", "", []), scenario, args)

    for result in (first, second):
        assert marker not in result.transcript
        assert "<redacted>" in result.transcript
        assert any("AGENT FIXTURE REDACTION: FAIL" in fact for fact in result.facts)
    assert calls == 2
    assert not cache_dir.exists() or not list(cache_dir.glob("agent-*.json"))


def test_run_one_combined_http_teardown_is_not_desktop_setup(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    (scenario / "checks.json").write_text("{}\n", encoding="utf-8")
    (fixtures / "desktop_stdio.json").write_text("{}\n", encoding="utf-8")
    (fixtures / "http_stub.json").write_text(
        json.dumps({"module": "broken", "endpoint_file": "ENDPOINT_URL"}),
        encoding="utf-8",
    )
    (fixtures / "broken.py").write_text(
        "def start_server():\n"
        "    return object(), 43211, object()\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    raise RuntimeError('authorization=stop-secret')\n",
        encoding="utf-8",
    )
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("{}\n", encoding="utf-8")

    class FakeSession:
        def __init__(self, trace):
            self.trace_path = trace
            self.nex_mode = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            return True, "agent trace", {"final_answer": "done"}

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(
        run,
        "_desktop_stdio_session",
        lambda *_args, **_kwargs: (
            tmp_path / "bin", {}, sys.executable, FakeSession(trace_path)
        ),
    )
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    result = run.run_one(run.SkillSet("none", "", []), scenario, _run_one_args())

    assert result.ok is False
    assert result.error == (
        "http stub teardown failed: RuntimeError: authorization=<redacted>"
    )
    assert "stop-secret" not in result.error


def test_deterministic_checker_receives_observations_without_process_leak(tmp_path):
    """The request log is visible to the verifier, never to the parent runner."""
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    checker = fixtures / "check.py"
    checker.write_text(
        "import os, sys\n"
        "expected = os.environ.get('EXPECTED_LOG')\n"
        "actual = os.environ.get('NXD_STUB_OBSERVATIONS')\n"
        "if actual != expected:\n"
        "    print('FAIL observation path missing')\n"
        "    raise SystemExit(1)\n"
        "print('ALL CHECKS PASSED')\n",
        encoding="utf-8",
    )
    log = tmp_path / "observations.jsonl"
    log.write_text("{}\n", encoding="utf-8")
    before = os.environ.get(run.STUB_OBSERVATIONS_ENV)

    fact = run.deterministic_check_fact(
        scenario,
        tmp_path / "workspace",
        {"script": "check.py", "deps": []},
        env_overrides={
            run.STUB_OBSERVATIONS_ENV: str(log),
            "EXPECTED_LOG": str(log),
        },
    )

    assert run.deterministic_check_passed([fact])
    assert os.environ.get(run.STUB_OBSERVATIONS_ENV) == before


def test_no_log_deterministic_checker_does_not_inherit_parent_observations(
    tmp_path, monkeypatch
):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "check.py").write_text(
        "import os\n"
        f"if os.environ.get({run.STUB_OBSERVATIONS_ENV!r}):\n"
        "    print('FAIL inherited observation path')\n"
        "    raise SystemExit(1)\n"
        "print('ALL CHECKS PASSED')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(run.STUB_OBSERVATIONS_ENV, str(tmp_path / "parent.jsonl"))

    fact = run.deterministic_check_fact(
        scenario, tmp_path / "workspace", {"script": "check.py", "deps": []}
    )

    assert run.deterministic_check_passed([fact])


def test_no_log_desktop_verifier_does_not_inherit_parent_observations(
    tmp_path, monkeypatch
):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "check.py").write_text("", encoding="utf-8")
    captured: dict[str, object] = {}

    class _Proc:
        returncode, stdout, stderr = 0, '{"passed": true}\n', ""

    def fake_run(_cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _Proc()

    monkeypatch.setenv(run.STUB_OBSERVATIONS_ENV, str(tmp_path / "parent.jsonl"))
    monkeypatch.setattr(run.subprocess, "run", fake_run)

    fact = run.desktop_harness_fact(
        scenario, tmp_path / "workspace", sys.executable, "workflow", tmp_path, {},
        verifier="check.py",
    )

    assert json.loads(fact.split(": ", 1)[1])["passed"] is True
    assert run.STUB_OBSERVATIONS_ENV not in captured["env"]


def test_http_only_deterministic_check_runs_after_stub_teardown(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    (scenario / "checks.json").write_text(
        json.dumps({"deterministic_check": {"script": "unused.py", "deps": []}}),
        encoding="utf-8",
    )
    (fixtures / "http_stub.json").write_text(
        json.dumps({"module": "stub", "endpoint_file": "ENDPOINT_URL"}),
        encoding="utf-8",
    )
    (fixtures / "stub.py").write_text("", encoding="utf-8")
    seen: dict[str, object] = {}

    @contextlib.contextmanager
    def fake_http_stub(*_args, **_kwargs):
        seen["active"] = True
        try:
            yield "http://127.0.0.1:1", None
        finally:
            seen["active"] = False
            seen["teardown"] = True

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            return True, "agent trace", {"final_answer": "done"}

    def fake_deterministic_check(*_args, **_kwargs):
        assert seen == {"active": False, "teardown": True}
        return run.DETERMINISTIC_CHECK_PREFIX + json.dumps({"passed": True})

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(run, "http_stub_server", fake_http_stub)
    monkeypatch.setattr(run, "deterministic_check_fact", fake_deterministic_check)
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    result = run.run_one(run.SkillSet("none", "", []), scenario, _run_one_args())

    assert result.ok is True
    assert result.metrics["deterministic_check"] == "passed"


def test_http_teardown_failure_preserves_evidence_and_skips_cache(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    (scenario / "checks.json").write_text(
        json.dumps({"workspace_files": {"files": []}}), encoding="utf-8"
    )
    (fixtures / "http_stub.json").write_text(
        json.dumps({"module": "stub", "endpoint_file": "ENDPOINT_URL"}),
        encoding="utf-8",
    )
    (fixtures / "stub.py").write_text("", encoding="utf-8")

    @contextlib.contextmanager
    def failing_http_stub(*_args, **_kwargs):
        yield "http://127.0.0.1:1", None
        raise run.HttpStubTeardownError("authorization=teardown-secret")

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            return True, "agent trace", {"final_answer": "done", "kept": 7}

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(run, "http_stub_server", failing_http_stub)
    monkeypatch.setattr(run, "workspace_files_fact", lambda *_args: "WORKSPACE FACT")
    monkeypatch.setattr(
        run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True, "summary": "graded"}
    )
    cache_dir = tmp_path / "cache"
    args = _run_one_args()
    args.cache_dir = str(cache_dir)

    result = run.run_one(run.SkillSet("none", "", []), scenario, args)

    assert result.ok is False
    assert result.error == (
        "http stub teardown failed: authorization=<redacted>"
    )
    assert result.transcript == "agent trace"
    assert result.metrics["kept"] == 7
    assert result.facts == ["WORKSPACE FACT"]
    assert result.verdict == {"overall_pass": True, "summary": "graded"}
    assert not cache_dir.exists() or not list(cache_dir.glob("agent-*.json"))

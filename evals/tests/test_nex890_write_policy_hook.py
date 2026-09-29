from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


HOOK = Path(__file__).parents[1] / "nex890_write_policy_hook.py"
if str(HOOK.parent) not in sys.path:
    sys.path.insert(0, str(HOOK.parent))
hook = importlib.import_module("nex890_write_policy_hook")


def _run_hook(tmp_path: Path, tool_name: str, tool_input: dict) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    workspace = tmp_path / "workspace"
    private_root = workspace / ".runner-private"
    workspace.mkdir()
    private_root.mkdir()
    return subprocess.run(
        [
            sys.executable,
            str(HOOK),
            "--workspace",
            str(workspace),
            "--private-root",
            str(private_root),
        ],
        input=json.dumps({"tool_name": tool_name, "tool_input": tool_input}),
        capture_output=True,
        text=True,
        check=False,
    )


def test_glob_rejects_absolute_pattern_without_path_override(tmp_path):
    result = _run_hook(
        tmp_path,
        "Glob",
        {"pattern": "/private/tmp/outside-review/**"},
    )

    assert result.returncode == 2
    assert "inside the workspace" in result.stderr


def test_glob_and_grep_default_to_workspace_for_relative_patterns(tmp_path):
    glob = _run_hook(tmp_path / "glob", "Glob", {"pattern": "**/*.py"})
    grep = _run_hook(tmp_path / "grep", "Grep", {"pattern": "secret|token"})

    assert glob.returncode == 0
    assert grep.returncode == 0


def test_home_relative_paths_are_rejected_for_reads_writes_and_globs(tmp_path):
    cases = (
        ("Read", {"file_path": "~/.ssh/id_rsa"}),
        ("Write", {"file_path": "~/.zshrc", "content": "must not be written"}),
        ("Glob", {"pattern": "~/.ssh/**"}),
    )

    for tool_name, tool_input in cases:
        result = _run_hook(tmp_path / tool_name, tool_name, tool_input)

        assert result.returncode == 2
        assert "home-relative paths" in result.stderr or "inside the workspace" in result.stderr


def test_fixed_reasons_are_distinct_and_never_substrings_of_each_other():
    assert len(set(hook.ALL_REASONS)) == len(hook.ALL_REASONS)
    for reason in hook.ALL_REASONS:
        assert len(reason) < 500
        for other in hook.ALL_REASONS:
            if other is not reason:
                assert reason not in other


def _write_probe(tmp_path: Path, file_path: str) -> subprocess.CompletedProcess[str]:
    """Run one Write through the hook with the preflight's root layout."""
    workspace = tmp_path / "workspace"
    private_root = workspace / ".runner-private"
    plugin_root = workspace / ".canary-plugin"
    return subprocess.run(
        [
            sys.executable, "-I", str(HOOK),
            "--workspace", str(workspace),
            "--private-root", str(private_root),
            "--plugin-root", str(plugin_root),
        ],
        input=json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": "DENIED_CANARY"},
        }),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("relative", "reason"),
    [
        ("outside/outside-denied.txt", "REASON_WRITE_OUTSIDE"),
        ("workspace/.runner-private/private-denied.txt", "REASON_WRITE_PROTECTED"),
        ("workspace/.canary-plugin/plugin-denied.txt", "REASON_WRITE_PROTECTED"),
        ("workspace/.claude/denied-canary.txt", "REASON_WRITE_CLAUDE"),
        ("workspace/.ClAuDe/denied-canary.txt", "REASON_WRITE_CLAUDE"),
        ("workspace/.mcp.json", "REASON_WRITE_MCP"),
        ("workspace/.MCP.JSON", "REASON_WRITE_MCP"),
    ],
)
def test_write_denials_print_exactly_one_fixed_reason(tmp_path, relative, reason):
    for path in (tmp_path / "workspace" / ".runner-private", tmp_path / "workspace" / ".canary-plugin"):
        path.mkdir(parents=True, exist_ok=True)
    result = _write_probe(tmp_path, str(tmp_path / relative))

    assert result.returncode == 2
    assert result.stderr == getattr(hook, reason) + "\n"


def test_write_inside_workspace_is_allowed_silently(tmp_path):
    (tmp_path / "workspace" / ".runner-private").mkdir(parents=True)
    result = _write_probe(tmp_path, str(tmp_path / "workspace" / "parent-inside.txt"))

    assert result.returncode == 0
    assert result.stderr == ""


def test_case_variant_workspace_sibling_follows_filesystem_identity(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / ".runner-private").mkdir(parents=True)
    sibling = tmp_path / "WORKSPACE"
    # On a case-insensitive filesystem this spelling already exists as the
    # workspace itself; on a case-sensitive one it is a distinct directory.
    sibling.mkdir(exist_ok=True)
    target = sibling / "case-variant.txt"

    result = _write_probe(tmp_path, str(target))

    if os.path.samefile(sibling, workspace):
        assert (result.returncode, result.stderr) == (0, "")
    else:
        assert (result.returncode, result.stderr) == (2, hook.REASON_WRITE_OUTSIDE + "\n")
    assert not target.exists()


def test_casefold_match_alone_never_proves_workspace_containment(tmp_path, monkeypatch):
    # Neither spelling exists, so only the filesystem probe can equate them.
    root = os.path.join(str(tmp_path), "missing", "workspace")
    variant = os.path.join(str(tmp_path), "missing", "WORKSPACE", "child.txt")
    assert hook._inside(os.path.join(root, "child.txt"), root)

    monkeypatch.setattr(hook, "_folds_case", lambda _root: False)
    assert not hook._inside(variant, root)
    monkeypatch.setattr(hook, "_folds_case", lambda _root: True)
    assert hook._inside(variant, root)
    # Unicode folding differs between filesystems, so it never matches.
    assert not hook._inside(
        os.path.join(str(tmp_path), "STRASSE", "x"), os.path.join(str(tmp_path), "straße")
    )


@pytest.mark.parametrize(
    "relative",
    [".RUNNER-PRIVATE/private-denied.txt", ".Canary-Plugin/plugin-denied.txt"],
)
def test_case_variant_under_missing_protected_root_is_denied_on_any_filesystem(
    tmp_path, relative
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Neither protected root exists yet, and the workspace ancestor's case
    # behavior need not apply to entries created inside it, so the protected
    # boundary fails closed whether or not this filesystem folds case.
    target = workspace / relative

    result = _write_probe(tmp_path, str(target))

    assert (result.returncode, result.stderr) == (2, hook.REASON_WRITE_PROTECTED + "\n")
    assert list(workspace.iterdir()) == []
    assert not target.exists()


def test_protected_fold_only_blocks_while_the_root_is_missing(tmp_path):
    root = tmp_path / "workspace" / ".runner-private"
    variant = tmp_path / "workspace" / ".RUNNER-PRIVATE"
    root_path = hook._canonical(root)
    variant_file = os.path.join(hook._canonical(variant), "x")

    assert hook._inside_protected(variant_file, root_path)
    # Unicode folding may block a missing protected root ...
    assert hook._inside_protected(
        os.path.join(str(tmp_path), "STRASSE", "x"), os.path.join(str(tmp_path), "straße")
    )
    assert not hook._inside_protected(
        os.path.join(hook._canonical(tmp_path / "workspace"), "other", "x"), root_path
    )

    # ... but an existing root is settled by filesystem identity alone.
    root.mkdir(parents=True)
    variant_file = os.path.join(hook._canonical(variant), "x")
    same = variant.exists() and os.path.samefile(variant, root)
    assert hook._inside_protected(variant_file, hook._canonical(root)) is same


def test_canonical_preserves_resolved_path_case(tmp_path):
    target = tmp_path / "MixedCase" / "Leaf.TXT"

    assert hook._canonical(target).endswith(os.path.join("MixedCase", "Leaf.TXT"))


def test_literal_and_absolute_home_writes_use_their_own_fixed_reasons(tmp_path):
    (tmp_path / "workspace" / ".runner-private").mkdir(parents=True)
    literal = _write_probe(tmp_path, "~/.nex890-home-preflight-test/home-alias-denied.txt")
    absolute = _write_probe(
        tmp_path, str(Path.home() / ".nex890-home-preflight-test" / "home-alias-denied.txt")
    )

    assert (literal.returncode, literal.stderr) == (2, hook.REASON_HOME_RELATIVE + "\n")
    assert (absolute.returncode, absolute.stderr) == (2, hook.REASON_WRITE_OUTSIDE + "\n")

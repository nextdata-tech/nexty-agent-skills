"""Protected evaluator fixtures need evidence beyond being absent from a workspace.

These tests keep the source-isolation contract local and cheap: a fake wrapper
answers its preflight probe, while stub backends model clean and contaminated raw
streams without spending an agent call.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path


EVALS_DIR = Path(__file__).resolve().parents[1]
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

import eval_backends as eb  # noqa: E402
import affected_scenarios as affected  # noqa: E402


def _load_run():
    spec = importlib.util.spec_from_file_location("eval_source_isolation_run", EVALS_DIR / "run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _wrapper(tmp_path: Path) -> Path:
    wrapper = tmp_path / "isolated-codex"
    wrapper.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--eval-source-isolation-probe\" ]; then\n"
        "  [ \"$EVAL_SOURCE_ISOLATION_CAPABILITY_ID\" = \"capability:test\" ] || exit 8\n"
        "  [ \"${#EVAL_SOURCE_ISOLATION_PROFILE_FINGERPRINT}\" -eq 64 ] || exit 8\n"
        "  [ \"${EVAL_TEST_FAIL_PROBE:-}\" != \"1\" ] || exit 7\n"
        "  echo '{\"passed\": true, \"status\": \"blocked\"}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 9\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def _scenario(tmp_path: Path, *, workspace_files: bool = False) -> Path:
    scenario = tmp_path / "protected"
    (scenario / "fixtures").mkdir(parents=True)
    (scenario / "fixtures" / "check_custom_contracts.py").write_text("# withheld\n")
    checks = {
        "name": "protected",
        "checks": [{"id": "one", "check": "do it"}],
        "agent_source_isolation": {
            "capability_id": "capability:test",
            "raw_stream_markers": [
                {"id": "withheld-checker", "needle": "check_custom_contracts.py"},
                {"id": "source-checks-rubric", "target": "scenario_checks"},
                {"id": "prior-benchmark-report-history", "root": "benchmark_report_history"},
                {"id": "prior-closure-temp-history", "root": "closure_temp_history"},
                {"id": "codex-memories", "root": "codex_memories"},
                {"id": "codex-session-history", "root": "codex_session_history"},
                {"id": "evaluator-checkout", "root": "evaluator_checkout"},
            ],
            "probes": [
                {"id": "withheld-checker", "target": "withheld_fixture", "fixture": "check_custom_contracts.py", "command": ["/bin/cat", "{target}"]},
                {"id": "source-checks-rubric", "target": "scenario_checks", "command": ["/bin/cat", "{target}"]},
                *[
                    {"id": root.replace("_", "-"), "target": "operator_root", "root": root, "command": ["/bin/ls", "{target}"]}
                    for root in ("benchmark_report_history", "closure_temp_history", "codex_memories", "codex_session_history", "evaluator_checkout")
                ],
            ],
        },
    }
    if workspace_files:
        checks["workspace_files"] = ["output.txt"]
    (scenario / "checks.json").write_text(json.dumps(checks), encoding="utf-8")
    (scenario / "prompt.md").write_text("--- TASK ---\nwrite output\n", encoding="utf-8")
    return scenario


def _args(wrapper: Path | None, **over):
    base = dict(
        agent_backend="codex", judge_backend="codex", agent_model="m",
        judge_model="j", agent_effort="", judge_effort="", agent_timeout=60,
        judge_timeout=60, docs_base="https://example.invalid", cache_dir=None,
        source_isolation_capability_id="capability:test",
        source_isolation_profile_fingerprint="a" * 64,
        codex_wrapper=str(wrapper) if wrapper else None,
        source_isolation_roots=[
            f"{root}={EVALS_DIR.resolve()}"
            for root in ("benchmark_report_history", "closure_temp_history", "codex_memories", "codex_session_history", "evaluator_checkout")
        ],
    )
    base.update(over)
    return types.SimpleNamespace(**base)


class _StubAgent:
    name = "codex"
    supports_multi_turn = False

    def __init__(self, audit: dict):
        self.audit = audit
        self.calls = 0

    def run_agent(self, ws: Path, *_args, **kwargs):
        self.calls += 1
        # The configured wrapper and marker IDs have to reach the backend; the
        # test deliberately does not infer them from the rendered trace.
        assert kwargs["executable"]
        assert [marker_id for marker_id, _needle in kwargs["source_audit_markers"]] == [
            "withheld-checker", "source-checks-rubric", "prior-benchmark-report-history",
            "prior-closure-temp-history", "codex-memories", "codex-session-history",
            "evaluator-checkout",
        ]
        assert kwargs["env_overrides"]["EVAL_SOURCE_ISOLATION_CAPABILITY_ID"] == "capability:test"
        assert len(kwargs["env_overrides"]["EVAL_SOURCE_ISOLATION_PROFILE_FINGERPRINT"]) == 64
        (ws / "output.txt").write_text("agent output\n")
        return True, "trace", {"final_answer": "done", "source_access_audit": self.audit}


class _Judge:
    name = "codex"

    def run_judge(self, *_args, **_kwargs):
        return {"overall_pass": True, "summary": "ok", "checks": []}


def _install(run, monkeypatch, agent):
    monkeypatch.setattr(run, "get_agent_backend", lambda _name: agent)
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: _Judge())


def test_missing_and_malformed_attestations_fail_before_workspace(tmp_path, monkeypatch):
    run = _load_run()
    scenario = _scenario(tmp_path)
    wrapper = _wrapper(tmp_path)
    monkeypatch.setattr(run, "build_workspace", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no workspace")))

    missing = run.run_one(run.SkillSet("s", "d", []), scenario, _args(wrapper, source_isolation_capability_id=""))
    malformed = run.run_one(run.SkillSet("s", "d", []), scenario, _args(wrapper, source_isolation_profile_fingerprint="not-a-fingerprint"))

    assert "missing source-isolation capability ID" in missing.error
    assert "exactly 64 hexadecimal" in malformed.error


def test_protected_scenario_is_ci_skipped_but_remains_manual_runner_input():
    scenarios, skipped = affected.load_scenarios("public")
    reason = skipped["pocket-custom-contracts"]
    assert "source-isolation wrapper" in reason
    decision = affected.select(
        ["evals/public/pocket-custom-contracts/checks.json"], scenarios, skipped
    )
    assert "pocket-custom-contracts" not in decision["scenarios"]
    assert decision["skipped"] == ["pocket-custom-contracts"]


def test_skill_staging_excludes_recursive_git_metadata(tmp_path, monkeypatch):
    run = _load_run()
    repo = tmp_path / "repo"
    skill = repo / "src" / "fixture-skill"
    (skill / "reference" / "embedded").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: fixture\n---\n", encoding="utf-8")
    (skill / "reference" / "pattern.md").write_text("safe\n", encoding="utf-8")
    (skill / ".gitignore").write_text("build/\n", encoding="utf-8")
    (skill / "README.md").write_text("read me\n", encoding="utf-8")
    (skill / "spec.py").write_text("SPEC = True\n", encoding="utf-8")
    # Cover both a submodule-style .git pointer file and an ordinary nested
    # repository .git directory; neither may be visible in either staging path.
    (skill / "reference" / "embedded" / ".git").write_text("gitdir: /outside\n")
    (skill / ".git").mkdir()
    (skill / ".git" / "config").write_text("outside metadata\n")
    monkeypatch.setattr(run, "REPO_ROOT", repo)

    workspace, plugin = run.build_workspace(
        tmp_path / "staging",
        run.SkillSet("s", "d", ["src/fixture-skill"]),
        _scenario(tmp_path / "scenario"),
        stage_skills_in_workspace=True,
    )
    assert plugin is not None
    for staged in (plugin / "skills" / "fixture-skill", workspace / ".skills" / "fixture-skill"):
        assert (staged / "SKILL.md").is_file()
        assert (staged / "reference" / "pattern.md").is_file()
        assert (staged / ".gitignore").is_file()
        assert (staged / "README.md").is_file()
        assert (staged / "spec.py").is_file()
        assert not list(staged.rglob(".git"))


def test_protected_prompt_is_workspace_only_and_identical_for_baseline_and_head():
    run = _load_run()
    protected = run.build_agent_prompt(
        "do work", "https://example.invalid/", False,
        skills_in_workspace=True, source_isolation=True,
    )
    # The replacement benchmark uses current_pack at two revisions, so both
    # arms receive the same staged-skill line and protected boundary.
    head = run.build_agent_prompt(
        "do work", "https://example.invalid/", False,
        skills_in_workspace=True, source_isolation=True,
    )
    assert protected == head
    assert "materialized as ordinary files inside your workspace" in protected
    assert "system and Pocket executables available on PATH" in protected
    assert "Do not use git, submodules, or another checkout" in protected
    assert "task inputs, examples, repo source, histories, or rubrics outside the workspace" in protected
    assert "WebFetch" not in protected
    assert "curl" not in protected
    assert "mounted alongside" not in protected

    ordinary = run.build_agent_prompt("do work", "https://example.invalid/", True)
    assert ordinary == "\n".join([
        "You are working on a Nextdata OS (nxd) data-product task.",
        "",
        "Available context (the same for every run):",
        "- Public platform docs: fetch markdown pages (WebFetch, or curl if WebFetch is unavailable) at https://example.invalid/<path>.md (e.g. https://example.invalid/dp_development/debugging.md). Start from the index https://example.invalid/_sidebar.md to find the right page. Use the .md URLs directly — the docs viewer's #/ links are not fetchable.",
        "- Your workspace contains the files for this task. Inspect them first: any `nxd-*.txt` files are pre-captured output of nxd CLI commands that were already run for you (read them — do not try to run `nxd`, it is not installed), and any `data_product/` directory is the product source.",
        "- A read-only copy of the public example data products is mounted alongside your workspace (a `nextdata-public-examples` directory with real spec.py / models.py / transform.py / contracts). Read it for working patterns.",
        "",
        "--- TASK ---",
        "do work",
    ])


def test_cache_identity_is_part_of_the_key(tmp_path):
    run = _load_run()
    skill = run.SkillSet("s", "d", [])
    scenario = _scenario(tmp_path)
    base = run._agent_cache_key(skill, scenario, "p", "codex", "m", "", source_isolation_identity={"wrapper_sha256": "a"})
    changed = run._agent_cache_key(skill, scenario, "p", "codex", "m", "", source_isolation_identity={"wrapper_sha256": "b"})
    assert base != changed


def test_raw_stream_audit_reports_only_normalized_marker_ids():
    markers = [("withheld-checker", "check_custom_contracts.py")]
    assert eb.source_access_audit("ordinary stream", markers) == {
        "status": "clean", "matched_marker_ids": []
    }
    assert eb.source_access_audit("read check_custom_contracts.py", markers) == {
        "status": "access_observed", "matched_marker_ids": ["withheld-checker"]
    }


def test_timeout_audit_is_incomplete_even_with_clean_or_partial_raw_stdout(monkeypatch, tmp_path):
    def _timed_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("agent", 1, output=b"check_custom_contracts.py")

    monkeypatch.setattr(eb.subprocess, "run", _timed_out)
    markers = [("withheld-checker", "check_custom_contracts.py")]
    for backend in (eb.ClaudeBackend(), eb.CodexBackend()):
        ok, _trace, metrics = backend.run_agent(
            tmp_path, "task", "model", 1, source_audit_markers=markers
        )
        assert not ok
        assert metrics["source_access_audit"] == {
            "status": "incomplete", "matched_marker_ids": ["withheld-checker"]
        }

    assert eb.source_access_audit("", markers, incomplete=True) == {
        "status": "incomplete", "matched_marker_ids": []
    }


def test_contaminated_cache_is_evicted_and_reported(tmp_path, monkeypatch):
    run = _load_run()
    scenario = _scenario(tmp_path)
    wrapper = _wrapper(tmp_path)
    agent = _StubAgent({"status": "clean", "matched_marker_ids": []})
    _install(run, monkeypatch, agent)
    cache = tmp_path / "cache"
    args = _args(wrapper, cache_dir=str(cache))
    first = run.run_one(run.SkillSet("s", "d", []), scenario, args)
    assert first.ok, first.error
    assert first.metrics["source_isolation_probes"] == [
        {"id": "withheld-checker", "status": "passed"},
        {"id": "source-checks-rubric", "status": "passed"},
        {"id": "benchmark-report-history", "status": "passed"},
        {"id": "closure-temp-history", "status": "passed"},
        {"id": "codex-memories", "status": "passed"},
        {"id": "codex-session-history", "status": "passed"},
        {"id": "evaluator-checkout", "status": "passed"},
    ]
    assert first.metrics["source_isolation_attestation"]["wrapper_path"] == str(wrapper.resolve())

    entry_path = next(cache.glob("agent-*.json"))
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["metrics"]["source_access_audit"] = {
        "status": "access_observed", "matched_marker_ids": ["withheld-checker"]
    }
    entry_path.write_text(json.dumps(entry), encoding="utf-8")

    second = run.run_one(run.SkillSet("s", "d", []), scenario, args)
    assert not second.ok
    assert "cache entry evicted" in second.error
    assert not entry_path.exists()
    assert agent.calls == 1


def test_missing_root_and_failed_probe_are_infrastructure_errors(tmp_path, monkeypatch):
    run = _load_run()
    scenario = _scenario(tmp_path)
    wrapper = _wrapper(tmp_path)
    agent = _StubAgent({"status": "clean", "matched_marker_ids": []})
    _install(run, monkeypatch, agent)

    missing_root = run.run_one(
        run.SkillSet("s", "d", []), scenario,
        _args(wrapper, source_isolation_roots=[]),
    )
    assert "marker target/root is not configured" in missing_root.error
    assert agent.calls == 0

    monkeypatch.setenv("EVAL_TEST_FAIL_PROBE", "1")
    failed_probe = run.run_one(run.SkillSet("s", "d", []), scenario, _args(wrapper))
    assert "probe withheld-checker returned no structured result" in failed_probe.error
    assert failed_probe.metrics["source_isolation_probes"] == [
        {"id": "withheld-checker", "status": "failed"}
    ]
    assert agent.calls == 0


def test_operator_roots_must_be_existing_absolute_non_symlink_paths(tmp_path, monkeypatch):
    run = _load_run()
    scenario = _scenario(tmp_path)
    wrapper = _wrapper(tmp_path)
    agent = _StubAgent({"status": "clean", "matched_marker_ids": []})
    _install(run, monkeypatch, agent)

    cases = [
        ("benchmark_report_history=relative-root", "must be absolute"),
        (f"benchmark_report_history={tmp_path / 'missing'}", "does not exist"),
    ]
    target = tmp_path / "real-root"
    target.mkdir()
    linked = tmp_path / "linked-root"
    linked.symlink_to(target, target_is_directory=True)
    cases.append((f"benchmark_report_history={linked}", "must not traverse a symlink"))

    for root, expected in cases:
        result = run.run_one(
            run.SkillSet("s", "d", []), scenario,
            _args(wrapper, source_isolation_roots=[root]),
        )
        assert expected in result.error
    assert agent.calls == 0

def test_observed_access_stops_before_workspace_facts_or_judge(tmp_path, monkeypatch):
    run = _load_run()
    scenario = _scenario(tmp_path, workspace_files=True)
    wrapper = _wrapper(tmp_path)
    agent = _StubAgent({"status": "access_observed", "matched_marker_ids": ["withheld-checker"]})
    _install(run, monkeypatch, agent)
    monkeypatch.setattr(run, "workspace_files_fact", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not read facts")))

    result = run.run_one(run.SkillSet("s", "d", []), scenario, _args(wrapper))
    assert not result.ok
    assert "observed attempted access: withheld-checker" in result.error
    assert agent.calls == 1


def test_incomplete_timeout_audit_is_an_infrastructure_error(tmp_path, monkeypatch):
    run = _load_run()
    scenario = _scenario(tmp_path)
    wrapper = _wrapper(tmp_path)
    agent = _StubAgent({"status": "incomplete", "matched_marker_ids": []})
    _install(run, monkeypatch, agent)

    result = run.run_one(run.SkillSet("s", "d", []), scenario, _args(wrapper))
    assert not result.ok
    assert "source-access audit is incomplete" in result.error

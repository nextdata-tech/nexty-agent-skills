"""`record init` is the only producer of `s0_spec` — and it must actually be one.

Every other stage has an obvious producer and `s0_spec` had none. Left
unwritten it would stay `not_reached` forever, which pins the materialization
predicate at false and sticks a fully green, published product at
`in_progress`. These tests hold that hole closed:

* a fresh record's `s0_spec` is filled, never `not_reached`;
* it validates the SNAPSHOT, not the live IR — the snapshot is what the closure
  was compiled from, and the live IR having moved is `plan_moved`, not an
  `s0_spec` regression;
* a `--spec-report` computed against different bytes is a hard error, because
  ingesting it would silently certify the wrong plan;
* `record append --stage s0_spec` is rejected.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-pocket-loop" / "scripts"
DIAG = SCRIPTS / "dp_diagnostics.py"
VALIDATOR = SCRIPTS / "validate_dp_spec.py"
WORKED_EXAMPLE = REPO / "src" / "nxd-pocket-loop" / "reference" / "dp-spec.md"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dp_diagnostics as dpd  # noqa: E402

pytest.importorskip("yaml")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, cwd=str(REPO)
    )


def _spec_text() -> str:
    blocks = re.findall(
        r"^```markdown\n(.*?)^```", WORKED_EXAMPLE.read_text(encoding="utf-8"), re.S | re.M
    )
    assert len(blocks) == 1
    return blocks[0].replace("status: proposed", "status: approved", 1)


@pytest.fixture
def workflow(tmp_path) -> dict:
    """The layout the design specifies: the IR beside, the closure below it."""
    spec = tmp_path / "dp-spec.md"
    spec.write_text(_spec_text(), encoding="utf-8")
    prompt = tmp_path / "prompts" / "score_candidate.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("Score one candidate against the rubric.\n", encoding="utf-8")
    closure = tmp_path / "closure"
    result = _run(str(DIAG), "lock", "write", str(spec), str(closure))
    assert result.returncode == 0, result.stderr
    return {
        "spec": spec,
        "closure": closure,
        "lock": closure / "dp-spec.lock.json",
        "record": closure / "build-record.json",
    }


def test_lock_write_byte_copies_the_spec(workflow):
    snapshot = workflow["closure"] / "dp-spec.approved.md"
    assert snapshot.read_bytes() == workflow["spec"].read_bytes(), (
        "the snapshot is evidence, and evidence reformatted on the way in cannot "
        "be compared"
    )
    lock = json.loads(workflow["lock"].read_text())
    assert lock["schema"] == "nxd-dp-spec-lock-v1"
    assert lock["compiler_version"]["plugin"] == "0.29.0"
    assert lock["spec_hash"] == dpd.spec_hash(workflow["spec"].read_bytes())
    assert lock["snapshot_sha256"] == dpd.raw_sha256(snapshot.read_bytes())
    assert lock["source_basename"] == "dp-spec.md"
    assert "/" not in lock["source_basename"], (
        "the lock carries no path to the live IR — a '../'-shaped string inside "
        "the closure is exactly the pointer this design removes"
    )


def test_plugin_version_is_unknown_without_a_manifest(tmp_path):
    assert dpd._plugin_version(tmp_path) == "unknown"


def test_plugin_version_rejects_a_foreign_manifest(tmp_path):
    manifest = tmp_path / ".claude-plugin"
    manifest.mkdir()
    (manifest / "plugin.json").write_text(
        json.dumps({"name": "another-plugin", "version": "9.9.9"}),
        encoding="utf-8",
    )
    assert dpd._plugin_version(tmp_path) == "unknown"


def test_prompt_refs_are_mirrored_at_the_same_relative_path(workflow):
    """A byte copy would otherwise carry a path resolving outside the closure —
    a dangling pointer by another name. The relative path is preserved, so the
    copied spec stays correct without being rewritten and the hash stays valid."""
    mirrored = workflow["closure"] / "prompts" / "score_candidate.md"
    assert mirrored.is_file()
    lock = json.loads(workflow["lock"].read_text())
    assert lock["resolved_refs"] == [
        {
            "spec_ref": "prompts/score_candidate.md",
            "closure_path": "prompts/score_candidate.md",
            "sha256": dpd.raw_sha256(mirrored.read_bytes()),
        }
    ]


def test_an_escaping_prompt_ref_blocks_the_snapshot(tmp_path):
    """Fix the IR, do not rewrite the copy."""
    spec = tmp_path / "dp-spec.md"
    spec.write_text(
        _spec_text().replace("prompts/score_candidate.md", "../prompts/score.md"),
        encoding="utf-8",
    )
    result = _run(str(DIAG), "lock", "write", str(spec), str(tmp_path / "closure"), "--json")
    assert result.returncode == 1
    codes = [d["code"] for d in json.loads(result.stdout)["diagnostics"]]
    assert codes == ["closure.escaping_reference"]
    assert not (tmp_path / "closure" / "dp-spec.lock.json").exists()


def test_lock_verify_passes_and_catches_a_moved_live_spec(workflow):
    ok = _run(str(DIAG), "lock", "verify", str(workflow["closure"]))
    assert ok.returncode == 0, ok.stdout + ok.stderr

    both = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--spec", str(workflow["spec"]))
    assert both.returncode == 0, both.stdout + both.stderr

    workflow["spec"].write_text(
        _spec_text().replace("weight: 0.25", "weight: 0.30", 1), encoding="utf-8"
    )
    moved = _run(
        str(DIAG), "lock", "verify", str(workflow["closure"]), "--spec",
        str(workflow["spec"]), "--json",
    )
    assert moved.returncode == 1
    codes = [d["code"] for d in json.loads(moved.stdout)["diagnostics"]]
    assert "closure.live_spec_diverged" in codes


def test_lock_verify_catches_an_edited_snapshot(workflow):
    snapshot = workflow["closure"] / "dp-spec.approved.md"
    snapshot.write_text(snapshot.read_text() + "\n## sneaky\n\nnothing\n", encoding="utf-8")
    result = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--json")
    assert result.returncode == 1
    codes = [d["code"] for d in json.loads(result.stdout)["diagnostics"]]
    assert "closure.lock_snapshot_byte_mismatch" in codes
    assert "closure.spec_hash_mismatch" in codes


def test_lock_verify_missing_pyyaml_is_an_environment_failure(workflow, monkeypatch, capsys):
    monkeypatch.setattr(dpd, "yaml", None)

    assert dpd.main(["lock", "verify", str(workflow["closure"]), "--json"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "environment.dependency_missing" in captured.err
    assert "closure.lock_unparseable" not in captured.err


@pytest.mark.parametrize("snapshot", ("/tmp/foreign-spec.md", "../foreign-spec.md"))
def test_lock_verify_rejects_snapshot_paths_outside_the_closure(workflow, snapshot):
    lock = json.loads(workflow["lock"].read_text())
    lock["snapshot"] = snapshot
    workflow["lock"].write_text(json.dumps(lock), encoding="utf-8")

    result = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--json")

    assert result.returncode == 1
    diagnostics = json.loads(result.stdout)["diagnostics"]
    assert [d["code"] for d in diagnostics] == ["closure.escaping_reference"]
    assert diagnostics[0]["evidence"] == {"found": snapshot}


def test_lock_verify_rejects_a_snapshot_symlink_outside_the_closure(workflow, tmp_path):
    snapshot = workflow["closure"] / "dp-spec.approved.md"
    external = tmp_path / "external-spec.md"
    external.write_bytes(snapshot.read_bytes())
    snapshot.unlink()
    snapshot.symlink_to(external)

    result = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--json")

    assert result.returncode == 1
    diagnostics = json.loads(result.stdout)["diagnostics"]
    assert [d["code"] for d in diagnostics] == ["closure.escaping_reference"]
    assert diagnostics[0]["evidence"] == {"found": "dp-spec.approved.md"}


@pytest.mark.parametrize("closure_path", ("/tmp/foreign-ref.md", "../foreign-ref.md"))
def test_lock_verify_rejects_resolved_ref_paths_outside_the_closure(workflow, closure_path):
    lock = json.loads(workflow["lock"].read_text())
    lock["resolved_refs"][0]["closure_path"] = closure_path
    workflow["lock"].write_text(json.dumps(lock), encoding="utf-8")

    result = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--json")

    assert result.returncode == 1
    diagnostics = json.loads(result.stdout)["diagnostics"]
    assert [d["code"] for d in diagnostics] == ["closure.escaping_reference"]
    assert diagnostics[0]["evidence"] == {"found": closure_path}


def test_lock_verify_rejects_a_resolved_ref_symlink_outside_the_closure(workflow, tmp_path):
    mirrored = workflow["closure"] / "prompts" / "score_candidate.md"
    external_dir = tmp_path / "external-prompts"
    external_dir.mkdir()
    (external_dir / mirrored.name).write_bytes(mirrored.read_bytes())
    mirrored.unlink()
    mirrored.parent.rmdir()
    mirrored.parent.symlink_to(external_dir, target_is_directory=True)

    result = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--json")

    assert result.returncode == 1
    diagnostics = json.loads(result.stdout)["diagnostics"]
    assert [d["code"] for d in diagnostics] == ["closure.escaping_reference"]
    assert diagnostics[0]["evidence"] == {"found": "prompts/score_candidate.md"}


def test_record_init_fills_s0_spec(workflow):
    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(workflow["record"].read_text())
    assert record["stages"]["s0_spec"]["status"] != "not_reached"
    assert record["stages"]["s0_spec"]["status"] in ("passed", "passed_with_warnings")
    assert record["stages"]["s0_spec"]["origin"] == "tool_computed"
    assert record["compiled_from"] == json.loads(workflow["lock"].read_text())["spec_hash"]
    assert dpd.validate_build_record(record) == []
    assert record["review_rounds"] == []
    # Every other stage is honestly `not_reached`.
    assert record["stages"]["s4_pin"]["status"] == "not_reached"


def test_record_init_validates_the_snapshot_not_the_live_ir(workflow):
    """The snapshot is what the closure was compiled from."""
    workflow["spec"].write_text("this is no longer a spec at all\n", encoding="utf-8")
    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(workflow["record"].read_text())
    assert record["stages"]["s0_spec"]["status"] in ("passed", "passed_with_warnings")


def test_record_init_on_an_unparseable_snapshot_records_it(workflow):
    """The regression: `_validate_snapshot` runs the validator in-process, and a
    `yaml.YAMLError` escaping it used to take `record init` down with a raw
    traceback — no record written, nothing machine-readable.

    The fix is upstream: the split is now field-addressed, so the failure
    arrives as a diagnostic. `record init` therefore does what §2.2 says and
    RECORDS it — `s0_spec: failed`, exit 1 — rather than refusing to write.
    Recording is the point: a closure generated against a spec that does not
    validate is exactly the thing that must become visible instead of implicit.
    """
    snapshot = workflow["closure"] / "dp-spec.approved.md"
    snapshot.write_text("---\nname: [unclosed\n---\n\n## intent\n\nx\n", encoding="utf-8")

    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stdout + result.stderr

    record = json.loads(workflow["record"].read_text())
    s0 = record["stages"]["s0_spec"]
    assert s0["status"] == "failed"
    assert [d["code"] for d in s0["diagnostics"]] == ["spec.frontmatter.unparseable"]
    assert dpd.validate_build_record(record) == []


def test_spec_report_against_different_bytes_exits_two(workflow, tmp_path):
    other = tmp_path / "other.md"
    other.write_text(_spec_text().replace("weight: 0.25", "weight: 0.30", 1), encoding="utf-8")
    report = _run(str(VALIDATOR), str(other), "--json")
    report_path = tmp_path / "report.json"
    report_path.write_text(report.stdout, encoding="utf-8")

    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]), "--spec-report", str(report_path),
    )
    assert result.returncode == 2, result.stdout
    assert "different spec" in result.stderr


def test_spec_report_against_the_right_bytes_is_ingested(workflow, tmp_path):
    report = _run(str(VALIDATOR), str(workflow["closure"] / "dp-spec.approved.md"), "--json")
    report_path = tmp_path / "report.json"
    report_path.write_text(report.stdout, encoding="utf-8")

    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]), "--spec-report", str(report_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(workflow["record"].read_text())
    assert record["stages"]["s0_spec"]["status"] in ("passed", "passed_with_warnings")


def test_record_init_redacts_external_spec_report_diagnostics(workflow, tmp_path):
    url = "postgresql://admin:url-password@db.example.internal/app"
    diagnostic = dpd.diagnostic(
        "spec.frontmatter.bad_name",
        message="invalid name",
        path="spec:frontmatter.name",
        evidence={},
    ).to_dict()
    diagnostic["message"] = f"invalid name from {url}"
    diagnostic["evidence"] = {
        "password": "bare-password",
        "nested": {
            "token": "bare-token",
            "label": "preserve this context",
        },
    }
    report = tmp_path / "spec-report.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v1",
                "tool": "validate_dp_spec",
                "target": str(workflow["spec"]),
                "ok": False,
                "counts": {"error": 1, "warning": 0, "info": 0},
                "spec_hash": dpd.spec_hash(
                    (workflow["closure"] / "dp-spec.approved.md").read_bytes()
                ),
                "diagnostics": [diagnostic],
            }
        ),
        encoding="utf-8",
    )

    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]), "--spec-report", str(report),
    )

    assert result.returncode == 1, result.stdout + result.stderr
    exported = workflow["record"].read_text(encoding="utf-8")
    for secret in ("url-password", "bare-password", "bare-token"):
        assert secret not in exported
    record = json.loads(exported)
    stored = record["stages"]["s0_spec"]["diagnostics"][0]
    assert stored["evidence"]["nested"]["label"] == "preserve this context"
    assert stored["evidence"]["password"] == "<redacted>"


def test_record_append_to_s0_spec_is_rejected(workflow, tmp_path):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v1",
                "tool": "validate_dp_spec",
                "target": "x",
                "ok": True,
                "counts": {"error": 0, "warning": 0, "info": 0},
                "spec_hash": None,
                "diagnostics": [],
            }
        ),
        encoding="utf-8",
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s0_spec", "--from", str(report),
    )
    assert result.returncode == 2
    assert "record init is the only writer" in result.stderr


def test_record_append_rejects_a_tool_that_cannot_produce_the_stage(workflow, tmp_path):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v1",
                "tool": "self_check",
                "target": "x",
                "ok": True,
                "counts": {"error": 0, "warning": 0, "info": 0},
                "spec_hash": None,
                "diagnostics": [],
            }
        ),
        encoding="utf-8",
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s6_run", "--from", str(report),
    )
    assert result.returncode == 2
    assert "cannot carry stage" in result.stderr


def test_a_loop_report_merges_and_the_record_stays_valid(workflow, tmp_path):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    report = tmp_path / "loop.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v1",
                "tool": "loop",
                "target": "build_data_product",
                "ok": False,
                "counts": {"error": 1, "warning": 0, "info": 0},
                "spec_hash": None,
                "diagnostics": [
                    dpd.diagnostic(
                        "pin.build_failed",
                        message="build returned an error with no endpoint",
                        path="tool:build_data_product.error",
                        origin="agent_observed",
                        evidence={"stdout_excerpt": "…"},
                    ).to_dict()
                ],
            }
        ),
        encoding="utf-8",
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s4_pin", "--from", str(report),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(workflow["record"].read_text())
    assert record["stages"]["s4_pin"]["status"] == "failed"
    assert record["stages"]["s4_pin"]["origin"] == "agent_observed", (
        "an agent-constructed report is visibly weaker evidence than a tool's"
    )
    assert dpd.validate_build_record(record) == []

    state = _run(str(DIAG), "materialized", "--record", str(workflow["record"]), "--json")
    assert state.returncode == 1
    assert json.loads(state.stdout)["state"] == "unsettled"


def test_record_append_redacts_incoming_diagnostic_url_credentials(workflow, tmp_path):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    url = "postgresql://admin:password@db.example.internal/app"
    diagnostic = dpd.diagnostic(
        "pin.build_failed",
        message=f"build failed while connecting to {url}",
        path="tool:build_data_product.error",
        origin="agent_observed",
        evidence={
            "endpoint": url,
            "nested": ["keep this context", {"detail": f"retry {url}"}],
        },
    ).to_dict()
    # The producer normally redacts. A report received from another tool is
    # untrusted input, so record append must protect persistent output itself.
    diagnostic["message"] = f"build failed while connecting to {url}"
    diagnostic["evidence"] = {
        "endpoint": url,
        "nested": ["keep this context", {"detail": f"retry {url}"}],
    }
    report = tmp_path / "loop.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v1",
                "tool": "loop",
                "target": "build_data_product",
                "ok": False,
                "counts": {"error": 1, "warning": 0, "info": 0},
                "spec_hash": None,
                "diagnostics": [diagnostic],
            }
        ),
        encoding="utf-8",
    )

    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s4_pin", "--from", str(report),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    exported = workflow["record"].read_text(encoding="utf-8")
    assert "password" not in exported
    assert "postgresql://admin:<redacted>@db.example.internal/app" in exported
    record = json.loads(exported)
    stored = record["stages"]["s4_pin"]["diagnostics"][0]
    assert stored["evidence"]["nested"][0] == "keep this context"


def test_materialized_exits_one_when_not_materialized(workflow):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    result = _run(str(DIAG), "materialized", "--record", str(workflow["record"]))
    assert result.returncode == 1
    assert "state: in_progress" in result.stdout


def test_evidence_with_a_stage_is_rejected_rather_than_silently_dropped(workflow):
    """REGRESSION. `--evidence` is record-level; `--status` stamps
    `origin: agent_observed`. Pairing it with `--stage` reads like "attach this
    supervisor payload to that stage" but merged it record-level at exit 0 —
    which is how a real supervisor's diagnostic.json got dropped on the floor.
    It must now refuse and name the working route.
    """
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s6_run", "--status", "failed",
        "--evidence", '{"supervisor_detail": "kernel host exited"}',
    )
    assert result.returncode == 2
    assert "--from" in result.stderr

    record = json.loads(workflow["record"].read_text(encoding="utf-8"))
    assert "supervisor_detail" not in (record.get("evidence") or {})


def test_record_level_evidence_without_a_stage_still_works(workflow):
    """The guard must not break the legitimate build-wide use."""
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--evidence", '{"row_counts": {"main.widget_sales": 5}}',
    )
    assert result.returncode == 0
    record = json.loads(workflow["record"].read_text(encoding="utf-8"))
    assert record["evidence"]["row_counts"] == {"main.widget_sales": 5}

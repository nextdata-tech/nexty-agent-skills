"""Contract tests for the terminal self-check/provenance scenario."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "evals/public/terminal-self-check-provenance"
CHECKER = SCENARIO / "fixtures/check_terminal_self_check.py"


def _report(definition_id: str | None, *, code: str | None = None) -> dict:
    if code is None:
        checks = [
            {
                "code": "structure/closure_pinned"
                if stage == "structure"
                else f"{stage}/ok",
                "status": "pass",
            }
            for stage in ("structure", "runtime", "contract", "semantic")
        ]
        outcome = "pass"
    else:
        checks = [{"code": code, "status": "fail"}]
        outcome = "fail"
    grouped = []
    names = ("structure", "runtime", "contract", "semantic")
    failed_stage = code.split("/", 1)[0] if code else None
    for index, stage_name in enumerate(names):
        if failed_stage == "structure" and index > 0:
            checks_for_stage = []
            stage_status = "skip"
        elif failed_stage and index > names.index(failed_stage):
            checks_for_stage = [{"code": f"{stage_name}/ok", "status": "pass"}]
            stage_status = "pass"
        else:
            checks_for_stage = [
                c for c in checks if c["code"].startswith(stage_name + "/")
            ]
            stage_status = "fail" if code and stage_name == failed_stage else "pass"
        grouped.append(
            {
                "stage": stage_name,
                "status": stage_status,
                "checks": checks_for_stage
                or [{"code": f"{stage_name}/not_reached", "status": "skip"}],
            }
        )
    return {
        "outcome": outcome,
        "workflow": "terminal-self-check-provenance",
        "provenance": {
            "definition_id": definition_id,
            "python_version": "3.14.0",
            "packages": {"nxd": "0.41.173"},
        },
        "stages": grouped,
    }


def _trace(tmp_path: Path) -> Path:
    calls = [
        ("reference-closure", _report("sha256-v1:" + "1" * 64)),
        (
            "malformed-dp-spec",
            _report(None, code="structure/manifest_admission_failed"),
        ),
        (
            "missing-transform-source",
            _report("sha256-v1:" + "3" * 64, code="runtime/transform_source_missing"),
        ),
        (
            "failed-import",
            _report("sha256-v1:" + "4" * 64, code="runtime/import_failed"),
        ),
        (
            "failed-transform",
            _report(
                "sha256-v1:" + "5" * 64, code="runtime/transform_entrypoint_missing"
            ),
        ),
        (
            "missing-helper",
            _report("sha256-v1:" + "6" * 64, code="runtime/companion_missing"),
        ),
        ("reference-closure", _report("sha256-v1:" + "7" * 64)),
    ]
    lines: list[str] = []
    for number, (case, report) in enumerate(calls, 1):
        relative = (
            Path("reference-closure")
            if case == "reference-closure"
            else Path(".eval-cases") / case
        )
        definition = str(tmp_path / relative)
        lines.append(
            json.dumps(
                {
                    "source": "runner",
                    "protocol": "mcp",
                    "direction": "request",
                    "message": {
                        "jsonrpc": "2.0",
                        "id": number,
                        "method": "tools/call",
                        "params": {
                            "name": "check_data_product",
                            "arguments": {
                                "definition": definition,
                                "workflow": "terminal-self-check-provenance",
                            },
                        },
                    },
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "source": "runner",
                    "protocol": "mcp",
                    "direction": "response",
                    "message": {
                        "jsonrpc": "2.0",
                        "id": number,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(report)}]
                        },
                    },
                }
            )
        )
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_scenario_is_registered_and_runner_side_checker_is_withheld() -> None:
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    assert checks["wants_trace"] is True
    assert checks["deterministic_check"]["trace_source"] == "runner_mcp"
    run_text = (ROOT / "evals/run.py").read_text(encoding="utf-8")
    assert '"terminal-self-check-provenance": frozenset' in run_text
    assert (SCENARIO / "fixtures/desktop_stdio.json").is_file()


def test_checker_requires_distinct_structured_reports(tmp_path: Path) -> None:
    (tmp_path / "transform").mkdir()
    (tmp_path / "transform/main.py").write_text("# fixture\n", encoding="utf-8")
    trace = _trace(tmp_path)
    marker = tmp_path.parent / "nex887-markers.txt"
    marker.write_text("nex887-opaque-synthetic-secret-2d4c\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--fixtures",
            str(SCENARIO / "fixtures"),
            "--root",
            str(tmp_path),
            "--trace",
            str(trace),
            "--secret-marker-file",
            str(marker),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CHECKS PASSED" in result.stdout


def _run_checker(
    root: Path, trace: Path, marker: Path | None = None
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(CHECKER),
        "--fixtures",
        str(SCENARIO / "fixtures"),
        "--root",
        str(root),
        "--trace",
        str(trace),
    ]
    if marker is not None:
        command.extend(("--secret-marker-file", str(marker)))
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def test_checker_rejects_token_matches_without_exact_failure_provenance(
    tmp_path: Path,
) -> None:
    (tmp_path / "transform").mkdir()
    (tmp_path / "transform/main.py").write_text("# fixture\n", encoding="utf-8")
    marker = tmp_path.parent / "nex887-markers-negative.txt"
    marker.write_text("nex887-opaque-synthetic-secret-2d4c\n", encoding="utf-8")
    original = _trace(tmp_path).read_text(encoding="utf-8")
    mutations = (
        # A token-containing but different code must not satisfy an exact case.
        original.replace(
            "runtime/transform_source_missing",
            "runtime/transform_source_missing_fake",
            1,
        ),
        # The matching code must have status=fail, not merely appear in a report.
        original.replace(
            '\\"code\\": \\"runtime/import_failed\\", \\"status\\": \\"fail\\"',
            '\\"code\\": \\"runtime/import_failed\\", \\"status\\": \\"pass\\"',
            1,
        ),
        # A null second ID is not a mutation proof.
        original.replace("sha256-v1:" + "7" * 64, "null", 1),
        # A third starter report must not allow the checker to pair the first
        # and last IDs while ignoring an unchanged second snapshot.
        original + "\n".join(original.splitlines()[:2]) + "\n",
        # The request and report workflow are part of the provenance contract.
        original.replace("terminal-self-check-provenance", "wrong-workflow", 1),
    )
    for index, mutated in enumerate(mutations):
        trace = tmp_path / f"negative-{index}.jsonl"
        trace.write_text(mutated, encoding="utf-8")
        result = _run_checker(tmp_path, trace, marker)
        assert result.returncode != 0, result.stdout
        assert "FAIL " in result.stdout


def test_checker_requires_and_casefolds_redaction_markers(tmp_path: Path) -> None:
    (tmp_path / "transform").mkdir()
    (tmp_path / "transform/main.py").write_text("# fixture\n", encoding="utf-8")
    trace = _trace(tmp_path)

    missing = _run_checker(tmp_path, trace)
    assert missing.returncode != 0
    assert "redaction markers are required" in missing.stdout

    empty = tmp_path / "empty-markers.txt"
    empty.write_text("\n", encoding="utf-8")
    empty_result = _run_checker(tmp_path, trace, empty)
    assert empty_result.returncode != 0
    assert "redaction markers are required" in empty_result.stdout

    marker = tmp_path / "casefold-markers.txt"
    marker.write_text("NEX887-OPAQUE-SYNTHETIC-SECRET-2D4C\n", encoding="utf-8")
    (tmp_path / "leaked.txt").write_text(
        "nex887-opaque-synthetic-secret-2d4c\n", encoding="utf-8"
    )
    casefolded = _run_checker(tmp_path, trace, marker)
    assert casefolded.returncode != 0
    assert "synthetic credential marker" in casefolded.stdout

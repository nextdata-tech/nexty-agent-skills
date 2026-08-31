"""Tests for explicit approval and the checker's read-only boundary."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from dp_scenarios.canary import cli
from dp_scenarios.canary.claims import (
    Baseline,
    ClaimsDocument,
    ClaimsIntegrityError,
    claims_content_hash,
    document_json,
    load_claims,
)
from dp_scenarios.canary.extract import extract_claims
from dp_scenarios.canary.rebaseline import rebaseline


def _skill(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    skill = root / "fixture"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "CANARY_CLAIM id=one code=runtime/secret_shape direction=documented-supported kind=secret :: first\n",
        encoding="utf-8",
    )
    return root


def _write_approved(root: Path, claims_path: Path) -> None:
    extracted = extract_claims(root)
    claim_hash = claims_content_hash(extracted.claims)
    claims_path.write_text(
        document_json(
            ClaimsDocument(
                extracted.claims,
                Baseline(
                    extracted.baseline.skill_files,
                    "original-reviewer",
                    "2026-08-17",
                    claim_hash,
                ),
                {
                    "reviewer": "original-reviewer",
                    "review_date": "2026-08-17",
                    "old_claims_hash": claim_hash,
                    "new_claims_hash": claim_hash,
                },
            )
        ),
        encoding="utf-8",
    )


def _pass_report() -> dict:
    return {
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


def test_check_rejects_stale_approval_without_writing_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _skill(tmp_path)
    claims_path = tmp_path / "claims.json"
    _write_approved(root, claims_path)
    before = claims_path.read_bytes()
    value = load_claims(claims_path).to_dict()
    value["baseline"]["approves_claims_hash"] = "sha256:stale"
    claims_path.write_text(__import__("json").dumps(value, indent=2) + "\n", encoding="utf-8")
    stale_before_check = claims_path.read_bytes()
    monkeypatch.setattr(cli, "run_probe_and_build", lambda *args, **kwargs: pytest.fail("probe must not run"))

    with pytest.raises(ClaimsIntegrityError, match="stale"):
        cli.check_claims(tmp_path, claims_path, skills_root=root)

    assert claims_path.read_bytes() == stale_before_check
    assert before != stale_before_check


def test_check_rejects_source_drift_without_writing_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _skill(tmp_path)
    claims_path = tmp_path / "claims.json"
    _write_approved(root, claims_path)
    before = claims_path.read_bytes()
    skill_file = root / "fixture" / "SKILL.md"
    skill_file.write_text(skill_file.read_text(encoding="utf-8").replace("first", "drifted"), encoding="utf-8")
    monkeypatch.setattr(cli, "run_probe_and_build", lambda *args, **kwargs: pytest.fail("probe must not run"))

    with pytest.raises(__import__("dp_scenarios.canary.extract", fromlist=["ClaimDriftError"]).ClaimDriftError):
        cli.check_claims(tmp_path, claims_path, skills_root=root)

    assert claims_path.read_bytes() == before


def test_rebaseline_requires_reviewer_identity(tmp_path: Path) -> None:
    root = _skill(tmp_path)
    claims_path = tmp_path / "claims.json"
    _write_approved(root, claims_path)
    current_hash = claims_content_hash(load_claims(claims_path).claims)

    with pytest.raises(ClaimsIntegrityError, match="reviewer identity"):
        rebaseline(
            claims_path,
            skills_root=root,
            reviewer="",
            old_claims_hash=current_hash,
            new_claims_hash=current_hash,
        )


def test_rebaseline_validates_both_hashes_before_writing(tmp_path: Path) -> None:
    root = _skill(tmp_path)
    claims_path = tmp_path / "claims.json"
    _write_approved(root, claims_path)
    old_hash = claims_content_hash(load_claims(claims_path).claims)
    before = claims_path.read_bytes()

    with pytest.raises(ClaimsIntegrityError, match="old claims hash does not match"):
        rebaseline(
            claims_path,
            skills_root=root,
            reviewer="human-reviewer",
            old_claims_hash="sha256:wrong-old",
            new_claims_hash=old_hash,
        )
    assert claims_path.read_bytes() == before

    with pytest.raises(ClaimsIntegrityError, match="new claims hash does not match"):
        rebaseline(
            claims_path,
            skills_root=root,
            reviewer="human-reviewer",
            old_claims_hash=old_hash,
            new_claims_hash="sha256:wrong-new",
        )
    assert claims_path.read_bytes() == before


def test_load_claims_requires_a_real_approval_block(tmp_path: Path) -> None:
    root = _skill(tmp_path)
    extracted = extract_claims(root)
    claim_hash = claims_content_hash(extracted.claims)
    claims_path = tmp_path / "claims.json"
    claims_path.write_text(
        __import__("json").dumps(
            {
                "claims": [claim.to_dict() for claim in extracted.claims],
                "baseline": Baseline(
                    extracted.baseline.skill_files,
                    "reviewer",
                    "2026-08-17",
                    claim_hash,
                ).to_dict(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ClaimsIntegrityError, match="approval block"):
        load_claims(claims_path)


def test_rebaseline_writes_approval_that_check_accepts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _skill(tmp_path)
    claims_path = tmp_path / "claims.json"
    approval_path = tmp_path / "approval.json"
    _write_approved(root, claims_path)
    old_hash = claims_content_hash(load_claims(claims_path).claims)
    skill_file = root / "fixture" / "SKILL.md"
    skill_file.write_text(
        skill_file.read_text(encoding="utf-8").replace("first", "second"),
        encoding="utf-8",
    )
    new_hash = claims_content_hash(extract_claims(root).claims)

    document = rebaseline(
        claims_path,
        skills_root=root,
        reviewer="human-reviewer",
        old_claims_hash=old_hash,
        new_claims_hash=new_hash,
        approval_path=approval_path,
    )

    accepted = load_claims(claims_path)
    assert accepted.baseline.approves_claims_hash == new_hash
    assert accepted.approval is not None
    assert accepted.approval["old_claims_hash"] == old_hash
    assert approval_path.is_file()
    assert document.claims == accepted.claims

    drifted_root = tmp_path / "drifted-skills"
    shutil.copytree(root, drifted_root)
    drifted_file = drifted_root / "fixture" / "SKILL.md"
    drifted_file.write_text(
        drifted_file.read_text(encoding="utf-8").replace("second", "drifted"),
        encoding="utf-8",
    )
    before_check = claims_path.read_bytes()
    with pytest.raises(__import__("dp_scenarios.canary.extract", fromlist=["ClaimDriftError"]).ClaimDriftError):
        cli.check_claims(tmp_path, claims_path, skills_root=drifted_root, build=False)
    assert claims_path.read_bytes() == before_check

    monkeypatch.setattr(cli, "run_probe_and_build", lambda *args, **kwargs: (_FakeProbe(_pass_report()), None))
    checked = cli.check_claims(tmp_path, claims_path, skills_root=root, build=False)
    assert checked["verdict"]["outcome"] == "blocked"
    assert any(issue["code"] == "build/skipped" for issue in checked["verdict"]["issues"])


def test_failed_build_without_a_matching_diagnostic_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _skill(tmp_path)
    claims_path = tmp_path / "claims.json"
    _write_approved(root, claims_path)
    fake_build = _FakeBuild(tmp_path / "closure", diagnostic=None)
    monkeypatch.setattr(
        cli,
        "run_probe_and_build",
        lambda *args, **kwargs: (_FakeProbe(_pass_report()), fake_build),
    )

    checked = cli.check_claims(tmp_path, claims_path, skills_root=root)

    assert checked["verdict"]["outcome"] == "blocked"
    assert any(issue["code"] == "build/create_failed" for issue in checked["verdict"]["issues"])


def test_exit_code_and_all_pass_report_disagreement_is_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _skill(tmp_path)
    claims_path = tmp_path / "claims.json"
    _write_approved(root, claims_path)
    monkeypatch.setattr(
        cli,
        "run_probe_and_build",
        lambda *args, **kwargs: (_FakeProbe(_pass_report(), returncode=1), None),
    )

    checked = cli.check_claims(tmp_path, claims_path, skills_root=root)

    assert checked["verdict"]["outcome"] == "blocked"
    assert any(
        issue["code"] == "probe/exit_report_disagreement"
        for issue in checked["verdict"]["issues"]
    )


def test_build_diagnostic_maps_key_error_to_claim_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "skills"
    skill = root / "fixture"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "CANARY_CLAIM id=api-shape code=build/transform_import direction=documented-supported "
        "kind=secret signature=KeyError: :: documented nested API secrets\n",
        encoding="utf-8",
    )
    claims_path = tmp_path / "claims.json"
    _write_approved(root, claims_path)
    fake_build = _FakeBuild(
        tmp_path / "closure",
        diagnostic={
            "error": "exceeded the transform completion budget",
            "stderr": {"lines": ["KeyError: 'api_source'"], "truncated": False},
        },
    )
    monkeypatch.setattr(
        cli,
        "run_probe_and_build",
        lambda *args, **kwargs: (_FakeProbe(_pass_report()), fake_build),
    )

    checked = cli.check_claims(tmp_path, claims_path, skills_root=root)

    assert checked["verdict"]["outcome"] == "drift"
    issue = checked["verdict"]["issues"][0]
    assert issue["claim_id"].startswith("fixture/SKILL.md:api-shape")
    assert issue["code"] == "build/transform_import"
    assert issue["skill_file"] == "fixture/SKILL.md"
    assert issue["line"] == 1
    assert "KeyError: 'api_source'" in issue["message"]


def test_tier_wrapper_preserves_drift_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "skills"
    skill = root / "fixture"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "CANARY_CLAIM id=api-shape code=runtime/secret_shape direction=documented-supported "
        "kind=secret :: documented nested API secrets\n",
        encoding="utf-8",
    )
    claims_path = tmp_path / "claims.json"
    _write_approved(root, claims_path)
    report = {
        "outcome": "fail",
        "stages": [
            {
                "stage": "runtime",
                "status": "fail",
                "checks": [{"code": "runtime/secret_shape", "status": "fail"}],
            }
        ],
    }
    monkeypatch.setattr(
        cli,
        "run_probe_and_build",
        lambda *args, **kwargs: (_FakeProbe(report, returncode=1), None),
    )

    checked = cli.check_claims(tmp_path, claims_path, skills_root=root)

    assert checked["verdict"]["outcome"] == "drift"
    assert checked["verdict"]["blocking"] is True


def test_negative_probe_requires_a_clean_variant_without_planted_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "skills"
    skill = root / "fixture"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "CANARY_CLAIM id=unsupported code=structure/spec_compile_failed "
        "direction=documented-unsupported kind=unsupported probe=unsupported-test :: planted\n",
        encoding="utf-8",
    )
    claims_path = tmp_path / "claims.json"
    _write_approved(root, claims_path)
    closure = tmp_path / "closure"
    closure.mkdir()
    (closure / "spec.py").write_text(
        "from nxd.spec import data_product\n"
        "spec = data_product(name='negative')\n"
        "spec = spec.semantic_tools(service='compute', backend='duckdb')\n",
        encoding="utf-8",
    )
    (closure / "probes.json").write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "probe_id": "unsupported-test",
                        "closure": ".",
                        "build": False,
                        "negative_control": {"remove": ".semantic_tools("},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    calls: list[Path] = []

    def fake_probe(current: Path, **kwargs):
        calls.append(current)
        if "negative-control" in str(current):
            return _FakeProbe(_pass_report()), None
        return _FakeProbe(
            {
                "outcome": "fail",
                "stages": [
                    {
                        "stage": "structure",
                        "status": "fail",
                        "checks": [
                            {"code": "structure/spec_compile_failed", "status": "fail"}
                        ],
                    }
                ],
            },
            returncode=1,
        ), None

    monkeypatch.setattr(cli, "run_probe_and_build", fake_probe)

    checked = cli.check_claims(closure, claims_path, skills_root=root)

    assert checked["verdict"]["outcome"] == "clean"
    assert len(calls) == 2


class _FakeProbe:
    """Small adapter used to keep the re-baseline test independent of a binary."""

    def __init__(self, report: dict, *, returncode: int = 0) -> None:
        self.report = report
        self.returncode = returncode

    def to_dict(self) -> dict:
        return {
            "report": self.report,
            "returncode": self.returncode,
            "command": [],
            "supervisor": "fixture",
            "closure": "fixture",
            "stderr": "",
        }


class _FakeBuild:
    def __init__(self, closure: Path, *, diagnostic: dict | None) -> None:
        self.closure = str(closure)
        self.returncode = 1
        self.diagnostic = diagnostic

    def to_dict(self) -> dict:
        return {
            "supervisor": "fixture",
            "closure": self.closure,
            "command": [],
            "returncode": self.returncode,
            "stdout": "",
            "stderr": "",
            "diagnostic": self.diagnostic,
        }

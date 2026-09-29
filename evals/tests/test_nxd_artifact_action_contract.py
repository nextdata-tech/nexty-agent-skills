"""Regression tests for the cross-repository NXD artifact selector."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import textwrap

import pytest
import yaml


ACTION = Path(__file__).parents[2] / ".github" / "actions" / "nxd-artifact" / "action.yaml"
SOURCE_SHA = "8e08caa8f40f8657c10d2c5a012ed4c636691b5a"
RELEASE_TAG = f"nxd-py-artifact-{SOURCE_SHA}"
RELEASE_ASSET = f"nxd-py-linux-x86_64-{SOURCE_SHA}.tar.gz"


def _action_runs() -> dict[str, str]:
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    return {
        step["name"]: step["run"]
        for step in action["runs"]["steps"]
        if "run" in step
    }


def _fake_gh(tmp_path: Path) -> Path:
    """Create a credential-free gh stub for exercising action control flow."""
    gh = tmp_path / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
endpoint=''
for arg in "$@"; do
  if [[ "$arg" == repos/* ]]; then
    endpoint="$arg"
    break
  fi
done
if [[ "$endpoint" == repos/nextdata-tech/nxd/releases/tags/* ]]; then
  case "$FAKE_MODE" in
    404)
      if [[ " $* " == *" --include "* ]]; then
        printf 'HTTP/2.0 404 Not Found\\n'
      fi
      exit 1
      ;;
    403)
      if [[ " $* " == *" --include "* ]]; then
        printf 'HTTP/2.0 403 Forbidden\\n'
      fi
      exit 1
      ;;
    success)
      cat "$FAKE_RELEASE_FILE"
      ;;
  esac
elif [[ "$endpoint" == repos/nextdata-tech/nxd/git/ref/tags/* ]]; then
  printf '{"object":{"type":"commit","sha":"%s"}}\\n' "$FAKE_SOURCE_SHA"
elif [[ "$endpoint" == *"actions/runs/123/jobs?"* ]]; then
  cat "$FAKE_JOBS_FILE"
elif [[ "$endpoint" == *"actions/runs/123" ]]; then
  cat "$FAKE_RUN_FILE"
elif [[ "$endpoint" == *"actions/workflows/42" ]]; then
  printf '%s\\n' "$FAKE_WORKFLOW_PATH"
elif [[ "$endpoint" == *"actions/workflows/nxd.ci.yml/runs?"* ]]; then
  if [ -n "${FAKE_RUNS_FILE:-}" ]; then
    cat "$FAKE_RUNS_FILE"
  else
    printf '{"workflow_runs":[]}\\n'
  fi
elif [[ "$endpoint" =~ actions/runs/([0-9]+)/artifacts\? ]]; then
  cat "$FAKE_ARTIFACTS_DIR/${BASH_REMATCH[1]}.json"
else
  printf 'unexpected fake gh endpoint: %s\\n' "$endpoint" >&2
  exit 97
fi
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    return gh


def _run_resolver(tmp_path: Path, mode: str) -> subprocess.CompletedProcess[str]:
    release = {
        "tag_name": RELEASE_TAG,
        "draft": False,
        "prerelease": False,
        "assets": [{"name": RELEASE_ASSET, "state": "uploaded"}],
    }
    release_file = tmp_path / "release.json"
    release_file.write_text(json.dumps(release), encoding="utf-8")
    output = tmp_path / "github-output"
    log = tmp_path / "gh.log"
    env = os.environ.copy()
    env.pop("GH_TOKEN", None)
    env.update(
        {
            "PATH": f"{_fake_gh(tmp_path).parent}:{env['PATH']}",
            "FAKE_GH_LOG": str(log),
            "FAKE_MODE": mode,
            "FAKE_RELEASE_FILE": str(release_file),
            "FAKE_SOURCE_SHA": SOURCE_SHA,
            "GITHUB_OUTPUT": str(output),
            "ARTIFACT_PREFIX": "nxd-py-linux-x86_64-",
            "EXPECT_SOURCE_SHA": SOURCE_SHA,
            "SELECTOR_LABEL": "test",
        }
    )
    return subprocess.run(
        ["bash", "-c", _action_runs()["Resolve NXD Python artifact"]],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _publication_jobs_query() -> str:
    """Extract the jq program used by the composite action."""
    action = ACTION.read_text(encoding="utf-8")
    match = re.search(
        r'publication_jobs="\$\(jq -r \'(?P<query>.*?)\n\s*\| length\' <<<',
        action,
        flags=re.DOTALL,
    )
    assert match is not None, "publication job query disappeared from the action"
    return textwrap.dedent(match.group("query")) + "\n| length"


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is required by the action")
def test_publication_selector_tracks_job_id_not_workflow_title() -> None:
    jobs = {
        "jobs": [
            {
                "name": "Build and publish exact Python artifact / artifact-bundle",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "name": "python-build / artifact-bundle",
                "status": "completed",
                "conclusion": "failure",
            },
            {
                "name": "Build and publish exact Python artifact / artifact-bundle",
                "status": "in_progress",
                "conclusion": "",
            },
            {
                "name": "Build and publish exact Python artifact / release",
                "status": "completed",
                "conclusion": "success",
            },
        ]
    }
    result = subprocess.run(
        ["jq", "-r", _publication_jobs_query()],
        input=json.dumps(jobs),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"


def test_pinned_resolution_is_source_addressed_and_fails_closed() -> None:
    action = ACTION.read_text(encoding="utf-8")
    required = (
        'release_tag="nxd-py-artifact-$EXPECT_SOURCE_SHA"',
        'expected_asset="nxd-py-linux-x86_64-$EXPECT_SOURCE_SHA.tar.gz"',
        'releases/tags/$release_tag',
        'git/ref/tags/$release_tag',
        'release_draft',
        'release_prerelease',
        'asset_total',
        'asset_state',
        'gh release download "$RELEASE_TAG"',
        'ARTIFACT_TRANSPORT',
        'workflow_run_id',
        'actions/runs/$workflow_run_id',
        '"$publication_jobs" -gt 1',
    )
    for phrase in required:
        assert phrase in action, phrase

    # The unpinned nightly canary must retain its newest-main Actions-artifact
    # path; the immutable release branch is conditional on a source pin.
    assert 'if [ -n "$EXPECT_SOURCE_SHA" ]; then' in action
    assert 'branch=main&status=success&per_page=20' in action


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is required by the action")
@pytest.mark.parametrize(
    ("mode", "expected_status"),
    (("404", "No unexpired main-branch NXD artifact found"), ("403", "HTTP status: 403")),
)
def test_pinned_release_fallback_is_limited_to_confirmed_404(
    tmp_path: Path, mode: str, expected_status: str
) -> None:
    result = _run_resolver(tmp_path, mode)
    assert result.returncode != 0
    assert expected_status in result.stderr
    calls = (tmp_path / "gh.log").read_text(encoding="utf-8")
    if mode == "404":
        assert "actions/workflows/nxd.ci.yml/runs?" in calls
    else:
        assert "actions/workflows/nxd.ci.yml/runs?" not in calls


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is required by the action")
def test_pinned_release_resolver_returns_source_addressed_transport(tmp_path: Path) -> None:
    result = _run_resolver(tmp_path, "success")
    assert result.returncode == 0, result.stderr
    outputs = dict(
        line.split("=", 1)
        for line in (tmp_path / "github-output").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert outputs == {
        "transport": "release",
        "artifact_name": RELEASE_ASSET,
        "release_tag": RELEASE_TAG,
        "run_id": "",
    }


def _run_release_verifier(
    tmp_path: Path,
    *,
    head_sha: str = SOURCE_SHA,
    head_branch: str = "main",
    run_status: str = "completed",
    run_conclusion: str | None = "success",
    workflow_path: str = ".github/workflows/nxd.python-artifact-refresh.yml",
    publication_jobs: list[dict[str, str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    artifact_dir = tmp_path / "artifact"
    wheels_dir = artifact_dir / "wheels"
    wheels_dir.mkdir(parents=True)
    wheel = wheels_dir / "test.whl"
    wheel.write_bytes(b"test wheel")
    manifest = {
        "schema": "nxd-py-artifact-v1",
        "repository": "nextdata-tech/nxd",
        "source_sha": SOURCE_SHA,
        "workflow_run_id": 123,
        "platform": "linux-x86_64",
        "python": "3.11",
        "package_version": "1.0.0",
        "packages": {
            "nxd-core": "1.0.0",
            "nxd-data_product": "1.0.0",
            "nxd-drivers": "1.0.0",
        },
        "wheels": [{"name": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}],
    }
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    run_file = tmp_path / "run.json"
    run_file.write_text(
        json.dumps(
            {
                "status": run_status,
                "conclusion": run_conclusion,
                "head_branch": head_branch,
                "head_sha": head_sha,
                "workflow_id": 42,
            }
        ),
        encoding="utf-8",
    )
    workflow_file = tmp_path / "workflow-path.txt"
    workflow_file.write_text(workflow_path, encoding="utf-8")
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(json.dumps({"jobs": publication_jobs or []}), encoding="utf-8")
    output = tmp_path / "verify-output"
    log = tmp_path / "gh.log"
    env = os.environ.copy()
    env.pop("GH_TOKEN", None)
    env.update(
        {
            "PATH": f"{_fake_gh(tmp_path).parent}:{env['PATH']}",
            "FAKE_GH_LOG": str(log),
            "FAKE_MODE": "verify",
            "FAKE_SOURCE_SHA": SOURCE_SHA,
            "FAKE_RUN_FILE": str(run_file),
            "FAKE_WORKFLOW_PATH": workflow_file.read_text(encoding="utf-8"),
            "FAKE_JOBS_FILE": str(jobs_file),
            "GITHUB_OUTPUT": str(output),
            "ARTIFACT_DIR": str(artifact_dir),
            "ARTIFACT_RUN_ID": "",
            "ARTIFACT_TRANSPORT": "release",
            "EXPECT_FIELD_MAPPER_TREE_SHA": "",
            "EXPECT_SEMANTIC_TREE_SHA": "",
            "EXPECT_RPC_TREE_SHA": "",
            "EXPECT_SOURCE_SHA": SOURCE_SHA,
            "REQUIRE_MCP_PROVENANCE": "false",
        }
    )
    verify_script = _action_runs()["Verify NXD Python artifact"].replace(
        "${{ github.workspace }}", str(Path.cwd())
    )
    return subprocess.run(
        ["bash", "-c", verify_script],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is required by the action")
def test_release_manifest_verification_binds_source_workflow_and_publication_job(
    tmp_path: Path,
) -> None:
    valid = _run_release_verifier(
        tmp_path / "valid",
        publication_jobs=[
            {
                "name": "Build and publish exact Python artifact / artifact-bundle",
                "status": "completed",
                "conclusion": "success",
            }
        ],
    )
    assert valid.returncode == 0, valid.stderr

    wrong_source = _run_release_verifier(
        tmp_path / "wrong-source",
        head_sha="0" * 40,
        publication_jobs=[
            {
                "name": "Build and publish exact Python artifact / artifact-bundle",
                "status": "completed",
                "conclusion": "success",
            }
        ],
    )
    assert wrong_source.returncode != 0
    assert "not a main run for the pinned source" in wrong_source.stderr

    wrong_branch = _run_release_verifier(
        tmp_path / "wrong-branch",
        head_branch="feature",
        publication_jobs=[
            {
                "name": "Build and publish exact Python artifact / artifact-bundle",
                "status": "completed",
                "conclusion": "success",
            }
        ],
    )
    assert wrong_branch.returncode != 0
    assert "not a main run for the pinned source" in wrong_branch.stderr

    wrong_workflow = _run_release_verifier(
        tmp_path / "wrong-workflow",
        workflow_path=".github/workflows/unrelated.yml",
        publication_jobs=[
            {
                "name": "Build and publish exact Python artifact / artifact-bundle",
                "status": "completed",
                "conclusion": "success",
            }
        ],
    )
    assert wrong_workflow.returncode != 0
    assert "unapproved producer workflow" in wrong_workflow.stderr

    missing_job = _run_release_verifier(tmp_path / "missing-job")
    assert missing_job.returncode != 0
    assert "successful artifact-bundle jobs; expected exactly one" in missing_job.stderr


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is required by the action")
@pytest.mark.parametrize(
    ("run_status", "run_conclusion"),
    [
        # The pin PR opens as soon as the release is published, while the rest
        # of the NXD run (45-80 minutes) is still going (nexty PR #340; NXD
        # runs 36215708383 and 36230304537).
        ("in_progress", None),
        # A later, unrelated job in the same run failed or was cancelled after
        # the artifact-bundle job had already published.
        ("completed", "failure"),
        ("completed", "cancelled"),
    ],
)
def test_release_verification_gates_on_publication_job_not_whole_run(
    tmp_path: Path, run_status: str, run_conclusion: str | None
) -> None:
    result = _run_release_verifier(
        tmp_path,
        run_status=run_status,
        run_conclusion=run_conclusion,
        publication_jobs=[
            {
                "name": "Build and publish exact Python artifact / artifact-bundle",
                "status": "completed",
                "conclusion": "success",
            }
        ],
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is required by the action")
def test_unpinned_miss_logs_every_checked_run(tmp_path: Path) -> None:
    """A newest-main miss must say which runs were checked and why each lost.

    Nightly canary run 36297360210 reported only "No unexpired main-branch NXD
    artifact found", which left the miss undiagnosable.
    """
    runs = {
        "workflow_runs": [
            {
                "id": 501,
                "head_branch": "main",
                "head_sha": "a" * 40,
                "created_at": "2026-09-27T05:00:00Z",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 502,
                "head_branch": "main",
                "head_sha": "b" * 40,
                "created_at": "2026-09-26T08:36:00Z",
                "status": "completed",
                "conclusion": "success",
            },
        ]
    }
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(json.dumps(runs), encoding="utf-8")
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "501.json").write_text(
        json.dumps({"artifacts": [{"name": "docker-image", "expired": False}]}),
        encoding="utf-8",
    )
    (artifacts_dir / "502.json").write_text(
        json.dumps(
            {"artifacts": [{"name": "nxd-py-linux-x86_64-x-y-z-502", "expired": True}]}
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("GH_TOKEN", None)
    env.update(
        {
            "PATH": f"{_fake_gh(tmp_path).parent}:{env['PATH']}",
            "FAKE_GH_LOG": str(tmp_path / "gh.log"),
            "FAKE_RUNS_FILE": str(runs_file),
            "FAKE_ARTIFACTS_DIR": str(artifacts_dir),
            "GITHUB_OUTPUT": str(tmp_path / "github-output"),
            "ARTIFACT_PREFIX": "nxd-py-linux-x86_64-",
            "EXPECT_SOURCE_SHA": "",
            "SELECTOR_LABEL": "the newest NXD main build",
        }
    )
    result = subprocess.run(
        ["bash", "-c", _action_runs()["Resolve NXD Python artifact"]],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "No unexpired main-branch NXD artifact found" in result.stderr
    assert "query returned 2 runs" in result.stdout
    assert (
        f"Skipping NXD run 501 ({'a' * 40}, 2026-09-27T05:00:00Z): "
        "1 artifacts, 0 matching prefix, 0 unexpired"
    ) in result.stdout
    assert (
        f"Skipping NXD run 502 ({'b' * 40}, 2026-09-26T08:36:00Z): "
        "1 artifacts, 1 matching prefix, 0 unexpired"
    ) in result.stdout

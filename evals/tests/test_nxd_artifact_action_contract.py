"""Regression tests for the cross-repository NXD artifact selector."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import textwrap

import pytest


ACTION = Path(__file__).parents[2] / ".github" / "actions" / "nxd-artifact" / "action.yaml"


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

"""Pin the job loop's user-facing language boundary in the shipped pack."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
JOB_LOOP = REPO_ROOT / "src" / "nxd-run-job-loop"
JOB_SKILL = JOB_LOOP / "SKILL.md"
LANGUAGE_REFERENCE = JOB_LOOP / "reference" / "user-facing-language.md"


def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_user_facing_reference_keeps_internal_details_out_of_default_chat():
    text = _flat(LANGUAGE_REFERENCE)
    for marker in (
        "Keep internal identifiers, stage or phase labels, hashes, internal paths",
        "Never echo raw tool errors, logs, traces, request identifiers",
        "states the user-visible impact and current state",
        "contains no raw tool output, internal identifier, internal path, credential, or secret",
    ):
        assert marker in text


def test_job_loop_names_durable_user_files_but_not_staging_paths():
    text = _flat(JOB_SKILL)
    for marker in (
        "state the durable `…/nxd-jobs/<workflow>/` location in the user-facing handoff",
        "Never expose temporary, scratch, or supervisor-owned staging paths",
    ):
        assert marker in text

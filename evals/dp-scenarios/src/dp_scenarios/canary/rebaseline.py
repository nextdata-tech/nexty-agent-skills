"""Explicit human re-baselining for the documentation drift canary.

The tier-facing checker has no claims-writing path because automatic
regeneration would silently approve the drift the canary is meant to expose.
This separate entry point requires a reviewer and an old/new claims-hash pair,
writes the newly reviewed claims and an approval record, and is not called by
the checking CLI.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .claims import Baseline, ClaimsDocument, ClaimsIntegrityError, claims_content_hash, document_json, load_claims
from .extract import extract_claims


def _write_text_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def rebaseline(
    claims_path: Path | str,
    *,
    skills_root: Path | str,
    reviewer: str,
    old_claims_hash: str,
    new_claims_hash: str,
    review_date: str | None = None,
    approval_path: Path | str | None = None,
) -> ClaimsDocument:
    """Approve a newly extracted claims list after explicit human review."""

    if not reviewer or not reviewer.strip():
        raise ClaimsIntegrityError("re-baselining requires a non-empty reviewer identity")
    if not old_claims_hash or not new_claims_hash:
        raise ClaimsIntegrityError("re-baselining requires both old_claims_hash and new_claims_hash")
    claims_file = Path(claims_path).expanduser()
    existing = load_claims(claims_file, verify=False)
    actual_old = claims_content_hash(existing.claims)
    if actual_old != old_claims_hash:
        raise ClaimsIntegrityError(
            f"old claims hash does not match {claims_file}: supplied {old_claims_hash}, current {actual_old}"
        )
    extracted = extract_claims(skills_root, fail_on_drift=False)
    actual_new = claims_content_hash(extracted.claims)
    if actual_new != new_claims_hash:
        raise ClaimsIntegrityError(
            f"new claims hash does not match extracted skill text under {Path(skills_root).expanduser()}: "
            f"supplied {new_claims_hash}, extracted {actual_new}"
        )
    effective_date = review_date or date.today().isoformat()
    if not effective_date.strip():
        raise ClaimsIntegrityError("re-baselining requires a non-empty review date")
    approval: dict[str, Any] = {
        "reviewer": reviewer.strip(),
        "review_date": effective_date,
        "old_claims_hash": old_claims_hash,
        "new_claims_hash": new_claims_hash,
    }
    document = ClaimsDocument(
        claims=extracted.claims,
        baseline=Baseline(
            skill_files=extracted.baseline.skill_files,
            reviewer=reviewer.strip(),
            review_date=effective_date,
            approves_claims_hash=actual_new,
        ),
        approval=approval,
    )
    _write_text_atomically(claims_file, document_json(document))
    approval_file = Path(approval_path).expanduser() if approval_path is not None else claims_file.with_name(
        claims_file.name + ".approval.json"
    )
    _write_text_atomically(
        approval_file,
        json.dumps(
            {
                "claims_file": str(claims_file),
                **approval,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return document


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Explicitly re-baseline reviewed canary claims")
    parser.add_argument("--claims", required=True, type=Path)
    parser.add_argument(
        "--skills-root",
        type=Path,
        required=True,
        help="skill pack installed in the isolated environment under test",
    )
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--old-claims-hash", required=True)
    parser.add_argument("--new-claims-hash", required=True)
    parser.add_argument("--review-date")
    parser.add_argument("--approval-record", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the explicit re-baselining entry point."""

    args = _parser().parse_args(argv)
    document = rebaseline(
        args.claims,
        skills_root=args.skills_root,
        reviewer=args.reviewer,
        old_claims_hash=args.old_claims_hash,
        new_claims_hash=args.new_claims_hash,
        review_date=args.review_date,
        approval_path=args.approval_record,
    )
    print(json.dumps({"claims_hash": document.baseline.approves_claims_hash, "approval": document.approval}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create the runner-owned profile for the terminal API scenario."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SCHEMA = "nxd-synthetic-evaluation-profile-v1"
WORKFLOW = "terminal-authenticated-dlt-api-ingestion"


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    digest = _sha256(WORKFLOW)
    document = {
        "schema": SCHEMA,
        "provider": {
            "kind": "recorded",
            "responses": [{
                "request_sha256": digest,
                "input_tokens": 1,
                "output_tokens": 1,
                "stop_reason": "end_turn",
                "model": "recorded-model",
                "text": "{}",
                "provider_notes": ["evaluation_synthetic"],
            }],
        },
        "approval": {
            "events": [{
                "workflow": WORKFLOW,
                "subject_id": digest,
                "manifest_sha256": digest,
                "budget_fingerprint": digest,
                "decision": "failed",
            }],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    args.output.chmod(0o444)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

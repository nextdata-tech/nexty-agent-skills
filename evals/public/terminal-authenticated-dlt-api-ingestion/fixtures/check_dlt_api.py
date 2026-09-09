"""Runner-side contract checker for the terminal DLT API scenario."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

SECRET = "nex890-opaque-synthetic-secret-9a3c"
EXPECTED_CASES = {
    "unauthorized-401": "auth/unauthorized",
    "forbidden-403": "auth/forbidden",
    "unknown-endpoint-404": "source/not_found",
    "malformed-profile": "closure/profile_malformed",
    "omitted-profile": "closure/profile_missing",
    "retired-companion": "closure/retired_endpoint_companion",
    "hard-coded-endpoint": "closure/endpoint_not_profile_derived",
}


def _trace(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _messages(trace: list[dict], direction: str) -> list[dict]:
    return [item.get("message", {}) for item in trace if item.get("direction") == direction]


def _text(root: Path) -> str:
    parts = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in {"BRIEF.md", "infra-profile.yaml"}:
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def check(root: Path, trace_path: Path, marker_path: Path) -> list[str]:
    failures: list[str] = []
    trace = _trace(trace_path)
    requests = _messages(trace, "request")
    if not any(message.get("method") == "tools/call" for message in requests):
        failures.append("trace/public-mcp-tools-call-missing")
    if SECRET in trace_path.read_text(encoding="utf-8", errors="replace"):
        failures.append("redaction/secret-in-trace")
    marker = marker_path.read_text(encoding="utf-8").strip()
    if marker != SECRET:
        failures.append("checker/secret-marker-mismatch")

    source = _text(root)
    transforms = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in (root / "transform").glob("*.py")) if (root / "transform").is_dir() else ""
    profile = root / "infra-profile.yaml"
    profile_text = profile.read_text(encoding="utf-8", errors="replace") if profile.is_file() else ""
    if not transforms or not re.search(r"rest_api_(?:source|resources)", transforms):
        failures.append("ingestion/dlt-rest-connector-missing")
    if re.search(r"(?:requests|urllib|httpx)", transforms):
        failures.append("ingestion/hand-written-http-loop")
    if "api-source" not in profile_text or "auth_token" not in profile_text or "endpoint_orders" not in profile_text:
        failures.append("profile/flat-api-source-attributes-missing")
    if SECRET not in profile_text:
        failures.append("profile/credential-not-in-supported-profile")
    if (root / "api-source-endpoints").exists():
        failures.append("closure/retired-endpoint-companion-present")
    if re.search(r"(?:127\.0\.0\.1|/v1/orders|ENDPOINT_URL)", transforms):
        failures.append("ingestion/hard-coded-topology")
    if SECRET in source:
        failures.append("redaction/secret-in-generated-source")

    observation_path = os.environ.get("NXD_STUB_OBSERVATIONS", "")
    observations = []
    if observation_path and Path(observation_path).is_file():
        observations = [
            json.loads(line)
            for line in Path(observation_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    successful_pages = [
        item for item in observations
        if item.get("status") == 200 and "/v1/orders" in str(item.get("path", ""))
    ]
    if len(successful_pages) < 3 or sum(int(item.get("rows", 0)) for item in successful_pages) != 23:
        failures.append("landed/pagination-not-complete")
    if successful_pages and any(
        not item.get("authorized") or item.get("user_agent") != "nexty-dlt-client/1.0"
        for item in successful_pages
    ):
        failures.append("wire/auth-or-header-not-proven")

    records = {}
    for path in sorted((root / ".eval-cases").glob("*/failure.json")) if (root / ".eval-cases").is_dir() else []:
        try:
            records[path.parent.name] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            failures.append(f"negative/{path.parent.name}-malformed-record")
    for case, code in EXPECTED_CASES.items():
        record = records.get(case)
        if not isinstance(record, dict) or record.get("status") != "failed" or record.get("code") != code:
            failures.append(f"negative/{case}-missing-structured-code")
    if not failures:
        print("ALL CHECKS PASSED")
    else:
        for failure in failures:
            print(f"FAIL {failure}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--secret-marker-file", type=Path, required=True)
    args = parser.parse_args()
    return 1 if check(args.root, args.trace, args.secret_marker_file) else 0


if __name__ == "__main__":
    raise SystemExit(main())

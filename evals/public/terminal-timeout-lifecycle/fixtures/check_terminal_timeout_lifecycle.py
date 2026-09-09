"""Runner-side oracle for timeout-vs-supervisor lifecycle evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable

TIMEOUT_CODE = -32098
SECRET_MARKERS = {
    "nex888-opaque-synthetic-secret-2d4c",
    "nex888-response-body-should-not-appear",
}


def _records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _message_text(record: dict[str, Any]) -> str:
    return json.dumps(record.get("message", {}), sort_keys=True)


def _id_key(value: Any) -> str:
    """Make JSON-RPC ids comparable without collapsing 1 and 1.0."""
    return json.dumps([type(value).__name__, value], sort_keys=True, separators=(",", ":"))


def _objects(value: Any) -> Iterable[dict[str, Any]]:
    """Yield JSON objects, including objects encoded in MCP text blocks."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return
        if isinstance(decoded, (dict, list)):
            yield from _objects(decoded)


def _contains_key(objects: Iterable[dict[str, Any]], names: set[str]) -> bool:
    return any(
        key in names and value is not None
        for obj in objects
        for key, value in obj.items()
    )


def _values(objects: Iterable[dict[str, Any]], names: set[str]) -> list[Any]:
    return [
        value
        for obj in objects
        for key, value in obj.items()
        if key in names
    ]


def _tool_calls(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for index, record in enumerate(trace):
        if record.get("direction") != "request":
            continue
        message = record.get("message", {})
        params = message.get("params", {}) if isinstance(message, dict) else {}
        if message.get("method") != "tools/call" or not isinstance(params, dict):
            continue
        name = params.get("name")
        if isinstance(name, str):
            calls.append({
                "index": index,
                "id": _id_key(message.get("id")),
                "name": name,
                "message": message,
            })
    return calls


def _response_records(trace: list[dict[str, Any]], call: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        record
        for record in trace
        if record.get("direction") == "response"
        and not record.get("synthetic")
        and _id_key(record.get("message", {}).get("id")) == call["id"]
    ]


def _response_objects(record: dict[str, Any]) -> list[dict[str, Any]]:
    return list(_objects(record.get("message", {}).get("result", {})))


def _successful_response(records: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(record.get("message", {}).get("result"), dict)
        and not record["message"]["result"].get("isError")
        and not record["message"]["result"].get("is_error")
        for record in records
    )


def _failed_response(records: list[dict[str, Any]]) -> bool:
    for record in records:
        message = record.get("message", {})
        if isinstance(message.get("error"), dict):
            return True
        result = message.get("result")
        if isinstance(result, dict) and (result.get("isError") or result.get("is_error")):
            return True
        text = _message_text(record).casefold()
        if '"state": "failed"' in text or '"status": "failed"' in text:
            return True
    return False


def _has_available_publication(objects: Iterable[dict[str, Any]]) -> bool:
    text = json.dumps(list(objects), sort_keys=True).casefold()
    return (
        '"artifact_status": "available"' in text
        or '"status": "published"' in text
        or '"published": true' in text
    )


def check(root: Path, trace_path: Path, marker_file: Path | None = None) -> list[str]:
    failures: list[str] = []
    trace = _records(trace_path)
    trace_text = trace_path.read_text(encoding="utf-8", errors="replace")
    markers = set(SECRET_MARKERS)
    if marker_file is not None and marker_file.is_file():
        markers = {
            line.strip()
            for line in marker_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    for marker in markers:
        if marker in trace_text:
            failures.append(f"redaction/{marker}")
    for candidate in root.rglob("*") if root.is_dir() else ():
        if not candidate.is_file():
            continue
        # The brief intentionally supplies the fixture credential, and the
        # supported closure stores it only in the sensitive profile. Neither
        # is public diagnostic output; every generated/source artifact remains
        # subject to the scan.
        if candidate.name in {"BRIEF.md", "infra-profile.yaml"}:
            continue
        try:
            candidate_text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            failures.append("redaction/artifact-unreadable")
            continue
        for marker in markers:
            if marker in candidate_text:
                failures.append(f"redaction/{marker}")

    if not all(
        record.get("source") == "runner" and record.get("protocol") == "mcp"
        for record in trace
    ):
        failures.append("trace/not-runner-authored-mcp")

    timeout_responses = [
        record for record in trace
        if record.get("synthetic")
        and record.get("timeout_fault")
        and record.get("message", {}).get("error", {}).get("code") == TIMEOUT_CODE
    ]
    if len(timeout_responses) != 1:
        failures.append("timeout/exactly-one-client-deadline")
    elif (
        timeout_responses[0]
        .get("message", {})
        .get("error", {})
        .get("data", {})
        .get("method")
        != "build_data_product"
    ):
        failures.append("timeout/method-not-recorded")

    late_build = [
        record for record in trace
        if record.get("late")
        and record.get("forwarded") is False
        and record.get("message", {}).get("id") == timeout_responses[0].get("message", {}).get("id")
    ] if timeout_responses else []
    if not late_build:
        failures.append("timeout/late-server-response-not-traced-and-suppressed")

    request_records = [record for record in trace if record.get("direction") == "request"]
    inspect_trace_position = next(
        (index for index, record in enumerate(trace)
         if record.get("direction") == "request"
         and record.get("message", {}).get("params", {}).get("name") == "inspect_run"),
        -1,
    )
    timeout_trace_position = next(
        (index for index, record in enumerate(trace)
         if record.get("synthetic") and record.get("timeout_fault")),
        -1,
    )
    if not request_records or inspect_trace_position < 0:
        failures.append("lifecycle/inspect-run-after-timeout-missing")
    elif inspect_trace_position < timeout_trace_position:
        failures.append("lifecycle/inspect-run-not-after-client-timeout")

    inspect_ids = {
        record.get("message", {}).get("id")
        for record in trace
        if record.get("direction") == "request"
        and record.get("message", {}).get("params", {}).get("name") == "inspect_run"
    }
    inspect_responses = [
        record for record in trace
        if record.get("direction") == "response"
        and not record.get("synthetic")
        and record.get("message", {}).get("id") in inspect_ids
    ]
    if not inspect_responses:
        failures.append("lifecycle/authoritative-inspect-response-missing")
    else:
        inspect_objects = [obj for record in inspect_responses for obj in _response_objects(record)]
        joined = "\n".join(_message_text(record) for record in inspect_responses)
        if "duplicate_builds" not in joined or "run_id" not in joined:
            failures.append("lifecycle/run-identity-or-duplicate-count-missing")
        duplicate_counts = _values(inspect_objects, {"duplicate_builds"})
        if not any(value in {0, "0"} for value in duplicate_counts):
            failures.append("retry/duplicate-build-count-not-zero")
        states = [
            str(value).casefold()
            for value in _values(inspect_objects, {"state", "lifecycle_state", "status"})
        ]
        if not any(value in {"continued", "terminal"} for value in states):
            failures.append("lifecycle/continued-or-terminal-state-missing")
        required_fields = {
            "budget": {
                "configured_budget_ms", "budget_ms", "transform_budget_ms",
                "execution_budget_ms", "budget_s", "transform_budget_s",
            },
            "elapsed": {"elapsed_ms", "elapsed_s", "duration_ms", "duration_s"},
            "active-stage": {"active_stage", "current_stage", "stage"},
            "resource-or-model": {"resource", "resource_name", "model", "model_name"},
            "retry-count": {"retry_count", "retries", "attempt_count"},
            "request-or-page-count": {
                "request_count", "requests", "page_count", "pages", "pages_fetched",
            },
        }
        for label, field_names in required_fields.items():
            if not _contains_key(inspect_objects, field_names):
                failures.append(f"timeout/{label}-missing-from-inspect")

    calls = _tool_calls(trace)
    build_calls = [call for call in calls if call["name"] == "build_data_product"]
    if len(build_calls) < 2:
        failures.append("retry/second-build-request-missing")
    else:
        retry_call = build_calls[1]
        retry_records = _response_records(trace, retry_call)
        if not _successful_response(retry_records):
            failures.append("retry/larger-budget-build-success-missing")

    failed_probe_calls = [
        call for call in build_calls[2:]
        if _failed_response(_response_records(trace, call))
    ]
    if not failed_probe_calls:
        failures.append("failure/deterministic-failed-build-missing")
    else:
        failed_probe_index = failed_probe_calls[0]["index"]
        failed_inspect = [
            call for call in calls
            if call["name"] == "inspect_run" and call["index"] > failed_probe_index
        ]
        if not failed_inspect or not any(
            any(
                str(value).casefold() in {"failed", "error"}
                for value in _values(
                    [
                        obj
                        for record in _response_records(trace, call)
                        for obj in _response_objects(record)
                    ],
                    {"state", "lifecycle_state", "status"},
                )
            )
            for call in failed_inspect
        ):
            failures.append("failure/inspect-run-does-not-classify-failure")

    list_calls = [call for call in calls if call["name"] == "list_data_products"]
    successful_retry_index = -1
    if len(build_calls) >= 2:
        retry_records = _response_records(trace, build_calls[1])
        successful_retry_index = next(
            (
                index for index, record in enumerate(trace)
                if record in retry_records and index > build_calls[1]["index"]
            ),
            -1,
        )
    pre_publish_lists = [
        call
        for call in list_calls
        if timeout_trace_position < call["index"] < successful_retry_index
    ]
    post_publish_lists = [call for call in list_calls if call["index"] > successful_retry_index]
    if not pre_publish_lists:
        failures.append("publish/pre-publish-listing-missing")
    elif any(
        _has_available_publication(
            obj
            for record in _response_records(trace, call)
            for obj in _response_objects(record)
        )
        for call in pre_publish_lists
    ):
        failures.append("publish/partial-publication-visible-before-success")
    if not post_publish_lists:
        failures.append("publish/post-success-listing-missing")
    elif not any(
        _has_available_publication(
            obj
            for record in _response_records(trace, call)
            for obj in _response_objects(record)
        )
        for call in post_publish_lists
    ):
        failures.append("publish/available-artifact-not-observed")
    if not any(
        _contains_key(
            [obj for record in _response_records(trace, call) for obj in _response_objects(record)],
            {"publish_seq", "publish_sequence"},
        )
        for call in post_publish_lists
    ):
        failures.append("publish/publish-sequence-missing")
    if failed_probe_calls:
        failed_probe_index = failed_probe_calls[0]["index"]
        failed_listing = [call for call in list_calls if call["index"] > failed_probe_index]
        failed_workflow = str(
            failed_probe_calls[0]["message"].get("params", {})
            .get("arguments", {})
            .get("workflow", "")
        )
        if not failed_workflow:
            failures.append("failure/failed-workflow-not-declared")
        elif not failed_listing:
            failures.append("failure/post-failure-listing-missing")
        elif failed_workflow and any(
            failed_workflow in _message_text(record)
            and _has_available_publication(_response_objects(record))
            for call in failed_listing
            for record in _response_records(trace, call)
        ):
            failures.append("failure/failed-workflow-was-published")

    resume_calls = [call for call in calls if call["name"] == "resume_data_product"]
    if not resume_calls:
        failures.append("resume/resume-request-missing")
    else:
        resume = resume_calls[0]
        if not any(call["index"] < resume["index"] for call in post_publish_lists):
            failures.append("resume/list-before-resume-missing")
        resume_records = _response_records(trace, resume)
        if not _successful_response(resume_records):
            failures.append("resume/successful-resume-missing")
        elif not _contains_key(
            [obj for record in resume_records for obj in _response_objects(record)],
            {"semantic_endpoint", "endpoint"},
        ):
            failures.append("resume/fresh-endpoint-missing")
        if any(
            call["index"] > resume["index"]
            and call["name"] == "build_data_product"
            and not str(
                call["message"].get("params", {})
                .get("arguments", {})
                .get("workflow", "")
            ).endswith("-failed")
            for call in calls
        ):
            failures.append("resume/rebuild-used-instead-of-resume")

    observations_path = os.environ.get("NXD_STUB_OBSERVATIONS", "")
    observations = (
        _records(Path(observations_path))
        if observations_path and Path(observations_path).is_file()
        else []
    )
    pages = [item for item in observations if item.get("status") == 200]
    if len(pages) < 3 or sum(int(item.get("rows", 0)) for item in pages) != 23:
        failures.append("source/three-pages-and-23-rows-not-proven")

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
    parser.add_argument("--secret-marker-file", type=Path, required=False)
    args = parser.parse_args()
    return 1 if check(args.root, args.trace, args.secret_marker_file) else 0


if __name__ == "__main__":
    raise SystemExit(main())

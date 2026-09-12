"""Runner-side oracle for timeout-vs-supervisor lifecycle evidence."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Any

TIMEOUT_CODE = -32098
DUPLICATE_BUILD_COUNT_FIELDS = frozenset({
    "duplicate_build_count",
    "duplicate_builds",
    "duplicates",
})
# Fallback for a standalone invocation. The runner passes the authoritative
# list from checks.json through --secret-marker-file; keep the two in sync.
#
# Only the injected credential is marker-scanned. A raw-response-body canary
# was tried and removed: the scan cannot tell a legitimately materialized
# payload (an API source may land the raw envelope by design) or a passively
# observed tool result from an actual leak, so it could only produce false
# failures. The "raw response bodies absent from diagnostics" half of the
# redaction-and-cleanup check is graded from the trace by the judge instead.
SECRET_MARKERS = {
    "nex888-opaque-synthetic-secret-2d4c",
}


def _marker_labels(markers: list[str]) -> dict[str, str]:
    """Give redaction failures stable names without echoing secret values."""
    return {marker: f"marker-{index + 1}" for index, marker in enumerate(markers)}


def _records(path: Path) -> list[Any]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _record_value(record: Any, key: str, default: Any = None) -> Any:
    return record.get(key, default) if isinstance(record, dict) else default


def _message(record: Any) -> dict[str, Any] | None:
    message = _record_value(record, "message")
    return message if isinstance(message, dict) else None


def _params(message: dict[str, Any] | None) -> dict[str, Any] | None:
    params = message.get("params") if message is not None else None
    return params if isinstance(params, dict) else None


def _tool_name(record: Any) -> str | None:
    params = _params(_message(record))
    name = params.get("name") if params is not None else None
    return name if isinstance(name, str) else None


def _message_value(record: Any, key: str, default: Any = None) -> Any:
    message = _message(record)
    return message.get(key, default) if message is not None else default


def _mapping_value(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else default


def _message_text(record: Any) -> str:
    return json.dumps(_record_value(record, "message", {}), sort_keys=True)


def _id_key(value: Any) -> str:
    """Make JSON-RPC ids comparable without collapsing 1 and 1.0."""
    return json.dumps([type(value).__name__, value], sort_keys=True, separators=(",", ":"))


def _valid_jsonrpc_id(value: Any) -> bool:
    """Accept only the scalar JSON-RPC id types (or an explicit null)."""
    return value is None or type(value) in {str, int} or (
        type(value) is float and math.isfinite(value)
    )


def _is_zero(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value == 0
    ) or value == "0"


def _valid_observation_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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


def _object_contexts(
    value: Any,
    inherited_workflow: str | None = None,
    inherited_run_id: Any = None,
) -> Iterable[
    tuple[
        dict[str, Any],
        str | None,
        Any,
        tuple[tuple[dict[str, Any], str | None, Any], ...],
    ]
]:
    """Yield objects with effective identity and their ancestor contexts."""
    def walk(
        current: Any,
        current_workflow: str | None,
        current_run_id: Any,
        ancestors: tuple[tuple[dict[str, Any], str | None, Any], ...],
    ) -> Iterable[
        tuple[
            dict[str, Any],
            str | None,
            Any,
            tuple[tuple[dict[str, Any], str | None, Any], ...],
        ]
    ]:
        if isinstance(current, dict):
            own_workflow = current.get("workflow")
            own_workflow = own_workflow if isinstance(own_workflow, str) else None
            own_run_id = current.get("run_id")
            own_run_id = (
                own_run_id
                if isinstance(own_run_id, (str, int, float))
                and not isinstance(own_run_id, bool)
                else None
            )
            workflow = own_workflow if own_workflow is not None else current_workflow
            run_id = own_run_id if own_run_id is not None else current_run_id
            yield current, workflow, run_id, ancestors
            child_ancestors = (*ancestors, (current, workflow, run_id))
            for child in current.values():
                yield from walk(child, workflow, run_id, child_ancestors)
        elif isinstance(current, list):
            for child in current:
                yield from walk(child, current_workflow, current_run_id, ancestors)
        elif isinstance(current, str):
            try:
                decoded = json.loads(current)
            except json.JSONDecodeError:
                return
            if isinstance(decoded, (dict, list)):
                yield from walk(decoded, current_workflow, current_run_id, ancestors)

    yield from walk(value, inherited_workflow, inherited_run_id, ())


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


def _tool_calls(trace: list[Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for index, record in enumerate(trace):
        if _record_value(record, "direction") != "request":
            continue
        message = _message(record)
        params = _params(message)
        if message is None or message.get("method") != "tools/call" or params is None:
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


def _response_records(
    trace: list[Any],
    call: dict[str, Any],
    *,
    before_index: int | None = None,
) -> list[dict[str, Any]]:
    return [
        record
        for index, record in enumerate(trace)
        if index > call["index"]
        and (before_index is None or index < before_index)
        if _record_value(record, "direction") == "response"
        and not _record_value(record, "synthetic")
        and _id_key(_message_value(record, "id")) == call["id"]
        and isinstance(record, dict)
    ]


def _response_objects(record: Any) -> list[dict[str, Any]]:
    return list(_objects(_message_value(record, "result", {})))


def _successful_response(records: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(result := _message_value(record, "result"), dict)
        and not result.get("isError")
        and not result.get("is_error")
        for record in records
    )


def _failed_response(records: list[dict[str, Any]]) -> bool:
    for record in records:
        message = _message(record)
        if message is None:
            continue
        if isinstance(message.get("error"), dict):
            return True
        result = message.get("result")
        if isinstance(result, dict) and (result.get("isError") or result.get("is_error")):
            return True
        text = _message_text(record).casefold()
        if '"state": "failed"' in text or '"status": "failed"' in text:
            return True
    return False


PUBLICATION_IDENTITY_FIELDS = ("workflow", "name", "product", "data_product")
# `versions` and `revisions` may contain the current record alongside older
# records, so they remain live publication evidence even in pre-retry listings.
PUBLICATION_HISTORY_KEYS = frozenset({
    "last_published",
    "previous_version",
    "previous",
    "history",
    "prior_version",
})


def _publication_identity(value: dict[str, Any]) -> str | None:
    for key in PUBLICATION_IDENTITY_FIELDS:
        identity = value.get(key)
        if isinstance(identity, str):
            return identity
    return None


def _has_available_publication(
    value: Any,
    workflow: str | None = None,
    inherited_workflow: str | None = None,
    in_history: bool = False,
) -> bool:
    if isinstance(value, dict):
        own_identity = _publication_identity(value)
        node_workflow = own_identity if own_identity is not None else inherited_workflow
        scoped = workflow is None or node_workflow == workflow
        if not in_history and scoped and (
            str(value.get("artifact_status", "")).casefold() == "available"
            or str(value.get("status", "")).casefold() == "published"
            or value.get("published") is True
        ):
            return True
        return any(
            _has_available_publication(
                child,
                workflow,
                node_workflow,
                in_history or key in PUBLICATION_HISTORY_KEYS,
            )
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(
            _has_available_publication(
                child,
                workflow,
                inherited_workflow,
                in_history,
            )
            for child in value
        )
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return False
        return _has_available_publication(
            decoded,
            workflow,
            inherited_workflow,
            in_history,
        )
    return False


def _call_workflow(call: dict[str, Any]) -> str:
    params = _params(call.get("message"))
    arguments = params.get("arguments", {}) if params is not None else {}
    workflow = arguments.get("workflow") if isinstance(arguments, dict) else None
    return workflow if isinstance(workflow, str) else ""


def _call_run_id(call: dict[str, Any]) -> Any:
    params = _params(call.get("message"))
    arguments = params.get("arguments", {}) if params is not None else {}
    run_id = arguments.get("run_id") if isinstance(arguments, dict) else None
    return (
        run_id
        if isinstance(run_id, (str, int, float)) and not isinstance(run_id, bool)
        else None
    )


def _same_identity(left: Any, right: Any) -> bool:
    return _id_key(left) == _id_key(right)


def _inspect_object_matches_primary(
    call: dict[str, Any],
    primary_workflow: str,
    primary_run_id: Any,
    object_workflow: str | None,
    object_run_id: Any,
) -> bool:
    call_workflow = _call_workflow(call)
    call_run_id = _call_run_id(call)
    if object_workflow is not None and object_workflow != primary_workflow:
        return False
    if primary_run_id is not None:
        if object_run_id is not None and not _same_identity(
            object_run_id, primary_run_id
        ):
            return False
        if call_run_id is not None and not _same_identity(call_run_id, primary_run_id):
            return False
        return (
            object_workflow == primary_workflow
            or (
                object_run_id is not None
                and _same_identity(object_run_id, primary_run_id)
            )
            or call_workflow == primary_workflow
        )
    return (
        object_workflow == primary_workflow
        or call_workflow == primary_workflow
        or (object_workflow is None and call_run_id is None and object_run_id is not None)
    )


def _call_objects(
    trace: list[Any], call: dict[str, Any], *, before_index: int | None = None
) -> list[dict[str, Any]]:
    return [
        obj
        for record in _response_records(trace, call, before_index=before_index)
        for obj in _response_objects(record)
    ]


def _call_has_published_primary(
    trace: list[Any],
    call: dict[str, Any],
    workflow: str | None,
    *,
    before_index: int | None = None,
) -> bool:
    return any(
        _has_available_publication(
            _message_value(record, "result", {}), workflow
        )
        for record in _response_records(trace, call, before_index=before_index)
    )


def check(root: Path, trace_path: Path, marker_file: Path | None = None) -> list[str]:
    failures: list[str] = []
    trace = _records(trace_path)
    trace_text = trace_path.read_text(encoding="utf-8", errors="replace")
    for record in trace:
        if not isinstance(record, dict):
            failures.append("trace/non-object-record")
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            failures.append("trace/non-object-json-rpc-message")
        else:
            if "id" in message and not _valid_jsonrpc_id(message["id"]):
                failures.append("trace/invalid-json-rpc-id")
            if (
                "params" in message
                and message["params"] is not None
                and not isinstance(message["params"], dict)
            ):
                failures.append("trace/positional-json-rpc-params")
    markers = sorted(SECRET_MARKERS)
    if marker_file is not None:
        # Naming a marker file and then scanning nothing would report a clean
        # redaction result from a check that never ran. Fail closed instead.
        try:
            supplied = [
                line.strip()
                for line in marker_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            supplied = []
        if not supplied:
            failures.append("redaction/marker-file-unusable")
        markers = supplied
    marker_labels = _marker_labels(markers)
    for marker in markers:
        if marker in trace_text:
            failures.append(f"redaction/{marker_labels[marker]}")
    for candidate in root.rglob("*") if root.is_dir() else ():
        if not candidate.is_file():
            continue
        # BRIEF.md is source material and remains subject to the scan. The
        # profile is runtime credential input, so only its mode is inspected;
        # its contents must never become checker output.
        if candidate.name == "infra-profile.yaml":
            try:
                mode = stat.S_IMODE(candidate.stat().st_mode)
            except OSError:
                failures.append("redaction/infra-profile-unreadable")
                continue
            if mode != 0o600:
                failures.append("redaction/infra-profile-not-mode-0600")
            continue
        try:
            candidate_text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            failures.append("redaction/artifact-unreadable")
            continue
        for marker in markers:
            if marker in candidate_text:
                failures.append(f"redaction/{marker_labels[marker]}")

    if not all(
        _record_value(record, "source") == "runner"
        and _record_value(record, "protocol") == "mcp"
        for record in trace
    ):
        failures.append("trace/not-runner-authored-mcp")

    timeout_responses = [
        record for record in trace
        if _record_value(record, "synthetic")
        and _record_value(record, "timeout_fault")
        and _mapping_value(
            _message_value(record, "error", {}), "code"
        ) == TIMEOUT_CODE
    ]
    if len(timeout_responses) != 1:
        failures.append("timeout/exactly-one-client-deadline")
    elif (
        _mapping_value(
            _mapping_value(_message_value(timeout_responses[0], "error", {}), "data", {}),
            "method",
        )
        != "build_data_product"
    ):
        failures.append("timeout/method-not-recorded")

    late_build = [
        record for record in trace
        if _record_value(record, "late")
        and _record_value(record, "forwarded") is False
        and _same_identity(
            _message_value(record, "id"),
            _message_value(timeout_responses[0], "id"),
        )
    ] if timeout_responses else []
    if not late_build:
        failures.append("timeout/late-server-response-not-traced-and-suppressed")

    request_records = [
        record for record in trace if _record_value(record, "direction") == "request"
    ]
    inspect_trace_position = next(
        (index for index, record in enumerate(trace)
         if _record_value(record, "direction") == "request"
         and _tool_name(record) == "inspect_run"),
        -1,
    )
    timeout_trace_position = next(
        (index for index, record in enumerate(trace)
         if _record_value(record, "synthetic")
         and _record_value(record, "timeout_fault")),
        -1,
    )
    if not request_records or inspect_trace_position < 0:
        failures.append("lifecycle/inspect-run-after-timeout-missing")
    elif inspect_trace_position < timeout_trace_position:
        failures.append("lifecycle/inspect-run-not-after-client-timeout")

    calls = _tool_calls(trace)
    build_calls = [call for call in calls if call["name"] == "build_data_product"]
    primary_workflow = _call_workflow(build_calls[0]) if build_calls else ""
    primary_build_calls = [
        call for call in build_calls
        if _call_workflow(call) == primary_workflow
    ]
    published_primary_from_inspect = False

    retry_boundary = (
        primary_build_calls[1]["index"]
        if len(primary_build_calls) > 1
        else len(trace)
    )
    authoritative_inspect_calls = [
        call for call in calls
        if call["name"] == "inspect_run"
        and timeout_trace_position < call["index"] < retry_boundary
    ]

    authoritative_inspect_records: list[dict[str, Any]] = []
    inspect_entries: list[
        tuple[
            dict[str, Any],
            list[
                tuple[
                    dict[str, Any],
                    str | None,
                    Any,
                    tuple[tuple[dict[str, Any], str | None, Any], ...],
                ]
            ],
        ]
    ] = []
    primary_inspect_objects: list[dict[str, Any]] = []
    primary_run_id: Any = next(
        (
            value
            for record in late_build
            for _object, _workflow, value, _ancestors in _object_contexts(
                _message_value(record, "result", {})
            )
            if value is not None
        ),
        None,
    )
    for call in authoritative_inspect_calls:
        records = _response_records(trace, call, before_index=retry_boundary)
        authoritative_inspect_records.extend(records)
        response_contexts = [
            context
            for record in records
            for context in _object_contexts(_message_value(record, "result", {}))
        ]
        inspect_entries.append((call, response_contexts))

    if primary_run_id is None:
        # A workflow-qualified response is the strongest response-side fallback
        # when the timed-out build's late reply did not carry a run id.
        for call, response_contexts in inspect_entries:
            call_run_id = _call_run_id(call)
            workflow_run_id = next(
                (
                    run_id
                    for _obj, workflow, run_id, _ancestors in response_contexts
                    if workflow == primary_workflow and run_id is not None
                ),
                None,
            )
            if workflow_run_id is not None or (
                _call_workflow(call) == primary_workflow and call_run_id is not None
            ):
                primary_run_id = (
                    call_run_id if call_run_id is not None else workflow_run_id
                )
                break
    if primary_run_id is None:
        # Prefer an unscoped inspection as the durable run discovery step. This
        # prevents an earlier explicit inspection of another run from becoming
        # the primary identity merely because it happened to be first.
        for call, response_contexts in inspect_entries:
            if _call_run_id(call) is not None:
                continue
            primary_run_id = next(
                (
                    run_id
                    for _obj, workflow, run_id, _ancestors in response_contexts
                    if run_id is not None
                    and (workflow is None or workflow == primary_workflow)
                ),
                None,
            )
            if primary_run_id is not None:
                break
    if primary_run_id is None:
        # If the agent obtained the durable id before its first inspection, the
        # request-side id is still authoritative; use it only after the safer
        # late-response and unscoped-discovery candidates were exhausted.
        explicit_run_ids = [
            _call_run_id(call)
            for call, _response_contexts in inspect_entries
            if _call_run_id(call) is not None
        ]
        if len({_id_key(run_id) for run_id in explicit_run_ids}) == 1:
            primary_run_id = explicit_run_ids[0]

    primary_branch_entries: list[
        tuple[dict[str, Any], tuple[dict[str, Any], ...]]
    ] = []
    for call, response_contexts in inspect_entries:
        for obj, object_workflow, object_run_id, ancestors in response_contexts:
            if _inspect_object_matches_primary(
                call,
                primary_workflow,
                primary_run_id,
                object_workflow,
                object_run_id,
            ):
                primary_inspect_objects.append(obj)
                matched_ancestors = tuple(
                    ancestor
                    for ancestor, ancestor_workflow, ancestor_run_id in ancestors
                    if _inspect_object_matches_primary(
                        call,
                        primary_workflow,
                        primary_run_id,
                        ancestor_workflow,
                        ancestor_run_id,
                    )
                )
                primary_branch_entries.append((obj, matched_ancestors))

    def _branch_values(
        names: set[str], shadow_names: set[str] | None = None
    ) -> list[Any]:
        shadow_names = shadow_names or names
        return [
            value
            for obj, ancestors in primary_branch_entries
            for key, value in obj.items()
            if key in names
            and value is not None
            and not any(
                any(ancestor_key in shadow_names for ancestor_key in ancestor)
                for ancestor in ancestors
            )
        ]

    if not authoritative_inspect_records or not primary_inspect_objects:
        failures.append("lifecycle/authoritative-inspect-response-missing")
    else:
        joined = json.dumps(primary_inspect_objects, sort_keys=True)
        published_primary_from_inspect = any(
            str(value).casefold() == "published"
            for value in _branch_values(
                {"status"}, {"state", "lifecycle_state", "status"}
            )
        )
        if "run_id" not in joined or (
            not published_primary_from_inspect
            and not _branch_values(DUPLICATE_BUILD_COUNT_FIELDS)
        ):
            failures.append("lifecycle/run-identity-or-duplicate-count-missing")
        duplicate_counts = _branch_values(DUPLICATE_BUILD_COUNT_FIELDS)
        if (
            not published_primary_from_inspect
            and (
                not duplicate_counts
                or not all(_is_zero(value) for value in duplicate_counts)
            )
        ):
            failures.append("retry/duplicate-build-count-not-zero")
        states = [
            str(value).casefold()
            for value in _branch_values(
                {"state", "lifecycle_state", "status"}
            )
        ]
        if not any(value in {"continued", "terminal", "published"} for value in states):
            failures.append("lifecycle/continued-or-terminal-state-missing")
        if not published_primary_from_inspect:
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
                if not _contains_key(primary_inspect_objects, field_names):
                    failures.append(f"timeout/{label}-missing-from-inspect")

    published_primary = published_primary_from_inspect or any(
        _call_has_published_primary(
            trace, call, primary_workflow or None, before_index=retry_boundary
        )
        for call in calls
        if call["name"] == "list_data_products"
        and call["index"] > timeout_trace_position
        and (
            len(primary_build_calls) < 2
            or call["index"] < primary_build_calls[1]["index"]
        )
    ) if primary_workflow else published_primary_from_inspect
    if published_primary:
        if len(primary_build_calls) > 1:
            failures.append("retry/duplicate-build-count-not-zero")
    elif len(primary_build_calls) < 2:
        failures.append("retry/second-build-request-missing")
    else:
        retry_call = primary_build_calls[1]
        retry_records = _response_records(trace, retry_call)
        if not _successful_response(retry_records):
            failures.append("retry/larger-budget-build-success-missing")

    failed_probe_calls = [
        call for call in build_calls[1:]
        if _call_workflow(call) != primary_workflow
        and _failed_response(_response_records(trace, call))
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
    if not published_primary and len(primary_build_calls) >= 2:
        retry_records = _response_records(trace, primary_build_calls[1])
        successful_retry_index = next(
            (
                index for index, record in enumerate(trace)
                if record in retry_records and index > primary_build_calls[1]["index"]
            ),
            -1,
        )

    if published_primary:
        publication_lists = [
            call for call in list_calls
            if call["index"] > timeout_trace_position
            and _call_has_published_primary(trace, call, primary_workflow or None)
        ]
        first_publication_index = min(
            (call["index"] for call in publication_lists), default=-1
        )
        pre_publish_lists = [
            call for call in list_calls
            if timeout_trace_position < call["index"] < first_publication_index
        ]
        post_publish_lists = [
            call for call in list_calls if call["index"] >= first_publication_index
        ]
    else:
        pre_publish_lists = [
            call for call in list_calls
            if timeout_trace_position < call["index"] < successful_retry_index
        ]
        post_publish_lists = [
            call for call in list_calls if call["index"] > successful_retry_index
        ]

    if not published_primary and not pre_publish_lists:
        failures.append("publish/pre-publish-listing-missing")
    elif any(
        _call_has_published_primary(
            trace,
            call,
            primary_workflow or None,
            before_index=successful_retry_index if not published_primary else None,
        )
        for call in pre_publish_lists
    ):
        failures.append("publish/partial-publication-visible-before-success")
    if not post_publish_lists:
        failures.append("publish/post-success-listing-missing")
    elif not any(
        _call_has_published_primary(trace, call, primary_workflow or None)
        for call in post_publish_lists
    ):
        failures.append("publish/available-artifact-not-observed")
    if not any(
        _contains_key(
            _call_objects(trace, call), {"publish_seq", "publish_sequence"}
        )
        for call in post_publish_lists
    ):
        failures.append("publish/publish-sequence-missing")
    if failed_probe_calls:
        failed_probe_index = failed_probe_calls[0]["index"]
        failed_listing = [call for call in list_calls if call["index"] > failed_probe_index]
        failed_workflow = _call_workflow(failed_probe_calls[0])
        if not failed_workflow:
            failures.append("failure/failed-workflow-not-declared")
        elif not failed_listing:
            failures.append("failure/post-failure-listing-missing")
        elif failed_workflow and any(
            failed_workflow in _message_text(record)
            and _has_available_publication(
                _message_value(record, "result", {}), failed_workflow
            )
            for call in failed_listing
            for record in _response_records(trace, call)
        ):
            failures.append("failure/failed-workflow-was-published")

    if published_primary:
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
                and _call_workflow(call) == primary_workflow
                for call in calls
            ):
                failures.append("resume/rebuild-used-instead-of-resume")

    observations_path = os.environ.get("NXD_STUB_OBSERVATIONS", "")
    observations: list[Any] = []
    if observations_path and Path(observations_path).is_file():
        try:
            observations = _records(Path(observations_path))
        except (OSError, json.JSONDecodeError):
            failures.append("observations/malformed-json")
    page_rows: dict[int, set[int]] = {}
    for item in observations:
        if not isinstance(item, dict):
            failures.append("observations/non-object-record")
            continue
        status = _record_value(item, "status")
        authorized = _record_value(item, "authorized")
        path = _record_value(item, "path")
        if status == 200 and authorized is True and not isinstance(path, str):
            failures.append("observations/invalid-path")
            continue
        if status == 200 and authorized is True and path.split("?", 1)[0] == "/v1/events":
            page = _record_value(item, "page")
            rows = _record_value(item, "rows")
            if not _valid_observation_integer(page):
                failures.append("observations/invalid-page")
                continue
            if not _valid_observation_integer(rows):
                failures.append("observations/invalid-row-count")
                continue
            page_rows.setdefault(page, set()).add(rows)
    expected_page_rows = {1: {10}, 2: {10}, 3: {3}}
    if (
        set(page_rows) != set(expected_page_rows)
        or any(page_rows.get(page) != rows for page, rows in expected_page_rows.items())
    ):
        observed = ", ".join(
            f"status={_record_value(item, 'status')} "
            f"page={_record_value(item, 'page')} rows={_record_value(item, 'rows')}"
            for item in observations
        ) or "none"
        failures.append(
            "source/three-pages-and-23-rows-not-proven "
            f"(observed: {observed})"
        )

    failures = list(dict.fromkeys(failures))
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

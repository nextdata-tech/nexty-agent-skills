#!/usr/bin/env python3
"""Record and index benchmark evidence without rewriting the frozen ledger.

Measured runs create a compact JSON report in ``evals/benchmarks/records/`` and
a matching human-readable entry in ``evals/benchmarks/entries/``.  The generated
``evals/benchmarks/README.md`` is an index of those new entries.  The historical
``ledger.md`` and its pre-migration records are deliberately never read or
modified by this script.

Use ``--rebuild-index`` after hand-authoring a ``NO_EVAL`` entry, and use
``--check`` in CI to verify both entry validity and index freshness.  This file
uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO_ROOT / "evals" / "benchmarks"
ENTRIES_DIR = BENCH_DIR / "entries"
RECORDS_DIR = BENCH_DIR / "records"
INDEX = BENCH_DIR / "README.md"
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"

MISSING = "—"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
MAX_SLUG_LENGTH = 60
MAX_ID_LENGTH = 71  # YYYY-MM-DD- plus the historical 60-character label slug.
UNICODE_LINE_SEPARATORS = ("\u0085", "\u2028", "\u2029")
FRONTMATTER_KEYS = (
    "id", "date", "label", "plugin_version", "status", "scenarios", "record",
)
MEASURED_STATUSES = {"PASS", "FAIL", "ERROR", "MIXED"}
DP_SCENARIO_REPORT_VERSION = 1
DP_PAIRED_SCENARIOS = frozenset({"crm-pipeline", "finance-close", "inventory-position"})
DP_GATE_NAMES = (
    "intake", "capability", "narrowing", "construction", "build", "query", "follow-up",
)
DP_MANIFEST_FIELDS = (
    "agent_model_id",
    "agent_sampling_params",
    "driver_model_id",
    "driver_sampling_params",
    "judge_model_id",
    "judge_prompt_hash",
    "skill_pack_version",
    "supervisor_version",
    "nxd_data_product_wheel_version",
    "fixture_dir_hash",
    "mock_api_version",
    "operator_script_hash",
    "turn_budget",
    "grant_fixture_hash",
    "scenario_id",
    "tier",
    "trial_index",
    "canary_claims_hash",
    "persona_paraphrase_prompt_hash",
    "judge_calibration_set_hash",
    "fixture_seed",
    "fixture_base_instant",
    "run_id",
    "session_config_sha256",
    "runtime_knobs",
    "validation_mode",
)
# These are the fields emitted by ``Manifest.to_dict``.  The six desktop
# session fields are accepted as producer output, but are intentionally not
# retained in a compact benchmark record because they are local paths (or a
# path-adjacent runtime identity).  The retained subset above is the public
# benchmark pin contract and every one of its fields is required below.
DP_PRODUCER_MANIFEST_FIELDS = (
    "agent_model_id",
    "agent_sampling_params",
    "judge_model_id",
    "judge_prompt_hash",
    "skill_pack_version",
    "supervisor_version",
    "nxd_data_product_wheel_version",
    "fixture_dir_hash",
    "mock_api_version",
    "operator_script_hash",
    "driver_model_id",
    "driver_sampling_params",
    "turn_budget",
    "grant_fixture_hash",
    "scenario_id",
    "tier",
    "trial_index",
    "canary_claims_hash",
    "persona_paraphrase_prompt_hash",
    "judge_calibration_set_hash",
    "fixture_seed",
    "fixture_base_instant",
    "run_id",
    "supervisor_binary_path",
    "session_root",
    "session_config_path",
    "session_config_sha256",
    "session_trace_path",
    "session_server_result_path",
    "runtime_knobs",
    "validation_mode",
)
DP_DROPPED_MANIFEST_FIELDS = frozenset(DP_PRODUCER_MANIFEST_FIELDS) - frozenset(DP_MANIFEST_FIELDS)
DP_MANIFEST_STRING_FIELDS = frozenset(
    {
        "agent_model_id",
        "judge_model_id",
        "judge_prompt_hash",
        "skill_pack_version",
        "supervisor_version",
        "nxd_data_product_wheel_version",
        "fixture_dir_hash",
        "mock_api_version",
        "operator_script_hash",
        "grant_fixture_hash",
        "scenario_id",
        "tier",
        "canary_claims_hash",
        "persona_paraphrase_prompt_hash",
        "judge_calibration_set_hash",
        "fixture_base_instant",
        "run_id",
        "session_config_sha256",
        "validation_mode",
    }
)
DP_MANIFEST_HASH_FIELDS = frozenset(
    {
        "judge_prompt_hash",
        "fixture_dir_hash",
        "operator_script_hash",
        "grant_fixture_hash",
        "canary_claims_hash",
        "persona_paraphrase_prompt_hash",
        "judge_calibration_set_hash",
        "session_config_sha256",
    }
)
DP_TIER_VALUES = frozenset({"smoke", "T0", "core", "live"})
DP_VALIDATION_MODES = frozenset({"live", "replay"})
DP_AGENT_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
DP_ROUTE_FIDELITY_STATUSES = frozenset({"examined", "unexamined", "not-applicable"})
DP_REPLAY_STATUSES = frozenset({"verified", "mismatch", "not-attempted"})
DP_OPERATOR_MODES = frozenset({"scripted", "generated_surface", "driver"})
DP_QUALIFICATION_DISPOSITIONS = frozenset({"CERTIFIED", "QUALIFIED", "OBSERVED", "REJECTED", "INVALID"})
DP_TERMINAL_STATES = frozenset({
    "completed", "script_exhausted", "sentinel_trip", "environment_wedge", "turn_timeout",
})
DP_FAILURE_MODES = frozenset({
    "sentinel_trip", "environment_wedge", "turn_timeout", "one_obstacle_per_turn",
    "intake_failure", "turn_budget_exceeded", "operator_fallback",
})
DP_FAILURE_REASONS = frozenset({
    "provider_session_limit", "child_no_terminal_result", "child_exited_early",
    "shared_runtime_contention", "interrupted_unclassified",
})
DP_SCORE_STATES = frozenset({"passed", "failed", "invalid", "ungraded", "automatic zero"})
DP_RAW_REPORT_FIELDS = frozenset({
    "verdict", "canary", "scenarios", "max_workers", "blocked_reason",
    "clean_tier_means", "report_format_version", "efficiency_is_reported_only",
})
DP_COMPACT_REPORT_FIELDS = frozenset({"report_format_version", "scenarios"})
DP_RAW_SCENARIO_FIELDS = frozenset({"scenario_id", "runs", "repeatability"})
DP_COMPACT_SCENARIO_FIELDS = frozenset({"scenario_id", "runs"})
DP_RAW_RUN_FIELDS = frozenset({
    "scenario_id", "epoch", "terminal_state", "stop_condition", "failure_modes",
    "ungraded_criteria", "score", "efficiency", "manifest", "replay_recording",
    "bundle_digest", "replay_verification", "qualification", "interruption",
    "route_fidelity",
})
DP_COMPACT_RUN_FIELDS = frozenset({
    "skill_set", "scenario_id", "result", "epoch", "terminal_state",
    "ungraded_criteria", "score", "efficiency", "manifest", "qualification",
    "interruption", "route_fidelity",
})
DP_SCORE_FIELDS = frozenset({
    "gates", "total", "scoreable_max", "threshold", "waived_gates",
    "hard_gate_flags", "state", "findings",
})
DP_RAW_GATE_FIELDS = frozenset({
    "passed", "points", "codes", "examined", "ungraded", "required", "diagnostics",
})
DP_COMPACT_GATE_FIELDS = DP_RAW_GATE_FIELDS - {"diagnostics"}
DP_HARD_GATE_FIELDS = frozenset({"honesty", "route_fidelity", "sentinel", "gold_access"})
DP_RUNTIME_FIELDS = frozenset({"schema_version", "transform_window", "broker_fault", "workflow_switch"})
DP_TRANSFORM_ARITHMETIC_FIELDS = frozenset({
    "naive_plan", "naive_calls", "naive_total_calls", "naive_lower_bound_ms",
    "naive_required_ms", "naive_margin_ms", "bounded_plan", "bounded_calls",
    "bounded_total_calls", "bounded_upper_bound_ms", "bounded_allowed_ms",
    "bounded_margin_ms", "per_call_latency_ms", "window_ms", "route_keys",
    "bounds_hold", "method",
})
DP_BROKER_ENABLED_FIELDS = frozenset({
    "enabled", "active_attempt", "active_fault", "faults", "bind_timeout_s",
    "margin_s", "entrypoint",
})
DP_BROKER_DISABLED_FIELDS = frozenset({"enabled", "active_attempt", "active_fault"})
DP_WORKFLOW_ENABLED_FIELDS = frozenset({"enabled", "from_workflow", "to_workflow", "assertion"})
DP_REPLAY_FIELDS = frozenset({"format_version", "turns", "manifest", "supervisor_facts", "metadata"})
DP_RECORDED_TURN_FIELDS = frozenset({"operator_message", "result"})
DP_OPERATOR_MESSAGE_FIELDS = frozenset({"text", "attachments"})
DP_ATTACHMENT_FIELDS = frozenset({"name", "content", "kind"})
DP_TURN_RESULT_FIELDS = frozenset({
    "transcript_delta", "agent_message", "tool_calls", "tool_results", "files_touched",
    "approval_artifact", "build_failed", "build_failure_count", "reported",
    "environment_wedged", "turn_timed_out", "environment_detail", "failure_reason",
    "last_mcp_call", "session_id", "terminal_result_count", "terminal_result_subtype",
    "terminal_result_is_error",
})
DP_TOOL_CALL_FIELDS = frozenset({"name", "arguments", "result"})
DP_TOUCHED_FILE_FIELDS = frozenset({"path", "content"})
DP_SUPERVISOR_FACT_FIELDS = frozenset({
    "run_id", "artifact_id", "publish_sequence", "per_model_row_counts", "lifecycle_state",
})
DP_REPLAY_METADATA_FIELDS = frozenset({"touched_file_contents_redacted"})
# The pack version is the treatment. Run IDs and local filesystem locations
# identify one execution, not the inputs that make two arms comparable.
DP_COMPARABILITY_FIELDS = tuple(
    field for field in DP_MANIFEST_FIELDS
    if field not in {"skill_pack_version", "run_id"}
)
DP_REQUIRED_IDENTITY_FIELDS = ("skill_pack_version", "run_id")
DP_CLEAN_TERMINAL_STATES = frozenset({"completed"})
DP_INTERRUPTED_TERMINAL_STATES = frozenset({
    "sentinel_trip", "environment_wedge", "script_exhausted", "turn_timeout",
})
DP_ERROR_SCORE_STATES = frozenset({"automatic zero", "invalid", "ungraded"})
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
DP_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]*$")
DP_CANARY_FIELDS = frozenset({"verdict", "claims_hash", "probe", "build", "package"})
DP_CANARY_VERDICT_FIELDS = frozenset({
    "outcome", "blocking", "observed_codes", "issues", "advisories",
})
DP_CANARY_ISSUE_FIELDS = frozenset({
    "kind", "message", "claim_id", "code", "skill_file", "line",
})
DP_CANARY_PROBE_FIELDS = frozenset({"report", "returncode", "stderr", "supervisor_digest"})
DP_CANARY_BUILD_FIELDS = frozenset({
    "diagnostic", "returncode", "stderr", "stdout", "supervisor_digest",
})
DP_SUPERVISOR_REPORT_FIELDS = frozenset({
    "duration_ms", "outcome", "provenance", "stages", "workflow", "probe_id",
})
DP_SUPERVISOR_STAGE_FIELDS = frozenset({"stage", "status", "checks"})
DP_SUPERVISOR_CHECK_FIELDS = frozenset({"code", "detail", "status", "subject"})
DP_SUPERVISOR_PROVENANCE_FIELDS = frozenset({
    "closure_path", "definition_id", "package_paths", "packages", "pinned_closure_path",
    "python", "python_executable", "python_version", "self_check_path", "self_check_sha256",
    "spec_compiler_path", "spec_compiler_sha256", "supervisor_version",
})
DP_REPEATABILITY_FIELDS = frozenset({
    "tier", "required_epochs", "observed_epochs", "certified", "rates",
    "excluded_invalid", "excluded_truncated", "demonstrated_once",
})
DP_RATE_FIELDS = frozenset({"passed", "examined", "rate", "wilson_lower_bound"})
DP_DEMONSTRATED_ONCE_FIELDS = frozenset({"state", "gates"})
DP_HASH_RE = re.compile(r"^(?:[0-9a-f]{64}|sha256:[0-9a-f]{64})$")
DP_VERSION_RE = re.compile(r"^(?:[0-9]+\.[0-9]+\.[0-9]+|sha256:[0-9a-f]{64})$")
DP_WHEEL_VERSION_RE = re.compile(
    r"^(?:[0-9]+\.[0-9]+\.[0-9]+|python-[0-9]+\.[0-9]+\.[0-9]+:sha256:[0-9a-f]{64})$"
)
DP_MOCK_VERSION_RE = re.compile(r"^(?:[0-9]+\.[0-9]+\.[0-9]+|mock-(?:v)?[0-9]+)$")
DP_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+~-]{0,254}$")
DP_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T")
DP_CREDENTIAL_RE = re.compile(
    # Bare vocabulary such as ``credential-rotation`` and ``tokenized`` is
    # producer data, not a secret. Reject only a credential scheme or a
    # credential-named key carrying a value.
    r"(?i)(?:\b(?:bearer|basic)\s+\S+|\b(?:api[_-]?key|secret|token|password|passwd|authorization|credential)\s*[:=]\s*\S+)"
)
# These are local filesystem roots, not route paths such as ``/deals``.  The
# latter is a legitimate runtime knob value; the former must never survive in
# a retained manifest or sampling field.
DP_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:/(?:private|tmp|Users|home|Volumes|var|etc|opt)(?:/|$)|[A-Za-z]:[\\/]|\\\\)"
)


class BenchmarkError(ValueError):
    """A user-facing benchmark evidence validation error."""


@dataclass(frozen=True)
class Entry:
    path: Path
    frontmatter: dict[str, Any]
    body: str


def parse_report_arg(spec: str) -> tuple[str, Path]:
    """Split ``tag=path`` (or bare ``path``) into ``(tag, path)``."""
    tag, sep, path = spec.partition("=")
    if not sep:
        return "", Path(spec)
    return tag.strip(), Path(path.strip())


def validate_date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise BenchmarkError(f"invalid date {value!r}; expected YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise BenchmarkError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


def validate_id(value: str) -> str:
    if (not isinstance(value, str) or len(value) > MAX_ID_LENGTH
            or not ID_RE.fullmatch(value)):
        raise BenchmarkError(
            f"id must be a lowercase hyphenated slug no longer than {MAX_ID_LENGTH} characters"
        )
    return value


def validate_semver(value: Any, field: str = "plugin_version") -> str:
    if not isinstance(value, str) or not SEMVER_RE.fullmatch(value):
        raise BenchmarkError(f"{field} must be a semver X.Y.Z string")
    return value


def yaml_quote(value: str) -> str:
    """Emit a YAML-safe scalar using JSON's compatible double-quoted syntax."""
    # ASCII escapes keep U+0085/U+2028/U+2029 inside a scalar. ``splitlines``
    # treats all three as line breaks, so literal output would not round-trip.
    return json.dumps(value, ensure_ascii=True)


def yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value == "null":
        return None
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"invalid quoted YAML scalar {value!r}") from exc
        if not isinstance(parsed, str):
            raise BenchmarkError("frontmatter scalar must be a string or null")
        return parsed
    if not value or value.startswith(("'", "[", "{", "- ")):
        raise BenchmarkError(f"unsupported YAML scalar {value!r}; use a quoted string")
    return value


def write_frontmatter(values: dict[str, Any]) -> str:
    """Write the deliberately small, stdlib-only YAML frontmatter subset."""
    if set(values) != set(FRONTMATTER_KEYS):
        raise BenchmarkError("writer received unexpected frontmatter keys")
    lines = ["---"]
    for key in FRONTMATTER_KEYS:
        value = values[key]
        if key == "scenarios":
            if not value:
                lines.append("scenarios: []")
            else:
                lines.append("scenarios:")
                for scenario in value:
                    lines.append(f"  - {yaml_quote(scenario)}")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {yaml_quote(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse the restricted YAML used by benchmark entries, without PyYAML."""
    if not text.startswith("---\n"):
        raise BenchmarkError("entry must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise BenchmarkError("entry frontmatter is missing its closing ---")
    raw, body = text[4:end], text[end + 5:]
    if any(separator in raw for separator in UNICODE_LINE_SEPARATORS):
        raise BenchmarkError("frontmatter must escape Unicode line separators")
    values: dict[str, Any] = {}
    lines = raw.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith(" ") or ":" not in line:
            raise BenchmarkError(f"malformed frontmatter line {line!r}")
        key, value = line.split(":", 1)
        if key not in FRONTMATTER_KEYS:
            raise BenchmarkError(f"unknown frontmatter field {key!r}")
        if key in values:
            raise BenchmarkError(f"duplicate frontmatter field {key!r}")
        if key == "scenarios":
            if value.strip() == "[]":
                values[key] = []
                index += 1
                continue
            if value.strip():
                raise BenchmarkError("scenarios must be a YAML list")
            scenarios: list[str] = []
            index += 1
            while index < len(lines) and lines[index].startswith("  - "):
                scenario = yaml_scalar(lines[index][4:])
                if not isinstance(scenario, str):
                    raise BenchmarkError("scenario names must be strings")
                scenarios.append(scenario)
                index += 1
            values[key] = scenarios
            continue
        values[key] = yaml_scalar(value)
        index += 1
    missing = set(FRONTMATTER_KEYS) - set(values)
    if missing:
        raise BenchmarkError("missing required frontmatter fields: " + ", ".join(sorted(missing)))
    return values, body


def escape_cell(value: Any) -> str:
    """Keep generated Markdown tables valid even when reports contain odd text."""
    text = str(value)
    return (text.replace("\\", "\\\\").replace("|", "\\|")
            .replace("\r\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")
            .replace("\u0085", "<br>").replace("\u2028", "<br>").replace("\u2029", "<br>"))


def is_dp_scenarios_report(report: Any) -> bool:
    """Return whether this is the versioned dp-scenarios machine format."""

    return (
        isinstance(report, dict)
        and report.get("report_format_version") == DP_SCENARIO_REPORT_VERSION
        and "scenarios" in report
    )


def _legacy_cell_rows(tag: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    """Render the original evals/run.py report shape unchanged."""

    if not isinstance(report, dict):
        raise BenchmarkError("report must be a JSON object")
    results = report.get("results", [])
    if not isinstance(results, list):
        raise BenchmarkError("report results must be a list")
    rows = []
    for res in results:
        if not isinstance(res, dict):
            raise BenchmarkError("report result must be an object")
        verdict = res.get("verdict", {}) or {}
        metrics = res.get("metrics", {}) or {}
        if not isinstance(verdict, dict) or not isinstance(metrics, dict):
            raise BenchmarkError("report verdict and metrics must be objects")
        checks = verdict.get("checks", []) or []
        if not isinstance(checks, list) or any(not isinstance(check, dict) for check in checks):
            raise BenchmarkError("report verdict checks must be a list of objects")
        n_pass = sum(1 for check in checks if check.get("pass"))
        if not res.get("ok"):
            status = "ERROR"
        else:
            status = "PASS" if verdict.get("overall_pass") else "FAIL"
        cost = metrics.get("total_cost_usd")
        rows.append({
            "tag": tag or MISSING,
            "skill_set": res.get("skill_set", MISSING),
            "scenario": res.get("scenario", MISSING),
            "status": status,
            "checks": f"{n_pass}/{len(checks)}" if checks else MISSING,
            "num_turns": metrics.get("num_turns", MISSING),
            "tool_calls": metrics.get("tool_calls", MISSING),
            "output_tokens": metrics.get("output_tokens", MISSING),
            "cost_usd": f"{cost:.2f}" if isinstance(cost, (int, float)) else MISSING,
            # A desktop-path scenario can pin a model per run, so report-level
            # metadata is only a fallback.
            "agent_model": metrics.get("agent_model", report.get("agent_model", MISSING)),
        })
    return rows


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _exact_keys(value: Any, expected: set[str] | frozenset[str], path: str,
                *, required: set[str] | frozenset[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BenchmarkError(f"{path} must be an object")
    unknown = set(value) - set(expected)
    if unknown:
        names = ", ".join(sorted(str(name) for name in unknown))
        raise BenchmarkError(f"{path} has unknown field(s): {names}")
    missing = set(required or ()) - set(value)
    if missing:
        names = ", ".join(sorted(missing))
        raise BenchmarkError(f"{path} is missing field(s): {names}")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkError(f"{path} must be a non-empty string")
    return value


def _safe_text(value: Any, path: str) -> str:
    """Validate a retained string without retaining secrets or local paths."""

    text = _text(value, path)
    if any(ord(character) < 32 for character in text):
        raise BenchmarkError(f"{path} contains a control character")
    if DP_CREDENTIAL_RE.search(text) or DP_LOCAL_PATH_RE.search(text):
        raise BenchmarkError(f"{path} contains credential or local path material")
    return text


def _identifier(value: Any, path: str) -> str:
    """Validate a producer identifier, including its lexical safety."""

    text = _safe_text(value, path)
    if not DP_IDENTIFIER_RE.fullmatch(text):
        raise BenchmarkError(f"{path} must be a producer identifier")
    return text


def _hash(value: Any, path: str, *, allow_not_applicable: bool = True) -> str:
    """Validate the digest spellings emitted by dp-scenarios producers."""

    text = _safe_text(value, path)
    if allow_not_applicable and text == "not-applicable":
        return text
    if not DP_HASH_RE.fullmatch(text):
        raise BenchmarkError(f"{path} must be a sha256 digest")
    return text


def _nullable_hash(value: Any, path: str) -> None:
    if value is not None:
        _hash(value, path, allow_not_applicable=False)


def _version(value: Any, path: str) -> str:
    text = _safe_text(value, path)
    if not DP_VERSION_RE.fullmatch(text):
        raise BenchmarkError(f"{path} must be a semver or sha256 version pin")
    return text


def _wheel_version(value: Any, path: str) -> str:
    text = _safe_text(value, path)
    if not DP_WHEEL_VERSION_RE.fullmatch(text):
        raise BenchmarkError(f"{path} must be a semver or pinned Python wheel version")
    return text


def _mock_version(value: Any, path: str) -> str:
    text = _safe_text(value, path)
    if not DP_MOCK_VERSION_RE.fullmatch(text):
        raise BenchmarkError(f"{path} must be a mock-vN or semver version")
    return text


def _timestamp(value: Any, path: str) -> str:
    text = _safe_text(value, path)
    if not DP_TIMESTAMP_RE.match(text):
        raise BenchmarkError(f"{path} must be an ISO-8601 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise BenchmarkError(f"{path} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise BenchmarkError(f"{path} must include a timezone")
    return text


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise BenchmarkError(f"{path} must be a string")
    return value


def _enum(value: Any, allowed: set[str] | frozenset[str], path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise BenchmarkError(f"{path} has an unsupported value")
    return value


def _nullable_text(value: Any, path: str) -> None:
    if value is not None and not isinstance(value, str):
        raise BenchmarkError(f"{path} must be a string or null")


def _encoded_bytes(value: Any, path: str) -> None:
    """Validate the JSON form emitted for a bytes-valued producer field."""

    if isinstance(value, str):
        return
    raw = _exact_keys(value, {"__bytes__"}, path, required={"__bytes__"})
    encoded = raw["__bytes__"]
    if not isinstance(encoded, str):
        raise BenchmarkError(f"{path}.__bytes__ must be a string")
    try:
        base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise BenchmarkError(f"{path}.__bytes__ must be valid base64") from exc


def _encoded_path(value: Any, path: str) -> None:
    if isinstance(value, str):
        return
    raw = _exact_keys(value, {"__path__"}, path, required={"__path__"})
    _string(raw["__path__"], f"{path}.__path__")


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise BenchmarkError(f"{path} must be a boolean")
    return value


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BenchmarkError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise BenchmarkError(f"{path} must be at least {minimum}")
    return value


def _number(value: Any, path: str, *, minimum: float | None = None,
            maximum: float | None = None) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkError(f"{path} must be a number")
    if not math.isfinite(float(value)):
        raise BenchmarkError(f"{path} must be finite")
    if minimum is not None and value < minimum:
        raise BenchmarkError(f"{path} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise BenchmarkError(f"{path} must be at most {maximum}")
    return value


def _code(value: Any, path: str) -> str:
    text = _safe_text(value, path)
    if not DP_CODE_RE.fullmatch(text):
        raise BenchmarkError(f"{path} must be a non-empty code")
    return text


def _nullable_code(value: Any, path: str) -> None:
    if value is not None:
        _code(value, path)


def _code_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise BenchmarkError(f"{path} must be an array")
    result = []
    for index, item in enumerate(value):
        result.append(_code(item, f"{path}[{index}]"))
    return result


def _validate_count_map(value: Any, path: str) -> None:
    if not isinstance(value, dict):
        raise BenchmarkError(f"{path} must be an object")
    raw = value
    if not raw:
        raise BenchmarkError(f"{path} must be a non-empty object")
    keys = list(raw)
    if any(not isinstance(key, str) or not key.strip() for key in keys):
        raise BenchmarkError(f"{path} keys must be non-empty strings")
    if keys != sorted(keys):
        raise BenchmarkError(f"{path} keys must be sorted")
    for key, item in raw.items():
        _integer(item, f"{path}[{key!r}]", minimum=1)


def _validate_transform_arithmetic(value: Any, path: str) -> None:
    raw = _exact_keys(value, DP_TRANSFORM_ARITHMETIC_FIELDS, path,
                      required=DP_TRANSFORM_ARITHMETIC_FIELDS)
    for name in ("naive_plan", "bounded_plan"):
        _identifier(raw[name], f"{path}.{name}")
    _safe_text(raw["method"], f"{path}.method")
    if raw["method"] != "declared_call_count_times_fixed_latency":
        raise BenchmarkError(f"{path}.method has an unsupported value")
    _validate_count_map(raw["naive_calls"], f"{path}.naive_calls")
    _validate_count_map(raw["bounded_calls"], f"{path}.bounded_calls")
    for name in (
        "naive_total_calls", "naive_lower_bound_ms", "naive_required_ms", "naive_margin_ms",
        "bounded_total_calls", "bounded_upper_bound_ms", "bounded_allowed_ms",
        "bounded_margin_ms", "per_call_latency_ms", "window_ms",
    ):
        _integer(raw[name], f"{path}.{name}", minimum=0)
    if raw["per_call_latency_ms"] < 1 or raw["window_ms"] < 1:
        raise BenchmarkError(f"{path} latency and window must be positive")
    raw_route_keys = raw["route_keys"]
    if not isinstance(raw_route_keys, list):
        raise BenchmarkError(f"{path}.route_keys must be an array")
    for index, item in enumerate(raw_route_keys):
        _safe_text(item, f"{path}.route_keys[{index}]")
    if raw_route_keys != sorted(set(raw_route_keys)):
        raise BenchmarkError(f"{path}.route_keys must be unique and sorted")
    _boolean(raw["bounds_hold"], f"{path}.bounds_hold")

    naive_calls = sum(raw["naive_calls"].values())
    bounded_calls = sum(raw["bounded_calls"].values())
    if raw["naive_total_calls"] != naive_calls or raw["bounded_total_calls"] != bounded_calls:
        raise BenchmarkError(f"{path} total call counts disagree with call maps")
    if raw["naive_lower_bound_ms"] != naive_calls * raw["per_call_latency_ms"]:
        raise BenchmarkError(f"{path}.naive_lower_bound_ms disagrees with its producer inputs")
    if raw["bounded_upper_bound_ms"] != bounded_calls * raw["per_call_latency_ms"]:
        raise BenchmarkError(f"{path}.bounded_upper_bound_ms disagrees with its producer inputs")
    if raw["naive_required_ms"] != 2 * raw["window_ms"]:
        raise BenchmarkError(f"{path}.naive_required_ms disagrees with window_ms")
    if raw["bounded_allowed_ms"] != raw["window_ms"] // 2:
        raise BenchmarkError(f"{path}.bounded_allowed_ms disagrees with window_ms")
    if raw["naive_margin_ms"] != raw["naive_lower_bound_ms"] - raw["naive_required_ms"]:
        raise BenchmarkError(f"{path}.naive_margin_ms disagrees with its producer inputs")
    if raw["bounded_margin_ms"] != raw["bounded_allowed_ms"] - raw["bounded_upper_bound_ms"]:
        raise BenchmarkError(f"{path}.bounded_margin_ms disagrees with its producer inputs")
    expected_bounds = (
        raw["naive_lower_bound_ms"] >= raw["naive_required_ms"]
        and raw["bounded_upper_bound_ms"] <= raw["bounded_allowed_ms"]
    )
    if raw["bounds_hold"] != expected_bounds:
        raise BenchmarkError(f"{path}.bounds_hold disagrees with its producer inputs")


def _validate_runtime_knobs(value: Any, path: str) -> None:
    raw = _exact_keys(value, DP_RUNTIME_FIELDS, path, required=DP_RUNTIME_FIELDS)
    _integer(raw["schema_version"], f"{path}.schema_version", minimum=1)
    if raw["schema_version"] != 1:
        raise BenchmarkError(f"{path}.schema_version must be 1")

    transform = raw["transform_window"]
    if not isinstance(transform, dict):
        raise BenchmarkError(f"{path}.transform_window must be an object")
    enabled = transform.get("enabled")
    _boolean(enabled, f"{path}.transform_window.enabled")
    if enabled is False:
        _exact_keys(transform, {"enabled"}, f"{path}.transform_window", required={"enabled"})
    else:
        _exact_keys(transform, {"enabled", "arithmetic"}, f"{path}.transform_window",
                    required={"enabled", "arithmetic"})
        _validate_transform_arithmetic(transform["arithmetic"], f"{path}.transform_window.arithmetic")

    broker = raw["broker_fault"]
    if not isinstance(broker, dict):
        raise BenchmarkError(f"{path}.broker_fault must be an object")
    broker_enabled = broker.get("enabled")
    _boolean(broker_enabled, f"{path}.broker_fault.enabled")
    if broker_enabled is False:
        _exact_keys(broker, DP_BROKER_DISABLED_FIELDS, f"{path}.broker_fault",
                    required=DP_BROKER_DISABLED_FIELDS)
        _integer(broker["active_attempt"], f"{path}.broker_fault.active_attempt", minimum=1)
        if broker["active_fault"] != "none":
            raise BenchmarkError(f"{path}.broker_fault.active_fault must be 'none' when disabled")
    else:
        _exact_keys(broker, DP_BROKER_ENABLED_FIELDS, f"{path}.broker_fault",
                    required=DP_BROKER_ENABLED_FIELDS)
        _integer(broker["active_attempt"], f"{path}.broker_fault.active_attempt", minimum=1)
        _enum(broker["active_fault"], {"none", "sleep_past_bind_timeout", "occupied_port"},
              f"{path}.broker_fault.active_fault")
        faults = broker["faults"]
        if not isinstance(faults, dict):
            raise BenchmarkError(f"{path}.broker_fault.faults must be an object")
        if not faults:
            raise BenchmarkError(f"{path}.broker_fault.faults must be a non-empty object")
        if any(not isinstance(attempt, str) for attempt in faults):
            raise BenchmarkError(f"{path}.broker_fault.faults keys must be positive integers")
        if list(faults) != sorted(faults):
            raise BenchmarkError(f"{path}.broker_fault.faults keys must be sorted")
        for attempt, shape in faults.items():
            if not re.fullmatch(r"[1-9][0-9]*", attempt):
                raise BenchmarkError(f"{path}.broker_fault.faults keys must be positive integers")
            _enum(shape, {"sleep_past_bind_timeout", "occupied_port"},
                  f"{path}.broker_fault.faults[{attempt!r}]")
        # The manifest producer deliberately calls this field ``entrypoint``;
        # the CLI input decoder's ``real_entrypoint`` is not a report field.
        if broker["entrypoint"] != "process-level-semantic-entrypoint-shim":
            raise BenchmarkError(f"{path}.broker_fault.entrypoint has an unsupported value")
        _integer(broker["bind_timeout_s"], f"{path}.broker_fault.bind_timeout_s", minimum=1)
        _integer(broker["margin_s"], f"{path}.broker_fault.margin_s", minimum=1)

    workflow = raw["workflow_switch"]
    if not isinstance(workflow, dict):
        raise BenchmarkError(f"{path}.workflow_switch must be an object")
    workflow_enabled = workflow.get("enabled")
    _boolean(workflow_enabled, f"{path}.workflow_switch.enabled")
    if workflow_enabled is False:
        _exact_keys(workflow, {"enabled"}, f"{path}.workflow_switch", required={"enabled"})
    else:
        _exact_keys(workflow, DP_WORKFLOW_ENABLED_FIELDS, f"{path}.workflow_switch",
                    required=DP_WORKFLOW_ENABLED_FIELDS)
        _identifier(workflow["from_workflow"], f"{path}.workflow_switch.from_workflow")
        _identifier(workflow["to_workflow"], f"{path}.workflow_switch.to_workflow")
        if workflow["from_workflow"] == workflow["to_workflow"]:
            raise BenchmarkError(f"{path}.workflow_switch workflows must differ")
        if workflow["assertion"] != "first_post_switch_call_answers_from_new_workflow_endpoint":
            raise BenchmarkError(f"{path}.workflow_switch.assertion has an unsupported value")


def _validate_agent_sampling(value: Any, path: str, validation_mode: str) -> None:
    if validation_mode == "live":
        raw = _exact_keys(value, {"effort", "temperature"}, path,
                          required={"effort", "temperature"})
        _enum(raw["effort"], DP_AGENT_EFFORTS, f"{path}.effort")
        _safe_text(raw["effort"], f"{path}.effort")
        if raw["temperature"] != "provider-default":
            raise BenchmarkError(f"{path}.temperature must be 'provider-default' for live runs")
        _safe_text(raw["temperature"], f"{path}.temperature")
        return
    raw = _exact_keys(value, {"temperature"}, path, required={"temperature"})
    _number(raw["temperature"], f"{path}.temperature", minimum=0, maximum=2)


def _validate_driver_sampling(value: Any, path: str, driver_model_id: str) -> None:
    if driver_model_id == "not-applicable":
        _exact_keys(value, set(), path)
        return
    raw = _exact_keys(value, {"temperature", "max_tokens", "prompt_hash"}, path,
                      required={"temperature", "max_tokens", "prompt_hash"})
    _number(raw["temperature"], f"{path}.temperature", minimum=0, maximum=2)
    _integer(raw["max_tokens"], f"{path}.max_tokens", minimum=1)
    _hash(raw["prompt_hash"], f"{path}.prompt_hash", allow_not_applicable=False)


def _validate_manifest(value: Any, path: str, *, compact: bool) -> None:
    expected = set(DP_MANIFEST_FIELDS) if compact else set(DP_PRODUCER_MANIFEST_FIELDS)
    raw = _exact_keys(value, expected, path, required=expected)
    for field in DP_DROPPED_MANIFEST_FIELDS:
        if field in raw:
            _text(raw[field], f"{path}.{field}")

    for field in DP_MANIFEST_STRING_FIELDS:
        if field in DP_MANIFEST_HASH_FIELDS:
            _hash(raw[field], f"{path}.{field}")
        elif field == "skill_pack_version":
            validate_semver(raw[field], f"{path}.{field}")
            _safe_text(raw[field], f"{path}.{field}")
        elif field == "supervisor_version":
            _version(raw[field], f"{path}.{field}")
        elif field == "nxd_data_product_wheel_version":
            _wheel_version(raw[field], f"{path}.{field}")
        elif field == "mock_api_version":
            _mock_version(raw[field], f"{path}.{field}")
        elif field == "fixture_base_instant":
            _timestamp(raw[field], f"{path}.{field}")
        elif field in {"agent_model_id", "judge_model_id", "scenario_id", "run_id"}:
            _identifier(raw[field], f"{path}.{field}")
        else:
            _safe_text(raw[field], f"{path}.{field}")
    _identifier(raw["driver_model_id"], f"{path}.driver_model_id")
    _enum(raw["tier"], DP_TIER_VALUES, f"{path}.tier")
    _enum(raw["validation_mode"], DP_VALIDATION_MODES, f"{path}.validation_mode")
    _integer(raw["turn_budget"], f"{path}.turn_budget", minimum=1)
    _integer(raw["trial_index"], f"{path}.trial_index", minimum=0)
    _integer(raw["fixture_seed"], f"{path}.fixture_seed", minimum=0)
    _validate_agent_sampling(raw["agent_sampling_params"], f"{path}.agent_sampling_params",
                             raw["validation_mode"])
    _validate_driver_sampling(raw["driver_sampling_params"], f"{path}.driver_sampling_params",
                              raw["driver_model_id"])
    _validate_runtime_knobs(raw["runtime_knobs"], f"{path}.runtime_knobs")


def _validate_diagnostics(value: Any, path: str) -> None:
    if not isinstance(value, list):
        raise BenchmarkError(f"{path} must be an array")
    for index, item in enumerate(value):
        raw = _exact_keys(item, {"code", "detail", "value"}, f"{path}[{index}]",
                          required={"code", "detail", "value"})
        _code(raw["code"], f"{path}[{index}].code")
        _string(raw["detail"], f"{path}[{index}].detail")


def _validate_failure_modes(value: Any, path: str) -> list[str]:
    """Validate the closed failure-mode values emitted by the operator."""

    if not isinstance(value, list):
        raise BenchmarkError(f"{path} must be an array")
    return [
        _enum(item, DP_FAILURE_MODES, f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


def _validate_supervisor_facts(value: Any, path: str) -> None:
    """Validate the five categories copied from ``SupervisorFacts``."""

    raw = _exact_keys(value, DP_SUPERVISOR_FACT_FIELDS, path,
                      required=DP_SUPERVISOR_FACT_FIELDS)
    _identifier(raw["run_id"], f"{path}.run_id")
    _identifier(raw["artifact_id"], f"{path}.artifact_id")
    publish_sequence = raw["publish_sequence"]
    if isinstance(publish_sequence, bool):
        raise BenchmarkError(f"{path}.publish_sequence must be a non-negative integer")
    if isinstance(publish_sequence, int):
        if publish_sequence < 0:
            raise BenchmarkError(f"{path}.publish_sequence must be a non-negative integer")
    elif isinstance(publish_sequence, str):
        _safe_text(publish_sequence, f"{path}.publish_sequence")
        if not re.fullmatch(r"0|[1-9][0-9]*", publish_sequence):
            raise BenchmarkError(f"{path}.publish_sequence must be a non-negative integer")
    else:
        raise BenchmarkError(f"{path}.publish_sequence must be a non-negative integer")
    _identifier(raw["lifecycle_state"], f"{path}.lifecycle_state")
    counts = raw["per_model_row_counts"]
    if not isinstance(counts, dict) or not counts:
        raise BenchmarkError(f"{path}.per_model_row_counts must be a non-empty object")
    for model, count in counts.items():
        _identifier(model, f"{path}.per_model_row_counts key")
        if isinstance(count, bool):
            raise BenchmarkError(f"{path}.per_model_row_counts.{model} must be a non-negative integer")
        if isinstance(count, int):
            if count < 0:
                raise BenchmarkError(f"{path}.per_model_row_counts.{model} must be a non-negative integer")
        elif isinstance(count, str):
            _safe_text(count, f"{path}.per_model_row_counts.{model}")
            if not re.fullmatch(r"0|[1-9][0-9]*", count):
                raise BenchmarkError(f"{path}.per_model_row_counts.{model} must be a non-negative integer")
        else:
            raise BenchmarkError(f"{path}.per_model_row_counts.{model} must be a non-negative integer")


def _validate_issue(value: Any, path: str) -> None:
    issue = _exact_keys(value, DP_CANARY_ISSUE_FIELDS, path,
                        required=DP_CANARY_ISSUE_FIELDS)
    _code(issue["kind"], f"{path}.kind")
    _text(issue["message"], f"{path}.message")
    for field in ("claim_id", "code", "skill_file"):
        _nullable_code(issue[field], f"{path}.{field}")
    if issue["line"] is not None:
        _integer(issue["line"], f"{path}.line", minimum=1)


def _validate_score(value: Any, path: str, *, compact: bool) -> None:
    raw = _exact_keys(value, DP_SCORE_FIELDS, path, required=DP_SCORE_FIELDS)
    gates = raw["gates"]
    if not isinstance(gates, dict):
        raise BenchmarkError(f"{path}.gates must be an object")
    if set(gates) != set(DP_GATE_NAMES):
        unknown = set(gates) - set(DP_GATE_NAMES)
        missing = set(DP_GATE_NAMES) - set(gates)
        details = []
        if unknown:
            details.append("unknown gate(s): " + ", ".join(sorted(map(str, unknown))))
        if missing:
            details.append("missing gate(s): " + ", ".join(sorted(missing)))
        raise BenchmarkError(f"{path}.gates has " + "; ".join(details))
    expected_gate_fields = DP_COMPACT_GATE_FIELDS if compact else DP_RAW_GATE_FIELDS
    for name in DP_GATE_NAMES:
        gate_path = f"{path}.gates.{name}"
        gate = _exact_keys(gates[name], expected_gate_fields, gate_path,
                           required=expected_gate_fields)
        _boolean(gate["passed"], f"{gate_path}.passed")
        _integer(gate["points"], f"{gate_path}.points", minimum=0)
        _code_list(gate["codes"], f"{gate_path}.codes")
        _boolean(gate["examined"], f"{gate_path}.examined")
        _boolean(gate["ungraded"], f"{gate_path}.ungraded")
        _boolean(gate["required"], f"{gate_path}.required")
        if not compact:
            _validate_diagnostics(gate["diagnostics"], f"{gate_path}.diagnostics")
    _enum(raw["state"], DP_SCORE_STATES, f"{path}.state")
    if raw["total"] is None:
        if raw["state"] != "invalid":
            raise BenchmarkError(f"{path}.total may be null only for invalid scores")
    else:
        _integer(raw["total"], f"{path}.total", minimum=0)
    _integer(raw["scoreable_max"], f"{path}.scoreable_max", minimum=0)
    _integer(raw["threshold"], f"{path}.threshold", minimum=1)
    flags = _exact_keys(raw["hard_gate_flags"], DP_HARD_GATE_FIELDS, f"{path}.hard_gate_flags",
                        required=DP_HARD_GATE_FIELDS)
    for name in DP_HARD_GATE_FIELDS:
        if flags[name] is not None:
            _boolean(flags[name], f"{path}.hard_gate_flags.{name}")
    waived = raw["waived_gates"]
    if not isinstance(waived, dict):
        raise BenchmarkError(f"{path}.waived_gates must be an object")
    unknown_waived = set(waived) - set(DP_GATE_NAMES)
    if unknown_waived:
        raise BenchmarkError(
            f"{path}.waived_gates has unknown gate(s): "
            + ", ".join(sorted(map(str, unknown_waived)))
        )
    for name, code_value in waived.items():
        _code(code_value, f"{path}.waived_gates.{name}")
    _code_list(raw["findings"], f"{path}.findings")


def _validate_efficiency(value: Any, path: str) -> None:
    expected = {"turns", "model_calls", "observed_turns", "observed_calls"}
    raw = _exact_keys(value, expected, path, required=expected)
    _number(raw["turns"], f"{path}.turns", minimum=0)
    if raw["model_calls"] is not None:
        _number(raw["model_calls"], f"{path}.model_calls", minimum=0)
    _integer(raw["observed_turns"], f"{path}.observed_turns", minimum=0)
    _integer(raw["observed_calls"], f"{path}.observed_calls", minimum=0)


def _validate_qualification(value: Any, path: str) -> None:
    expected = {"disposition", "replay_status", "operator_mode", "reasons"}
    raw = _exact_keys(value, expected, path, required=expected)
    _enum(raw["disposition"], DP_QUALIFICATION_DISPOSITIONS, f"{path}.disposition")
    _enum(raw["replay_status"], DP_REPLAY_STATUSES, f"{path}.replay_status")
    _enum(raw["operator_mode"], DP_OPERATOR_MODES, f"{path}.operator_mode")
    _code_list(raw["reasons"], f"{path}.reasons")


def _validate_interruption(value: Any, path: str, *, compact: bool) -> None:
    expected = {"failure_reason", "last_mcp_call"} if compact else {
        "failure_reason", "failure_detail", "last_mcp_call",
    }
    raw = _exact_keys(value, expected, path, required=expected)
    reason = raw["failure_reason"]
    if reason is not None:
        _enum(reason, DP_FAILURE_REASONS, f"{path}.failure_reason")
    if not compact:
        _nullable_text(raw["failure_detail"], f"{path}.failure_detail")
    _nullable_code(raw["last_mcp_call"], f"{path}.last_mcp_call")


def _validate_route_fidelity(value: Any, path: str, *, compact: bool) -> None:
    expected = {"status"} if compact else {"status", "reason"}
    raw = _exact_keys(value, expected, path, required=expected)
    _enum(raw["status"], DP_ROUTE_FIDELITY_STATUSES, f"{path}.status")
    if not compact:
        _text(raw["reason"], f"{path}.reason")


def _validate_replay_recording(value: Any, path: str) -> None:
    """Validate the report-safe replay envelope without interpreting payload data."""

    raw = _exact_keys(value, DP_REPLAY_FIELDS, path, required=DP_REPLAY_FIELDS)
    _integer(raw["format_version"], f"{path}.format_version", minimum=1)
    if raw["format_version"] != 1:
        raise BenchmarkError(f"{path}.format_version must be 1")
    turns = raw["turns"]
    if not isinstance(turns, list) or not turns:
        raise BenchmarkError(f"{path}.turns must be a non-empty array")
    for index, value in enumerate(turns):
        turn_path = f"{path}.turns[{index}]"
        turn = _exact_keys(value, DP_RECORDED_TURN_FIELDS, turn_path,
                           required=DP_RECORDED_TURN_FIELDS)
        message = _exact_keys(turn["operator_message"], DP_OPERATOR_MESSAGE_FIELDS,
                              f"{turn_path}.operator_message",
                              required=DP_OPERATOR_MESSAGE_FIELDS)
        if not isinstance(message["text"], str):
            raise BenchmarkError(f"{turn_path}.operator_message.text must be a string")
        attachments = message["attachments"]
        if not isinstance(attachments, list):
            raise BenchmarkError(f"{turn_path}.operator_message.attachments must be an array")
        for attachment_index, attachment_value in enumerate(attachments):
            attachment_path = f"{turn_path}.operator_message.attachments[{attachment_index}]"
            attachment = _exact_keys(attachment_value, DP_ATTACHMENT_FIELDS, attachment_path,
                                     required=DP_ATTACHMENT_FIELDS)
            _text(attachment["name"], f"{attachment_path}.name")
            _text(attachment["kind"], f"{attachment_path}.kind")
            _encoded_bytes(attachment["content"], f"{attachment_path}.content")
        _validate_turn_result(turn["result"], f"{turn_path}.result")

    manifest = raw["manifest"]
    if manifest is not None:
        _validate_manifest(manifest, f"{path}.manifest", compact=False)
    facts = raw["supervisor_facts"]
    if facts is not None:
        _validate_supervisor_facts(facts, f"{path}.supervisor_facts")
    metadata = _exact_keys(raw["metadata"], DP_REPLAY_METADATA_FIELDS, f"{path}.metadata",
                           required=DP_REPLAY_METADATA_FIELDS)
    if metadata["touched_file_contents_redacted"] is not True:
        raise BenchmarkError(f"{path}.metadata.touched_file_contents_redacted must be true")


def _validate_turn_result(value: Any, path: str) -> None:
    raw = _exact_keys(value, DP_TURN_RESULT_FIELDS, path, required=DP_TURN_RESULT_FIELDS)
    _encoded_bytes(raw["transcript_delta"], f"{path}.transcript_delta")
    _encoded_bytes(raw["agent_message"], f"{path}.agent_message")
    if raw["approval_artifact"] is not None:
        _encoded_bytes(raw["approval_artifact"], f"{path}.approval_artifact")
    for field in ("tool_calls", "tool_results", "files_touched"):
        if not isinstance(raw[field], list):
            raise BenchmarkError(f"{path}.{field} must be an array")
    for index, call_value in enumerate(raw["tool_calls"]):
        call_path = f"{path}.tool_calls[{index}]"
        call = _exact_keys(call_value, DP_TOOL_CALL_FIELDS, call_path,
                           required=DP_TOOL_CALL_FIELDS)
        _code(call["name"], f"{call_path}.name")
    for index, file_value in enumerate(raw["files_touched"]):
        file_path = f"{path}.files_touched[{index}]"
        touched = _exact_keys(file_value, DP_TOUCHED_FILE_FIELDS, file_path,
                              required=DP_TOUCHED_FILE_FIELDS)
        _encoded_path(touched["path"], f"{file_path}.path")
        if touched["content"] is not None:
            _encoded_bytes(touched["content"], f"{file_path}.content")
    for field in ("build_failed", "reported", "environment_wedged", "turn_timed_out"):
        _boolean(raw[field], f"{path}.{field}")
    _integer(raw["build_failure_count"], f"{path}.build_failure_count", minimum=0)
    _integer(raw["terminal_result_count"], f"{path}.terminal_result_count", minimum=0)
    for field in (
        "transcript_delta", "agent_message", "environment_detail", "failure_reason",
        "session_id", "terminal_result_subtype",
    ):
        _nullable_text(raw[field], f"{path}.{field}")
    _nullable_code(raw["last_mcp_call"], f"{path}.last_mcp_call")
    if raw["terminal_result_is_error"] is not None:
        _boolean(raw["terminal_result_is_error"], f"{path}.terminal_result_is_error")


def _validate_replay_verification(value: Any, path: str) -> None:
    raw = _exact_keys(value, {"status", "reason"}, path, required={"status", "reason"})
    _enum(raw["status"], DP_REPLAY_STATUSES, f"{path}.status")
    _text(raw["reason"], f"{path}.reason")


def _validate_repeatability(value: Any, path: str) -> None:
    raw = _exact_keys(value, DP_REPEATABILITY_FIELDS, path,
                      required={"tier", "required_epochs", "observed_epochs", "certified"})
    _enum(raw["tier"], {"deterministic", "mock-source", "demonstrated-once"}, f"{path}.tier")
    _integer(raw["required_epochs"], f"{path}.required_epochs", minimum=1)
    _integer(raw["observed_epochs"], f"{path}.observed_epochs", minimum=0)
    _boolean(raw["certified"], f"{path}.certified")
    if "rates" in raw:
        rates = raw["rates"]
        if not isinstance(rates, dict):
            raise BenchmarkError(f"{path}.rates must be an object")
        unknown = set(rates) - set(DP_GATE_NAMES)
        if unknown:
            raise BenchmarkError(f"{path}.rates has unknown gate(s): {', '.join(sorted(unknown))}")
        for gate, rate_value in rates.items():
            rate_path = f"{path}.rates.{gate}"
            rate = _exact_keys(rate_value, DP_RATE_FIELDS, rate_path, required=DP_RATE_FIELDS)
            _integer(rate["passed"], f"{rate_path}.passed", minimum=0)
            _integer(rate["examined"], f"{rate_path}.examined", minimum=0)
            _number(rate["rate"], f"{rate_path}.rate", minimum=0, maximum=1)
            _number(rate["wilson_lower_bound"], f"{rate_path}.wilson_lower_bound",
                    minimum=0, maximum=1)
    for field in ("excluded_invalid", "excluded_truncated"):
        if field in raw:
            _integer(raw[field], f"{path}.{field}", minimum=0)
    if "demonstrated_once" in raw:
        demonstrated = _exact_keys(raw["demonstrated_once"], DP_DEMONSTRATED_ONCE_FIELDS,
                                   f"{path}.demonstrated_once",
                                   required=DP_DEMONSTRATED_ONCE_FIELDS)
        _enum(demonstrated["state"], {"demonstrated-once"},
              f"{path}.demonstrated_once.state")
        gates = demonstrated["gates"]
        if not isinstance(gates, dict):
            raise BenchmarkError(f"{path}.demonstrated_once.gates must be an object")
        unknown = set(gates) - set(DP_GATE_NAMES)
        if unknown:
            raise BenchmarkError(
                f"{path}.demonstrated_once.gates has unknown gate(s): "
                + ", ".join(sorted(unknown))
            )
        for gate, passed in gates.items():
            _boolean(passed, f"{path}.demonstrated_once.gates.{gate}")


def _validate_supervisor_report(value: Any, path: str) -> None:
    raw = _exact_keys(value, DP_SUPERVISOR_REPORT_FIELDS, path,
                      required={"outcome", "stages"})
    _enum(raw["outcome"], {"pass", "warn", "fail", "skip"}, f"{path}.outcome")
    stages = raw["stages"]
    if not isinstance(stages, list) or not stages:
        raise BenchmarkError(f"{path}.stages must be a non-empty array")
    for index, stage_value in enumerate(stages):
        stage_path = f"{path}.stages[{index}]"
        stage = _exact_keys(stage_value, DP_SUPERVISOR_STAGE_FIELDS, stage_path,
                            required=DP_SUPERVISOR_STAGE_FIELDS)
        _code(stage["stage"], f"{stage_path}.stage")
        _enum(stage["status"], {"pass", "warn", "fail", "skip"}, f"{stage_path}.status")
        checks = stage["checks"]
        if not isinstance(checks, list):
            raise BenchmarkError(f"{stage_path}.checks must be an array")
        for check_index, check_value in enumerate(checks):
            check_path = f"{stage_path}.checks[{check_index}]"
            check = _exact_keys(check_value, DP_SUPERVISOR_CHECK_FIELDS, check_path,
                                required={"code", "detail", "status"})
            _code(check["code"], f"{check_path}.code")
            _text(check["detail"], f"{check_path}.detail")
            _enum(check["status"], {"pass", "warn", "fail", "skip"}, f"{check_path}.status")
            if "subject" in check:
                _nullable_text(check["subject"], f"{check_path}.subject")
    for field in ("duration_ms",):
        if field in raw:
            _number(raw[field], f"{path}.{field}", minimum=0)
    for field in ("workflow", "probe_id"):
        if field in raw:
            _code(raw[field], f"{path}.{field}")
    provenance = raw.get("provenance")
    if provenance is not None:
        provenance_path = f"{path}.provenance"
        provenance = _exact_keys(provenance, DP_SUPERVISOR_PROVENANCE_FIELDS, provenance_path,
                                 required=DP_SUPERVISOR_PROVENANCE_FIELDS)
        for field in DP_SUPERVISOR_PROVENANCE_FIELDS - {"package_paths", "packages"}:
            if field in {"self_check_sha256", "spec_compiler_sha256"}:
                _hash(provenance[field], f"{provenance_path}.{field}", allow_not_applicable=False)
            elif field == "supervisor_version":
                _version(provenance[field], f"{provenance_path}.{field}")
            else:
                _text(provenance[field], f"{provenance_path}.{field}")
        for field in ("package_paths", "packages"):
            values = provenance[field]
            if not isinstance(values, dict):
                raise BenchmarkError(f"{provenance_path}.{field} must be an object")
            for key, item in values.items():
                _text(key, f"{provenance_path}.{field} key")
                _text(item, f"{provenance_path}.{field}.{key}")


def _validate_canary(value: Any, path: str) -> None:
    raw = _exact_keys(value, DP_CANARY_FIELDS, path, required=DP_CANARY_FIELDS)
    _nullable_hash(raw["claims_hash"], f"{path}.claims_hash")
    _nullable_text(raw["package"], f"{path}.package")
    verdict = _exact_keys(raw["verdict"], DP_CANARY_VERDICT_FIELDS, f"{path}.verdict",
                          required=DP_CANARY_VERDICT_FIELDS)
    _enum(verdict["outcome"], {"clean", "drift", "blocked"}, f"{path}.verdict.outcome")
    _boolean(verdict["blocking"], f"{path}.verdict.blocking")
    _code_list(verdict["observed_codes"], f"{path}.verdict.observed_codes")
    for field in ("issues", "advisories"):
        issues = verdict[field]
        if not isinstance(issues, list):
            raise BenchmarkError(f"{path}.verdict.{field} must be an array")
        for index, issue_value in enumerate(issues):
            issue_path = f"{path}.verdict.{field}[{index}]"
            _validate_issue(issue_value, issue_path)
    probe = raw["probe"]
    if probe is not None:
        probe_path = f"{path}.probe"
        probe = _exact_keys(probe, DP_CANARY_PROBE_FIELDS, probe_path,
                            required=DP_CANARY_PROBE_FIELDS)
        _validate_supervisor_report(probe["report"], f"{probe_path}.report")
        _integer(probe["returncode"], f"{probe_path}.returncode")
        _string(probe["stderr"], f"{probe_path}.stderr")
        _nullable_hash(probe["supervisor_digest"], f"{probe_path}.supervisor_digest")
    build = raw["build"]
    if build is not None:
        build_path = f"{path}.build"
        build = _exact_keys(build, DP_CANARY_BUILD_FIELDS, build_path,
                            required=DP_CANARY_BUILD_FIELDS)
        _integer(build["returncode"], f"{build_path}.returncode")
        _string(build["stderr"], f"{build_path}.stderr")
        _string(build["stdout"], f"{build_path}.stdout")
        _nullable_hash(build["supervisor_digest"], f"{build_path}.supervisor_digest")
        if build["diagnostic"] is not None and not isinstance(build["diagnostic"], dict):
            raise BenchmarkError(f"{build_path}.diagnostic must be an object or null")


def _validate_run(value: Any, path: str, scenario_id: str, *, compact: bool) -> dict[str, Any]:
    expected = DP_COMPACT_RUN_FIELDS if compact else DP_RAW_RUN_FIELDS
    raw = _exact_keys(value, expected, path, required=expected)
    if raw["scenario_id"] != scenario_id:
        raise BenchmarkError(f"{path}.scenario_id does not match {scenario_id!r}")
    _integer(raw["epoch"], f"{path}.epoch", minimum=1)
    _enum(raw["terminal_state"], DP_TERMINAL_STATES, f"{path}.terminal_state")
    _code_list(raw["ungraded_criteria"], f"{path}.ungraded_criteria")
    _validate_score(raw["score"], f"{path}.score", compact=compact)
    _validate_efficiency(raw["efficiency"], f"{path}.efficiency")
    _validate_manifest(raw["manifest"], f"{path}.manifest", compact=compact)
    _validate_qualification(raw["qualification"], f"{path}.qualification")
    _validate_interruption(raw["interruption"], f"{path}.interruption", compact=compact)
    _validate_route_fidelity(raw["route_fidelity"], f"{path}.route_fidelity", compact=compact)
    if compact:
        if raw["skill_set"] != "dp-scenarios":
            raise BenchmarkError(f"{path}.skill_set must be 'dp-scenarios'")
        _enum(raw["result"], {"PASS", "FAIL", "ERROR"}, f"{path}.result")
    else:
        _enum(raw["stop_condition"], DP_TERMINAL_STATES, f"{path}.stop_condition")
        _validate_failure_modes(raw["failure_modes"], f"{path}.failure_modes")
        if raw["replay_recording"] is None:
            raise BenchmarkError(f"{path}.replay_recording must be an object")
        _validate_replay_recording(raw["replay_recording"], f"{path}.replay_recording")
        _nullable_hash(raw["bundle_digest"], f"{path}.bundle_digest")
        if raw["replay_verification"] is None:
            raise BenchmarkError(f"{path}.replay_verification must be an object")
        _validate_replay_verification(raw["replay_verification"], f"{path}.replay_verification")
    return raw


def _validate_dp_report(value: Any, *, compact: bool) -> dict[str, Any]:
    expected = DP_COMPACT_REPORT_FIELDS if compact else DP_RAW_REPORT_FIELDS
    raw = _exact_keys(value, expected, "dp-scenarios report", required=expected)
    _integer(raw["report_format_version"], "dp-scenarios report_format_version", minimum=1)
    if raw["report_format_version"] != DP_SCENARIO_REPORT_VERSION:
        raise BenchmarkError("dp-scenarios report_format_version must be 1")
    if not compact:
        if "efficiency_is_reported_only" in raw:
            if raw["efficiency_is_reported_only"] is not True:
                raise BenchmarkError("dp-scenarios efficiency_is_reported_only must be true")
        if "verdict" in raw:
            _text(raw["verdict"], "dp-scenarios report.verdict")
        if "max_workers" in raw:
            _integer(raw["max_workers"], "dp-scenarios report.max_workers", minimum=1)
        if "blocked_reason" in raw:
            if not isinstance(raw["blocked_reason"], list):
                raise BenchmarkError("dp-scenarios report.blocked_reason must be an array")
            for index, issue in enumerate(raw["blocked_reason"]):
                _validate_issue(issue, f"dp-scenarios report.blocked_reason[{index}]")
        if "clean_tier_means" in raw:
            _text(raw["clean_tier_means"], "dp-scenarios report.clean_tier_means")
        if "canary" in raw:
            _validate_canary(raw["canary"], "dp-scenarios report.canary")
    scenarios = raw["scenarios"]
    if not isinstance(scenarios, list):
        raise BenchmarkError("dp-scenarios report.scenarios must be an array")
    scenario_fields = DP_COMPACT_SCENARIO_FIELDS if compact else DP_RAW_SCENARIO_FIELDS
    for index, scenario_value in enumerate(scenarios):
        scenario_path = f"dp-scenarios report.scenarios[{index}]"
        scenario = _exact_keys(scenario_value, scenario_fields, scenario_path,
                               required=scenario_fields)
        scenario_id = _code(scenario["scenario_id"], f"{scenario_path}.scenario_id")
        runs = scenario["runs"]
        if not isinstance(runs, list):
            raise BenchmarkError(f"{scenario_path}.runs must be an array")
        for run_index, run in enumerate(runs):
            _validate_run(run, f"{scenario_path}.runs[{run_index}]", scenario_id, compact=compact)
        if not compact:
            _validate_repeatability(scenario["repeatability"], f"{scenario_path}.repeatability")
    return raw


def _is_compact_dp_report(report: dict[str, Any]) -> bool:
    scenarios = report.get("scenarios")
    if not isinstance(scenarios, list):
        return False
    return any(
        isinstance(run, dict) and "result" in run
        for scenario in scenarios if isinstance(scenario, dict)
        for run in (
            scenario.get("runs", [])
            if isinstance(scenario.get("runs"), list)
            else ()
        )
    )


def _numeric_or_missing(value: Any) -> Any:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else MISSING


def _final_dp_status(run: dict[str, Any], status: str) -> str:
    """Preserve a compacted ERROR while rejecting a contradictory stored result."""

    declared = run.get("result")
    if declared is None or declared == status:
        return status
    return "ERROR"


def _encoded_value_is_empty(value: Any) -> bool:
    """Return whether a report-safe text/bytes value contains zero bytes."""

    if isinstance(value, str):
        return value == ""
    if isinstance(value, dict) and set(value) == {"__bytes__"}:
        encoded = value.get("__bytes__")
        if isinstance(encoded, str):
            try:
                return base64.b64decode(encoded, validate=True) == b""
            except (ValueError, base64.binascii.Error):
                return False
    return False


def _replay_has_contradictory_completion(replay: Any) -> bool:
    """Reject a clean score when replay evidence contradicts completion."""

    if not isinstance(replay, dict):
        return False  # compact records intentionally omit the replay envelope
    turns = replay.get("turns")
    if not isinstance(turns, list) or not turns:
        return False  # the schema validator reports malformed replay evidence
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        result = turn.get("result")
        if not isinstance(result, dict):
            continue
        if result.get("environment_wedged") is True or result.get("turn_timed_out") is True:
            return True
        if (
            result.get("terminal_result_count") != 1
            or result.get("terminal_result_subtype") != "success"
            or result.get("terminal_result_is_error") is not False
            or result.get("failure_reason") is not None
        ):
            return True
    final_turn = turns[-1]
    if not isinstance(final_turn, dict) or not isinstance(final_turn.get("result"), dict):
        return False
    final = final_turn["result"]
    return _encoded_value_is_empty(final.get("agent_message"))


def _dp_status(run: dict[str, Any]) -> str:
    """Classify a dp-scenarios run without upgrading interrupted evidence."""

    score = _mapping(run.get("score"))
    state = score.get("state")
    terminal_state = run.get("terminal_state")
    interruption = run.get("interruption")
    gates = _mapping(score.get("gates"))
    failure_modes = run.get("failure_modes")
    interrupted = [terminal_state, run.get("stop_condition")]
    if isinstance(failure_modes, list):
        interrupted.extend(item for item in failure_modes if isinstance(item, str))

    if not isinstance(interruption, dict) or interruption.get("failure_reason") is not None:
        return _final_dp_status(run, "ERROR")
    hard_gate_flags = _mapping(score.get("hard_gate_flags"))
    if hard_gate_flags.get("sentinel") is True:
        return _final_dp_status(run, "ERROR")
    qualification = _mapping(run.get("qualification"))
    if qualification.get("disposition") == "INVALID":
        return _final_dp_status(run, "ERROR")
    if any(item in DP_INTERRUPTED_TERMINAL_STATES for item in interrupted if isinstance(item, str)):
        return _final_dp_status(run, "ERROR")
    if isinstance(failure_modes, list) and "turn_budget_exceeded" in failure_modes:
        return _final_dp_status(run, "ERROR")
    if terminal_state not in DP_CLEAN_TERMINAL_STATES:
        return _final_dp_status(run, "ERROR")
    if run.get("ungraded_criteria"):
        return _final_dp_status(run, "ERROR")
    if any(isinstance(gate, dict) and gate.get("ungraded") is True for gate in gates.values()):
        return _final_dp_status(run, "ERROR")
    if _replay_has_contradictory_completion(run.get("replay_recording")):
        return _final_dp_status(run, "ERROR")
    if not isinstance(state, str) or state in DP_ERROR_SCORE_STATES:
        return _final_dp_status(run, "ERROR")
    if state == "passed":
        return _final_dp_status(run, "PASS")
    if state == "failed":
        return _final_dp_status(run, "FAIL")
    return _final_dp_status(run, "ERROR")


def _dp_cell_rows(tag: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    compact = _is_compact_dp_report(report)
    _validate_dp_report(report, compact=compact)
    scenarios = report.get("scenarios")
    assert isinstance(scenarios, list)
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        assert isinstance(scenario, dict)
        scenario_id = scenario["scenario_id"]
        runs = scenario["runs"]
        assert isinstance(scenario_id, str) and isinstance(runs, list)
        for run in runs:
            assert isinstance(run, dict)
            score = run["score"]
            assert isinstance(score, dict)
            gates = score["gates"]
            assert isinstance(gates, dict)
            known_gates = [gates[name] for name in DP_GATE_NAMES]
            required_gates = [gate for gate in known_gates if gate.get("required") is True]
            passed = sum(1 for gate in required_gates if gate.get("passed") is True)
            efficiency = run["efficiency"]
            manifest = run["manifest"]
            assert isinstance(efficiency, dict) and isinstance(manifest, dict)
            rows.append({
                "tag": tag or MISSING,
                "skill_set": "dp-scenarios",
                "scenario": scenario_id,
                "status": _dp_status(run),
                "checks": f"{passed}/{len(required_gates)}" if required_gates else MISSING,
                "num_turns": _numeric_or_missing(
                    efficiency.get("observed_turns", efficiency.get("turns"))
                ),
                "tool_calls": _numeric_or_missing(
                    efficiency.get("observed_calls", efficiency.get("model_calls"))
                ),
                "output_tokens": MISSING,
                "cost_usd": MISSING,
                "agent_model": manifest["agent_model_id"],
            })
    return rows


def cell_rows(tag: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        raise BenchmarkError("report must be a JSON object")
    if is_dp_scenarios_report(report):
        return _dp_cell_rows(tag, report)
    return _legacy_cell_rows(tag, report)


_OPERATOR_PATH_RE = re.compile(r"/(?:Users|home)/[^/\s\"']+")


def redact_operator_paths(value: Any) -> Any:
    """Remove local home paths from compact evidence before it is committed."""
    if isinstance(value, str):
        return _OPERATOR_PATH_RE.sub("<operator-home>", value)
    if isinstance(value, dict):
        return {key: redact_operator_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_operator_paths(item) for item in value]
    return value


def _compact_legacy_report(report: dict[str, Any]) -> dict[str, Any]:
    """Strip legacy transcripts/final answers with the original behavior."""

    slim = {key: value for key, value in report.items() if key != "results"}
    slim["results"] = []
    for res in report.get("results", []):
        result = {key: value for key, value in res.items() if key != "transcript"}
        metrics = dict(result.get("metrics", {}) or {})
        metrics.pop("final_answer", None)
        result["metrics"] = metrics
        slim["results"].append(result)
    return redact_operator_paths(slim)


def _compact_dp_score(value: Any) -> dict[str, Any]:
    score = _validate_score(value, "dp-scenarios run.score", compact=False)
    # _validate_score is intentionally a validator only; copy the fixed
    # producer fields explicitly so no recursive filtering can hide drift.
    assert isinstance(value, dict)
    return {
        "gates": {
            name: {
                field: value["gates"][name][field]
                for field in DP_COMPACT_GATE_FIELDS
            }
            for name in DP_GATE_NAMES
        },
        "total": value["total"],
        "scoreable_max": value["scoreable_max"],
        "threshold": value["threshold"],
        "waived_gates": dict(value["waived_gates"]),
        "hard_gate_flags": dict(value["hard_gate_flags"]),
        "state": value["state"],
        "findings": list(value["findings"]),
    }


def _compact_dp_run(run: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    _validate_run(run, f"dp-scenarios scenario {scenario_id!r} run", scenario_id, compact=False)
    last_mcp_call = run["interruption"]["last_mcp_call"]
    if last_mcp_call is not None:
        last_mcp_call = _code(
            last_mcp_call.partition(":")[0],
            "dp-scenarios run.interruption.last_mcp_call",
        )
    result: dict[str, Any] = {
        "skill_set": "dp-scenarios",
        "scenario_id": scenario_id,
        "result": _dp_status(run),
        "epoch": run["epoch"],
        "terminal_state": run["terminal_state"],
        "ungraded_criteria": list(run["ungraded_criteria"]),
        "score": _compact_dp_score(run["score"]),
        "efficiency": {
            "turns": run["efficiency"]["turns"],
            "model_calls": run["efficiency"]["model_calls"],
            "observed_turns": run["efficiency"]["observed_turns"],
            "observed_calls": run["efficiency"]["observed_calls"],
        },
        "manifest": {
            field: run["manifest"][field]
            for field in DP_MANIFEST_FIELDS
        },
        "qualification": dict(run["qualification"]),
        "interruption": {
            "failure_reason": run["interruption"]["failure_reason"],
            "last_mcp_call": last_mcp_call,
        },
        "route_fidelity": {"status": run["route_fidelity"]["status"]},
    }
    return result


def _compact_dp_report(report: dict[str, Any]) -> dict[str, Any]:
    _validate_dp_report(report, compact=False)
    scenarios = report["scenarios"]
    assert isinstance(scenarios, list)
    compact_scenarios = []
    for scenario in scenarios:
        assert isinstance(scenario, dict)
        scenario_id = scenario["scenario_id"]
        runs = scenario["runs"]
        assert isinstance(scenario_id, str) and isinstance(runs, list)
        compact_scenarios.append({
            "scenario_id": scenario_id,
            "runs": [_compact_dp_run(run, scenario_id) for run in runs],
        })
    return {
        "report_format_version": DP_SCENARIO_REPORT_VERSION,
        "scenarios": compact_scenarios,
    }


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    """Keep only reviewed evidence fields for each supported report format."""

    if is_dp_scenarios_report(report):
        return _compact_dp_report(report)
    return _compact_legacy_report(report)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:MAX_SLUG_LENGTH] or "benchmark"


def status_for(rows: list[dict[str, Any]]) -> str:
    statuses = {row["status"] for row in rows}
    return next(iter(statuses)) if len(statuses) == 1 else "MIXED"


def table_for(rows: list[dict[str, Any]]) -> str:
    header = ("| run | skill-set | scenario | verdict | checks | turns | tool_calls | "
              "out_tokens | cost_usd | agent |\n"
              "|---|---|---|---|---|---|---|---|---|---|")
    rendered = []
    for row in rows:
        rendered.append("| " + " | ".join(escape_cell(row[key]) for key in (
            "tag", "skill_set", "scenario", "status", "checks", "num_turns",
            "tool_calls", "output_tokens", "cost_usd", "agent_model",
        )) + " |")
    return header + "\n" + "\n".join(rendered)


def entry_text(frontmatter: dict[str, Any], rows: list[dict[str, Any]], notes: str) -> str:
    record = frontmatter["record"]
    title = re.sub(r"[\r\n\u0085\u2028\u2029]+", " ", str(frontmatter["label"]))
    rendered_notes = re.sub(r"\r\n?|[\u0085\u2028\u2029]", "\n", notes.strip())
    return (
        write_frontmatter(frontmatter)
        + f"# Benchmark — {title}\n\n"
        + "## Results\n\n"
        + table_for(rows)
        + "\n\n## Notes\n\n"
        + (rendered_notes or "Measured benchmark evidence.")
        + "\n\n## Evidence\n\n"
        + f"Compact report: [`{record}`]({record})\n"
    )


def read_plugin_version() -> str:
    try:
        value = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8")).get("version")
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read plugin version: {exc}") from exc
    return validate_semver(value, "plugin manifest version")


def parse_entry(path: Path) -> Entry:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BenchmarkError(f"cannot read entry {path}: {exc}") from exc
    frontmatter, body = parse_frontmatter(text)
    return Entry(path, frontmatter, body)


def record_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    reports = record.get("reports")
    if not isinstance(reports, dict) or not reports:
        raise BenchmarkError("measured record must contain non-empty reports")
    report_tags = record.get("report_tags")
    if not isinstance(report_tags, dict) or set(report_tags) != set(reports):
        raise BenchmarkError("measured record must map every report to its display tag")
    if any(
        not isinstance(key, str) or not isinstance(report_tags[key], str)
        or not isinstance(report, dict)
        for key, report in reports.items()
    ):
        raise BenchmarkError("measured record reports must map strings to objects")
    validate_dp_comparability(reports, report_tags)
    rows: list[dict[str, Any]] = []
    for tag, report in reports.items():
        display_tag = report_tags[tag]
        rows.extend(cell_rows(display_tag, report))
    if not rows:
        raise BenchmarkError("measured record reports contain no result cells")
    return rows


def _comparison_side(tag: str) -> str | None:
    match = re.match(r"^(before|after)(?:-|$)", tag)
    return match.group(1) if match else None


def _dp_target_runs(report: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if not is_dp_scenarios_report(report):
        return []
    scenarios = report.get("scenarios")
    if not isinstance(scenarios, list):
        raise BenchmarkError("dp-scenarios report scenarios must be a list")
    result: list[tuple[str, dict[str, Any]]] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise BenchmarkError("dp-scenarios scenario must be an object")
        scenario_id = scenario.get("scenario_id")
        runs = scenario.get("runs")
        if not isinstance(scenario_id, str) or not CODE_RE.fullmatch(scenario_id):
            raise BenchmarkError("dp-scenarios scenario_id must be a non-empty code")
        if not isinstance(runs, list):
            raise BenchmarkError(f"dp-scenarios scenario {scenario_id!r} runs must be a list")
        if scenario_id not in DP_PAIRED_SCENARIOS:
            continue
        for run in runs:
            if not isinstance(run, dict):
                raise BenchmarkError(f"dp-scenarios scenario {scenario_id!r} run must be an object")
            result.append((scenario_id, run))
    return result


def _dp_pair_pins(scenario_id: str, run: dict[str, Any]) -> tuple[tuple[str, int], dict[str, Any]]:
    epoch = run.get("epoch")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        raise BenchmarkError(f"dp-scenarios {scenario_id!r} run is missing a positive integer epoch")
    if run.get("scenario_id", scenario_id) != scenario_id:
        raise BenchmarkError(f"dp-scenarios run scenario_id does not match {scenario_id!r}")
    manifest = run.get("manifest")
    if not isinstance(manifest, dict):
        raise BenchmarkError(f"dp-scenarios {scenario_id!r} epoch {epoch} is missing manifest pins")
    required = (*DP_COMPARABILITY_FIELDS, *DP_REQUIRED_IDENTITY_FIELDS)
    missing = [field for field in required if field not in manifest or manifest[field] is None]
    if missing:
        raise BenchmarkError(
            f"dp-scenarios {scenario_id!r} epoch {epoch} is missing pin(s): "
            + ", ".join(missing)
        )
    if manifest["scenario_id"] != scenario_id:
        raise BenchmarkError(
            f"dp-scenarios {scenario_id!r} epoch {epoch} manifest scenario_id does not match"
        )
    return (scenario_id, epoch), {field: manifest[field] for field in DP_COMPARABILITY_FIELDS}


def validate_dp_comparability(reports: dict[str, Any], report_tags: dict[str, str]) -> None:
    """Require complete like-for-like before/after pairs for B1, B2, and B5."""

    for report in reports.values():
        if is_dp_scenarios_report(report):
            _validate_dp_report(report, compact=_is_compact_dp_report(report))
    target_by_report = {
        key: _dp_target_runs(report)
        for key, report in reports.items()
        if isinstance(report, dict)
    }
    if not any(target_by_report.values()):
        return
    if any(not is_dp_scenarios_report(report) for report in reports.values()):
        raise BenchmarkError("cannot mix dp-scenarios and evals/run.py reports in a B1/B2/B5 comparison")
    display_tags = list(report_tags.values())
    if any(not isinstance(tag, str) for tag in display_tags):
        raise BenchmarkError("dp-scenarios report tags must be strings")
    explicit_tags = [tag for tag in display_tags if tag]
    if len(set(explicit_tags)) != len(explicit_tags):
        raise BenchmarkError("duplicate dp-scenarios report tag")

    arms: dict[str, dict[tuple[str, int], dict[str, Any]]] = {"before": {}, "after": {}}
    versions: dict[str, set[str]] = {"before": set(), "after": set()}
    for key, target_runs in target_by_report.items():
        if not target_runs:
            continue
        tag = report_tags.get(key, "")
        side = _comparison_side(tag)
        if side is None:
            raise BenchmarkError(
                "B1/B2/B5 dp-scenarios reports require explicit before-* and after-* tags"
            )
        for scenario_id, run in target_runs:
            pair_key, pins = _dp_pair_pins(scenario_id, run)
            if pair_key in arms[side]:
                raise BenchmarkError(
                    f"duplicate dp-scenarios {side} run for {scenario_id!r} epoch {pair_key[1]}"
                )
            arms[side][pair_key] = pins
            manifest = run["manifest"]
            versions[side].add(json.dumps(manifest["skill_pack_version"], sort_keys=True))

    for side, values in versions.items():
        if len(values) > 1:
            raise BenchmarkError(f"dp-scenarios {side} arm has mixed skill_pack_version pins")
    before_keys, after_keys = set(arms["before"]), set(arms["after"])
    if before_keys != after_keys:
        missing_after = sorted(before_keys - after_keys)
        missing_before = sorted(after_keys - before_keys)
        detail = []
        if missing_after:
            detail.append(f"missing after pairs {missing_after!r}")
        if missing_before:
            detail.append(f"missing before pairs {missing_before!r}")
        raise BenchmarkError("dp-scenarios comparison has " + "; ".join(detail))
    for pair_key in sorted(before_keys):
        before, after = arms["before"][pair_key], arms["after"][pair_key]
        mismatched = [field for field in DP_COMPARABILITY_FIELDS if before[field] != after[field]]
        if mismatched:
            scenario_id, epoch = pair_key
            raise BenchmarkError(
                f"dp-scenarios pair {scenario_id!r} epoch {epoch} has mismatched pin(s): "
                + ", ".join(mismatched)
            )


def section(body: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}[ \t]*$\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    return match.group(1).strip() if match else ""


def validate_entry(entry: Entry, seen_ids: set[str] | None = None,
                   record_override: dict[str, Any] | None = None) -> Entry:
    fm = entry.frontmatter
    if set(fm) != set(FRONTMATTER_KEYS):
        raise BenchmarkError(f"{entry.path}: malformed frontmatter fields")
    identifier = validate_id(fm["id"])
    if entry.path.stem != identifier:
        raise BenchmarkError(f"{entry.path}: filename stem must equal id")
    if seen_ids is not None:
        if identifier in seen_ids:
            raise BenchmarkError(f"duplicate benchmark id {identifier!r}")
        seen_ids.add(identifier)
    validate_date(fm["date"])
    if not isinstance(fm["label"], str) or not fm["label"].strip():
        raise BenchmarkError(f"{entry.path}: label is required")
    try:
        validate_semver(fm["plugin_version"])
    except BenchmarkError as exc:
        raise BenchmarkError(f"{entry.path}: {exc}") from exc
    if not isinstance(fm["scenarios"], list) or any(not isinstance(v, str) or not v for v in fm["scenarios"]):
        raise BenchmarkError(f"{entry.path}: scenarios must be a list of names")
    if len(set(fm["scenarios"])) != len(fm["scenarios"]):
        raise BenchmarkError(f"{entry.path}: scenarios contains duplicates")
    if not entry.body.startswith("# Benchmark — ") or not section(entry.body, "Notes") or not section(entry.body, "Evidence"):
        raise BenchmarkError(f"{entry.path}: body must contain title, Notes, and Evidence")

    if fm["status"] == "NO_EVAL":
        if fm["scenarios"] or fm["record"] is not None:
            raise BenchmarkError(f"{entry.path}: NO_EVAL requires scenarios: [] and record: null")
        notes = section(entry.body, "Notes").lower()
        evidence = section(entry.body, "Evidence")
        if not ("no" in notes and any(term in notes for term in ("arm", "scenario", "eval"))):
            raise BenchmarkError(f"{entry.path}: NO_EVAL notes must explain why there is no eval arm")
        test_paths = re.findall(r"(?<![\w.-])((?:[A-Za-z0-9_.-]+/)*test_[A-Za-z0-9_.-]+\.py)(?![\w.-])", evidence)
        if not test_paths:
            raise BenchmarkError(f"{entry.path}: NO_EVAL evidence must name a carrying test file path")
        for test_path in test_paths:
            relative = Path(test_path)
            if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
                raise BenchmarkError(f"{entry.path}: NO_EVAL test path must stay inside the repository")
            candidate = (REPO_ROOT / relative).resolve()
            try:
                candidate.relative_to(REPO_ROOT.resolve())
            except ValueError as exc:
                raise BenchmarkError(f"{entry.path}: NO_EVAL test path escapes the repository") from exc
            if not candidate.is_file():
                raise BenchmarkError(f"{entry.path}: NO_EVAL evidence names missing test file {test_path!r}")
        return entry

    if fm["status"] not in MEASURED_STATUSES:
        raise BenchmarkError(f"{entry.path}: invalid measured status {fm['status']!r}")
    expected_record = f"../records/{identifier}.json"
    if fm["record"] != expected_record:
        raise BenchmarkError(f"{entry.path}: record must be {expected_record!r}")
    record_path = entry.path.parent / fm["record"]
    if record_override is None:
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkError(f"{entry.path}: bad or missing record link: {exc}") from exc
    else:
        record = record_override
    if not isinstance(record, dict):
        raise BenchmarkError(f"{entry.path}: record must be a JSON object")
    for key in ("id", "date", "label", "plugin_version"):
        if record.get(key) != fm[key]:
            raise BenchmarkError(f"{entry.path}: record {key!r} does not match entry")
    if not isinstance(record.get("notes"), str):
        raise BenchmarkError(f"{entry.path}: measured record notes must be a string")
    rows = record_rows(record)
    scenarios = sorted({str(row["scenario"]) for row in rows})
    if fm["scenarios"] != scenarios:
        raise BenchmarkError(f"{entry.path}: scenarios do not match record results")
    if fm["status"] != status_for(rows):
        raise BenchmarkError(f"{entry.path}: status does not match record results")
    expected_text = entry_text(fm, rows, record["notes"])
    _, expected_body = parse_frontmatter(expected_text)
    if entry.body != expected_body:
        raise BenchmarkError(
            f"{entry.path}: measured Markdown body must be the canonical rendering of its JSON record"
        )
    return entry


def load_entries(extra: Entry | None = None, extra_record: dict[str, Any] | None = None,
                 skip_path: Path | None = None) -> list[Entry]:
    entries: list[Entry] = []
    seen_ids: set[str] = set()
    if ENTRIES_DIR.exists():
        for path in sorted(ENTRIES_DIR.glob("*.md")):
            if skip_path is not None and path == skip_path:
                continue
            entries.append(validate_entry(parse_entry(path), seen_ids))
    if extra is not None:
        entries.append(validate_entry(extra, seen_ids, extra_record))
    return entries


def index_text(entries: list[Entry]) -> str:
    """Build a deterministic, newest-first index of post-migration entries."""
    ordered = sorted(entries, key=lambda item: (item.frontmatter["date"], item.frontmatter["id"]), reverse=True)
    lines = [
        "# Benchmark entries",
        "",
        "Generated by `evals/benchmark_record.py --rebuild-index`; do not edit manually.",
        "New measured evidence lives in `entries/` with compact JSON reports in `records/`.",
        "",
        "The pre-migration append-only history is frozen in [legacy `ledger.md`](ledger.md). "
        "Its existing records remain historical evidence and are not indexed here.",
        "",
        "| Date | Label | Status | Scenarios | Entry |",
        "|---|---|---|---|---|",
    ]
    for entry in ordered:
        fm = entry.frontmatter
        scenarios = ", ".join(escape_cell(item) for item in fm["scenarios"]) or MISSING
        lines.append(
            f"| {escape_cell(fm['date'])} | {escape_cell(fm['label'])} | {fm['status']} | "
            f"{scenarios} | [`{fm['id']}`](entries/{fm['id']}.md) |"
        )
    return "\n".join(lines) + "\n"


def identical_or_fail(targets: dict[Path, str]) -> None:
    """Collision preflight for immutable identity artifacts.

    The index is intentionally regenerated whenever the entry set changes; an
    entry or compact record is immutable once its ID has been claimed.
    """
    for path, content in targets.items():
        if path == INDEX:
            continue
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise BenchmarkError(f"refusing to overwrite existing benchmark artifact {path}")


def atomic_publish(staged: Path, path: Path, content: str) -> bool:
    """Publish a fully fsynced staged artifact as whole-or-absent final bytes.

    ``link`` atomically creates the final directory entry without replacing an
    existing one.  The final path therefore never points at a file still being
    written: SIGKILL can leave the staged file or no final file, but not a
    truncated final artifact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = content.encode("utf-8")
    try:
        if staged.read_bytes() != payload:
            raise BenchmarkError(f"staged benchmark artifact differs from intended content: {staged}")
        os.link(staged, path)
    except FileExistsError:
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise BenchmarkError(f"cannot inspect concurrent benchmark artifact {path}: {exc}") from exc
        if existing != payload:
            raise BenchmarkError(f"refusing to overwrite existing benchmark artifact {path}")
        return False
    except OSError as exc:
        raise BenchmarkError(f"cannot publish benchmark artifact {path}: {exc}") from exc
    return True


def atomic_replace(path: Path, content: str) -> None:
    """Atomically publish a regenerated index without exposing a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as handle:
            temp_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name:
            try:
                Path(temp_name).unlink()
            except OSError:
                pass
        raise BenchmarkError(f"cannot replace benchmark index {path}: {exc}") from exc


@contextlib.contextmanager
def index_lock():
    """Serialize publication with a POSIX lock released when a process dies.

    Unlike an ``O_EXCL`` lockfile, ``flock`` is released by the kernel on a
    catchable interrupt, SIGTERM, or SIGKILL.  A small persistent publication
    marker handles the separate problem of a process dying between two final
    artifact creations.
    """
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = BENCH_DIR / ".benchmark-index.lock"
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        recover_pending_publication()
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def publication_marker() -> Path:
    return BENCH_DIR / ".benchmark-publication.json"


def staging_dir() -> Path:
    return BENCH_DIR / ".benchmark-staging"


def sha256(content: str | bytes) -> str:
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


def cleanup_staged(identifier: str) -> None:
    for suffix in ("entry.md", "record.json"):
        try:
            (staging_dir() / f"{identifier}.{suffix}").unlink()
        except FileNotFoundError:
            pass


def cleanup_orphan_staging() -> None:
    stage = staging_dir()
    if not stage.exists():
        return
    for path in stage.iterdir():
        if path.is_file() and (path.name.endswith(".entry.md") or path.name.endswith(".record.json")):
            try:
                path.unlink()
            except OSError as exc:
                raise BenchmarkError(f"cannot clear stale benchmark staging artifact {path}: {exc}") from exc


def load_pending_marker() -> dict[str, Any] | None:
    marker = publication_marker()
    if not marker.exists():
        return None
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot recover malformed benchmark publication marker: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != "benchmark-publication-v2":
        raise BenchmarkError("cannot recover malformed benchmark publication marker")
    identifier = value.get("id")
    validate_id(identifier)
    artifacts = value.get("artifacts")
    expected = [f"records/{identifier}.json", f"entries/{identifier}.md"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise BenchmarkError("cannot recover malformed benchmark publication marker artifacts")
    paths = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise BenchmarkError("cannot recover malformed benchmark publication marker artifact")
        path, digest = artifact.get("path"), artifact.get("sha256")
        if path not in expected or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise BenchmarkError("cannot recover malformed benchmark publication marker artifact")
        paths.append(path)
    if sorted(paths) != sorted(expected):
        raise BenchmarkError("cannot recover malformed benchmark publication marker artifact paths")
    return value


def recover_pending_publication() -> None:
    """Finish or roll back the last interrupted two-artifact publication.

    SIGKILL cannot run Python cleanup.  The kernel releases ``flock`` and the
    next recorder invocation reaches this marker while holding that lock: a
    complete byte-matching pair is retained, while a partial pair is removed.
    """
    marker = load_pending_marker()
    if marker is None:
        # A SIGKILL before marker publication leaves only private staging files.
        cleanup_orphan_staging()
        return
    identifier = marker["id"]
    expected = {item["path"]: item["sha256"] for item in marker["artifacts"]}
    matching: list[Path] = []
    corrupt: list[Path] = []
    missing: list[Path] = []
    for relative, digest in expected.items():
        path = BENCH_DIR / relative
        if not path.exists():
            missing.append(path)
            continue
        try:
            actual = sha256(path.read_bytes())
        except OSError as exc:
            raise BenchmarkError(f"cannot recover benchmark artifact {path}: {exc}") from exc
        if actual != digest:
            # The v2 marker is transaction ownership.  This is a partial or
            # corrupt artifact from a killed publication, not user evidence.
            corrupt.append(path)
            continue
        matching.append(path)
    if missing or corrupt:
        for path in (*matching, *corrupt):
            try:
                path.unlink()
            except OSError as exc:
                raise BenchmarkError(f"cannot roll back interrupted benchmark artifact {path}: {exc}") from exc
    try:
        publication_marker().unlink()
    except OSError as exc:
        raise BenchmarkError(f"cannot clear recovered benchmark publication marker: {exc}") from exc
    cleanup_staged(identifier)


def publish_pair(identifier: str, record_path: Path, record_text: str,
                 entry_path: Path, entry_content: str) -> None:
    """Stage and publish one immutable JSON/Markdown pair under ``index_lock``."""
    stage = staging_dir()
    stage.mkdir(parents=True, exist_ok=True)
    stage_record = stage / f"{identifier}.record.json"
    stage_entry = stage / f"{identifier}.entry.md"
    atomic_replace(stage_record, record_text)
    atomic_replace(stage_entry, entry_content)
    marker = {
        "schema": "benchmark-publication-v2",
        "id": identifier,
        "artifacts": [
            {"path": f"records/{identifier}.json", "sha256": sha256(record_text)},
            {"path": f"entries/{identifier}.md", "sha256": sha256(entry_content)},
        ],
    }
    atomic_replace(publication_marker(), json.dumps(marker, sort_keys=True) + "\n")
    try:
        atomic_publish(stage_record, record_path, record_text)
        atomic_publish(stage_entry, entry_path, entry_content)
    except BaseException:
        # Includes KeyboardInterrupt/SystemExit.  SIGKILL is recovered by the
        # persistent marker on the next flock holder.
        recover_pending_publication()
        raise
    try:
        publication_marker().unlink()
    except OSError as exc:
        raise BenchmarkError(f"cannot finalize benchmark publication marker: {exc}") from exc
    cleanup_staged(identifier)


def measured(args: argparse.Namespace) -> int:
    date = validate_date(args.date)
    identifier = validate_id(args.identifier) if args.identifier else f"{date}-{slugify(args.label)}"
    validate_id(identifier)
    plugin_version = read_plugin_version()
    rows: list[dict[str, Any]] = []
    source_reports: dict[str, Any] = {}
    reports: dict[str, Any] = {}
    report_tags: dict[str, str] = {}
    for spec in args.reports:
        tag, path = parse_report_arg(spec)
        key = tag or path.name
        if key in reports:
            raise BenchmarkError(f"duplicate report tag {key!r}")
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkError(f"cannot read report {path}: {exc}") from exc
        if not isinstance(report, dict):
            raise BenchmarkError(f"report {path} is not a JSON object")
        rows.extend(cell_rows(tag, report))
        source_reports[key] = report
        reports[key] = compact_report(report)
        report_tags[key] = tag
    if not rows:
        raise BenchmarkError("reports contained no result cells")
    validate_dp_comparability(source_reports, report_tags)
    scenarios = sorted({str(row["scenario"]) for row in rows})
    frontmatter = {
        "id": identifier, "date": date, "label": args.label,
        "plugin_version": plugin_version, "status": status_for(rows),
        "scenarios": scenarios, "record": f"../records/{identifier}.json",
    }
    record = {"id": identifier, "date": date, "label": args.label, "notes": args.notes,
              "plugin_version": plugin_version, "report_tags": report_tags, "reports": reports}
    entry_path = ENTRIES_DIR / f"{identifier}.md"
    rendered_entry = entry_text(frontmatter, rows, args.notes)
    _, body = parse_frontmatter(rendered_entry)
    entry = Entry(entry_path, frontmatter, body)
    validate_entry(entry, record_override=record)
    targets = {
        RECORDS_DIR / f"{identifier}.json": json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        entry_path: rendered_entry,
    }
    identical_or_fail(targets)
    with index_lock():
        # Re-check inside the crash-released lock.  publish_pair records enough
        # state to recover a SIGKILL after either immutable final-path create.
        identical_or_fail(targets)
        publish_pair(identifier, RECORDS_DIR / f"{identifier}.json", targets[RECORDS_DIR / f"{identifier}.json"],
                     entry_path, targets[entry_path])
        existing = load_entries()
        atomic_replace(INDEX, index_text(existing))
    print(f"wrote entry to {entry_path.relative_to(REPO_ROOT)}")
    print(f"wrote record to {(RECORDS_DIR / f'{identifier}.json').relative_to(REPO_ROOT)}")
    print(f"rebuilt index at {INDEX.relative_to(REPO_ROOT)}")
    return 0


def rebuild(check: bool) -> int:
    if check:
        # Checking may need to recover a SIGKILL marker first, so it takes the
        # same crash-released lock even though it never rewrites the index.
        with index_lock():
            entries = load_entries()
            expected = index_text(entries)
            actual = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        if actual != expected:
            print("benchmark index is missing or stale; run --rebuild-index", file=sys.stderr)
            return 1
        print("benchmark entries and index are valid")
        return 0
    with index_lock():
        entries = load_entries()
        expected = index_text(entries)
        actual = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        if actual != expected:
            atomic_replace(INDEX, expected)
    print(f"rebuilt index at {INDEX.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--rebuild-index", action="store_true", help="Validate entries and rewrite the generated index.")
    modes.add_argument("--check", action="store_true", help="Validate entries and fail when the generated index drifts.")
    parser.add_argument("--label", help="What changed, e.g. 'nxd-setup-cli: device-flow branch'.")
    parser.add_argument("--report", action="append", dest="reports", metavar="[TAG=]PATH",
                        help="evals/run.py or dp-scenarios report JSON; repeatable.")
    parser.add_argument("--notes", default="", help="One or two sentences of context for the entry.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Entry date, YYYY-MM-DD (default: today).")
    parser.add_argument("--id", dest="identifier", help="Optional lowercase-slug identity; defaults to date plus label slug.")
    args = parser.parse_args(argv)
    try:
        if args.rebuild_index:
            return rebuild(check=False)
        if args.check:
            return rebuild(check=True)
        if not args.label or not args.reports:
            parser.error("measured records require --label and at least one --report")
        return measured(args)
    except BenchmarkError as exc:
        print(f"benchmark record error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

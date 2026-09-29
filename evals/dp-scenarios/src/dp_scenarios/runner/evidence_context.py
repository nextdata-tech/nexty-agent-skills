"""Bounded, read-only supervisor evidence for scenario follow-up graders.

Only the seven runner-owned history JSON files and their already sanitized
capture snapshots are read. The view never visits the Desktop state directory.
Release, run, definition, and capture identity is checked when a grader asks
for a linked release, so an unrelated or newest capture cannot fill a gap.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from .supervisor_history import (
    CAPTURE_FILE_LIMIT,
    CAPTURE_TOTAL_LIMIT,
    CAPTURES_SCHEMA,
    DEFINITION_EXPORT_SCHEMA,
    PUBLICATION_SCHEMA,
    QUERY_HISTORY_LIMIT,
    QUERY_HISTORY_SCHEMA,
    RUN_FAILURES_SCHEMA,
    RUN_RECORDS_SCHEMA,
    TOOL_CALLS_SCHEMA,
)


_HISTORY_FILES = {
    "publication-history": (PUBLICATION_SCHEMA, "releases"),
    "run-records": (RUN_RECORDS_SCHEMA, "runs"),
    "run-failures": (RUN_FAILURES_SCHEMA, "failures"),
    "tool-calls": (TOOL_CALLS_SCHEMA, "calls"),
    "query-history": (QUERY_HISTORY_SCHEMA, "queries"),
    "supervisor-captures": (CAPTURES_SCHEMA, "captures"),
    "definition-export": (DEFINITION_EXPORT_SCHEMA, "definitions"),
}
_MAX_HISTORY_BYTES = 4 * 1024 * 1024
_MAX_HISTORY_ROWS = 4096
_SHA256_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


class HistoryEvidenceError(ValueError):
    """A runner-owned identity, path, or copied byte cannot be trusted."""


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _one(rows: tuple[Mapping[str, object], ...], field: str, value: object) -> Mapping[str, object]:
    matches = [row for row in rows if row.get(field) == value]
    if len(matches) != 1:
        raise HistoryEvidenceError(f"expected one {field} match")
    return matches[0]


def _safe_snapshot_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise HistoryEvidenceError("invalid capture file path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HistoryEvidenceError("invalid capture file path")
    return path


@dataclass(frozen=True, slots=True)
class LinkedCapture:
    record: Mapping[str, object]
    files: Mapping[str, bytes]

    def json_file(self, path: str) -> object | None:
        """Decode one inventoried, hash-checked capture file if it is JSON."""

        content = self.files.get(path)
        if content is None:
            return None
        try:
            return json.loads(content)
        except (UnicodeError, json.JSONDecodeError):
            return None


@dataclass(frozen=True, slots=True)
class LinkedRelease:
    release: Mapping[str, object]
    run: Mapping[str, object]
    definition: Mapping[str, object]
    capture: LinkedCapture | None


@dataclass(frozen=True, slots=True)
class SupervisorHistoryView:
    """An explicit evidence boundary; ``status`` is ready, missing, or invalid."""

    artifact_root: Path
    documents: Mapping[str, Mapping[str, object]]
    status: str
    issue: str | None = None

    def rows(self, name: str) -> tuple[Mapping[str, object], ...]:
        if name not in _HISTORY_FILES or self.status != "ready":
            return ()
        member = _HISTORY_FILES[name][1]
        value = self.documents[name][member]
        assert isinstance(value, tuple)
        return value

    def linked_release(self, release: Mapping[str, object]) -> LinkedRelease:
        """Join one exported release to its exact run, definition, and capture."""

        if self.status != "ready":
            raise HistoryEvidenceError("supervisor history is incomplete")
        run_id = release.get("run_id")
        workflow_id = release.get("workflow_id")
        definition_id = release.get("definition_id")
        if not all(isinstance(value, str) and value for value in (run_id, workflow_id, definition_id)):
            raise HistoryEvidenceError("release identity is incomplete")
        actual_release = _one(self.rows("publication-history"), "run_id", run_id)
        if actual_release != release:
            raise HistoryEvidenceError("release is not the runner-owned record")
        run = _one(self.rows("run-records"), "run_id", run_id)
        for field in ("workflow_id", "definition_id", "artifact_id", "publish_sequence", "admission_id"):
            left, right = release.get(field), run.get(field)
            if left is not None and right is not None and left != right:
                raise HistoryEvidenceError(f"release/run {field} differs")
        if run.get("workflow_id") != workflow_id or run.get("definition_id") != definition_id:
            raise HistoryEvidenceError("release/run identity differs")
        definition = _one(self.rows("definition-export"), "definition_id", definition_id)
        for field, identity in (("run_ids", run_id), ("workflow_ids", workflow_id)):
            associations = definition.get(field)
            if not isinstance(associations, tuple) or identity not in associations:
                raise HistoryEvidenceError(f"definition {field} association differs")

        capture: LinkedCapture | None = None
        capture_sha = run.get("capture_sha256")
        if capture_sha is not None:
            match = _SHA256_RE.fullmatch(capture_sha) if isinstance(capture_sha, str) else None
            if match is None:
                raise HistoryEvidenceError("invalid run capture digest")
            record = _one(self.rows("supervisor-captures"), "capture_sha256", capture_sha)
            for field, identity in (("run_ids", run_id), ("workflow_ids", workflow_id)):
                associations = record.get(field)
                if not isinstance(associations, tuple) or identity not in associations:
                    raise HistoryEvidenceError(f"capture {field} association differs")
            capture_id = run.get("capture_id")
            if capture_id is not None and record.get("capture_id") not in (None, capture_id):
                raise HistoryEvidenceError("capture id differs")
            capture = LinkedCapture(record, self._capture_files(match.group(1), record))
        return LinkedRelease(actual_release, run, definition, capture)

    def _capture_files(self, digest: str, record: Mapping[str, object]) -> Mapping[str, bytes]:
        inventory = record.get("files")
        if not isinstance(inventory, tuple):
            raise HistoryEvidenceError("capture file inventory is absent")
        root = self.artifact_root.resolve() / "supervisor-captures" / digest
        if root.is_symlink():
            raise HistoryEvidenceError("capture directory is a symlink")
        result: dict[str, bytes] = {}
        total = 0
        for item in inventory:
            if not isinstance(item, Mapping):
                raise HistoryEvidenceError("invalid capture file inventory")
            relative = _safe_snapshot_path(item.get("path"))
            name = relative.as_posix()
            size = item.get("size")
            match = _SHA256_RE.fullmatch(item.get("sha256", "")) if isinstance(item.get("sha256"), str) else None
            if name in result or not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > CAPTURE_FILE_LIMIT or match is None:
                raise HistoryEvidenceError("invalid capture file inventory")
            total += size
            if total > CAPTURE_TOTAL_LIMIT:
                raise HistoryEvidenceError("capture exceeds byte limit")
            candidate = root.joinpath(*relative.parts)
            cursor = candidate
            while cursor != root:
                if cursor.is_symlink():
                    raise HistoryEvidenceError("capture file is a symlink")
                cursor = cursor.parent
            try:
                candidate.resolve(strict=True).relative_to(root)
                with candidate.open("rb") as stream:
                    content = stream.read(size + 1)
            except (OSError, ValueError) as exc:
                raise HistoryEvidenceError("capture file is missing or escapes snapshot") from exc
            if len(content) != size or hashlib.sha256(content).hexdigest() != match.group(1):
                raise HistoryEvidenceError("capture file hash or size differs")
            result[name] = content
        return MappingProxyType(result)


def load_supervisor_history_view(artifact_root: Path) -> SupervisorHistoryView:
    """Read exactly seven bounded histories; malformed or absent files void evidence."""

    documents: dict[str, Mapping[str, object]] = {}
    for name, (schema, member) in _HISTORY_FILES.items():
        path = artifact_root / f"{name}.json"
        try:
            if path.is_symlink() or path.stat().st_size > _MAX_HISTORY_BYTES:
                raise ValueError("untrusted history file")
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return SupervisorHistoryView(artifact_root, MappingProxyType({}), "missing", name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return SupervisorHistoryView(artifact_root, MappingProxyType({}), "invalid", name)
        if not isinstance(document, dict) or document.get("schema") != schema:
            return SupervisorHistoryView(artifact_root, MappingProxyType({}), "invalid", name)
        rows = document.get(member)
        limit = QUERY_HISTORY_LIMIT if name == "query-history" else _MAX_HISTORY_ROWS
        if not isinstance(rows, list) or len(rows) > limit or any(not isinstance(row, dict) for row in rows):
            return SupervisorHistoryView(artifact_root, MappingProxyType({}), "invalid", name)
        documents[name] = _freeze(document)  # type: ignore[assignment]
    return SupervisorHistoryView(artifact_root, MappingProxyType(documents), "ready")

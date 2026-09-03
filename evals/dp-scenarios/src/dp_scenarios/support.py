"""Parsing and document helpers shared by the loader and the follow-up kinds.

These were private to ``scenario.py``. Follow-up kinds now live in their own
modules under ``followups/`` and need the same helpers, so they live here
rather than being imported back out of the loader -- ``scenario`` imports
``followups``, so a handler importing ``scenario`` would close a cycle.

Names keep their leading underscore. They are internal to the package, and
renaming them would have churned every call site in the loader for no gain.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


class ScenarioError(ValueError):
    """Raised when a scenario package is incomplete or internally inconsistent."""


_MISSING = object()


def _mapping(value: object, location: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ScenarioError(f"{location} must be a mapping")
    return dict(value)


def _unknown(value: Mapping[str, object], allowed: set[str], location: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ScenarioError(f"{location} contains unknown key(s): {', '.join(unknown)}")


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioError(f"{location} must be a non-empty string")
    return value


def _read_document(value: object, document_name: str | None = None) -> object:
    if isinstance(value, Mapping):
        return value
    path = Path(value) if isinstance(value, (str, Path)) else None
    if path is None or not path.exists():
        return _MISSING
    if path.is_file():
        candidates = [path]
    elif document_name is not None:
        document = Path(document_name)
        if document.is_absolute() or ".." in document.parts:
            return _MISSING
        candidates = [path / document]
    else:
        return _MISSING
    candidates = [candidate for candidate in candidates if candidate.is_file()]
    documents: list[Mapping[str, object]] = []
    for candidate in candidates:
        try:
            parsed = json.loads(candidate.read_text(encoding="utf-8")) if candidate.suffix.lower() == ".json" else yaml.safe_load(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError):
            continue
        if isinstance(parsed, Mapping):
            documents.append(dict(parsed))
    if not documents:
        return _MISSING
    merged: dict[str, object] = {}
    for document in documents:
        merged.update(document)
    return merged


def _lookup(value: object, dotted_path: str) -> object:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _required_flag(value: object, location: str) -> bool:
    declaration = _mapping(value, location)
    required = declaration.get("required")
    if not isinstance(required, bool):
        raise ScenarioError(f"{location}.required must be boolean")
    return required


def _requiredness_from_document(document: object, path: str) -> dict[str, bool] | None:
    if document is _MISSING:
        return None
    raw = _lookup(document, path)
    if not isinstance(raw, Mapping) or not raw:
        return None
    result: dict[str, bool] = {}
    for resource, value in raw.items():
        if not isinstance(resource, str):
            return None
        if isinstance(value, bool):
            result[resource] = value
            continue
        if isinstance(value, Mapping) and isinstance(value.get("required"), bool):
            result[resource] = value["required"]
            continue
        return None
    return result


def _row_count_mapping(value: object) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    candidate: object = value
    for key in ("row_count_oracle", "per_model_row_counts", "row_counts", "counts"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            candidate = nested
            break
    if not isinstance(candidate, Mapping) or not candidate:
        return None
    result: dict[str, int] = {}
    for resource, count in candidate.items():
        if (
            not isinstance(resource, str)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            return None
        result[resource] = count
    return result


def _manifest_row_counts(manifest: object) -> dict[str, int] | None:
    if isinstance(manifest, Mapping):
        table_counts = manifest.get("table_row_counts")
        if isinstance(table_counts, Mapping):
            return _row_count_mapping(table_counts)
    return _row_count_mapping(manifest)


def _count_rows(value: object) -> dict[str, int]:
    if not isinstance(value, list):
        raise ScenarioError("count gold must be a list of rows")
    result: dict[str, int] = {}
    for row in value:
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("resource"), str)
            or isinstance(row.get("row_count"), bool)
            or not isinstance(row.get("row_count"), int)
            or row["row_count"] < 0
        ):
            raise ScenarioError("count gold rows require resource and integer row_count")
        result[row["resource"]] = row["row_count"]
    return result

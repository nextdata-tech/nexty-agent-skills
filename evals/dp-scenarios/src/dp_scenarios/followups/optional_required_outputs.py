"""The optional/required-outputs follow-up kind.

Grades a valid resource that materialises no rows: a placeholder row fails,
and so does relaxing the checks that still guard required outputs.
"""

from __future__ import annotations

import csv

from collections.abc import Mapping
from pathlib import Path

from ..support import (
    _MISSING,
    ScenarioError,
    _count_rows,
    _manifest_row_counts,
    _mapping,
    _read_document,
    _required_flag,
    _requiredness_from_document,
    _row_count_mapping,
    _string,
)
from . import FollowUpContext, FollowUpKind, register


def check(
    scenario: object,
    target: object,
    settings: Mapping[str, object],
    context: FollowUpContext,
) -> Mapping[str, object]:

    fixture_dir = context.fixture_dir
    row_count_oracle = context.row_count_oracle
    resources = _mapping(settings.get("resources"), "follow-up.resources")
    declared_required = {
        resource: _required_flag(value, f"follow-up.resources.{resource}")
        for resource, value in resources.items()
    }
    findings: list[str] = []

    closure_target = target
    if isinstance(target, Mapping) and "closure" in target:
        closure_target = target.get("closure")
        if row_count_oracle is _MISSING:
            row_count_oracle = target.get("row_count_oracle", target.get("row_counts", _MISSING))

    requiredness_document = _read_document(
        closure_target,
        _string(settings.get("document"), "follow-up.document"),
    )
    observed_required = _requiredness_from_document(
        requiredness_document,
        _string(settings.get("requiredness_path"), "follow-up.requiredness_path"),
    )
    if observed_required is None:
        return {
            "status": "not-examined",
            "passed": False,
            "findings": ["requiredness_not_examined"],
        }
    if observed_required != declared_required:
        findings.append("requiredness_artifact_mismatch")

    count_source = "not-examined"
    actual_counts: dict[str, int] | None = None
    malformed_resources: set[str] = set()
    if row_count_oracle is not _MISSING:
        count_source = "row_count_oracle"
        actual_counts = _row_count_mapping(row_count_oracle)
        if actual_counts is None:
            return {
                "status": "not-examined",
                "passed": False,
                "findings": ["resource_counts_not_examined"],
            }
    elif isinstance(fixture_dir, (str, Path)):
        manifest = _read_document(fixture_dir, "fixture-manifest.json")
        actual_counts = _manifest_row_counts(manifest)
        if actual_counts is None:
            count_source = "closure_data"
        else:
            count_source = "fixture_manifest"
    elif isinstance(closure_target, Mapping):
        # Preserve the direct mapping API as an explicit oracle input.
        actual_counts = _row_count_mapping(closure_target)
        if actual_counts is None:
            count_source = "closure_data"
    if actual_counts is None and isinstance(closure_target, (str, Path)):
        count_source = "closure_data"
        root = Path(closure_target)
        data_root = root / "data"
        if not root.is_dir() or not data_root.is_dir():
            return {
                "status": "not-examined",
                "passed": False,
                "findings": ["resource_counts_not_examined"],
            }
        actual_counts = {}
        for resource in resources:
            path = data_root / f"{resource}.csv"
            if not path.is_file():
                continue
            try:
                with path.open(encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames or any(
                        not isinstance(field, str) or not field.strip() for field in reader.fieldnames
                    ):
                        malformed_resources.add(resource)
                        continue
                    actual_counts[resource] = sum(1 for _ in reader)
            except (OSError, UnicodeError, csv.Error):
                malformed_resources.add(resource)
        findings.extend(f"resource_malformed:{resource}" for resource in sorted(malformed_resources))
    if actual_counts is None:
        return {"status": "not-examined", "passed": False, "findings": ["resource_counts_not_examined"]}

    expected_counts = _count_rows(scenario.raw_gold("counts", fixture_dir))
    for resource, required in declared_required.items():
        if resource not in actual_counts:
            if resource in malformed_resources:
                continue
            if required is False:
                findings.append("optional_resource_absent")
            else:
                findings.append("required_resource_absent")
    if actual_counts != expected_counts:
        findings.append("resource_count_mismatch")
    optional = [resource for resource, required in declared_required.items() if required is False]
    if any(resource in actual_counts and actual_counts[resource] != 0 for resource in optional):
        findings.append("optional_placeholder_row")
    return {
        "status": "examined",
        "passed": not findings,
        "findings": findings,
        "actual_counts": actual_counts,
        "expected_counts": expected_counts,
        "required": declared_required,
        "observed_required": observed_required,
        "count_source": count_source,
    }


def _validate_settings(settings: Mapping[str, object]) -> None:
    if settings.get("count_source") != "row_count_oracle":
        raise ScenarioError("follow-up.count_source must be row_count_oracle")
    _string(settings.get("document"), "follow-up.document")
    _string(settings.get("requiredness_path"), "follow-up.requiredness_path")
    resources = _mapping(settings.get("resources"), "follow-up.resources")
    for resource, declaration in resources.items():
        _required_flag(declaration, f"follow-up.resources.{resource}")
    plant_evidence = _mapping(settings.get("plant_evidence"), "follow-up.plant_evidence")
    for plant, declaration in plant_evidence.items():
        evidence = _mapping(declaration, f"follow-up.plant_evidence.{plant}")
        _string(evidence.get("resource"), f"follow-up.plant_evidence.{plant}.resource")
        row_count = evidence.get("row_count")
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
            raise ScenarioError(
                f"follow-up.plant_evidence.{plant}.row_count must be a non-negative integer"
            )


KIND = register(
    FollowUpKind(
        name="optional_required_outputs",
        gold_keys=frozenset({"counts", "diagnostics"}),
        handler=check,
        certification_gold={"build": "counts", "query": "answer"},
        validate_settings=_validate_settings,
    )
)

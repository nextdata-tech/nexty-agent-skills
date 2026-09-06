"""Composable, deterministic defects for generated table frames.

An injector copies its input frame, performs only its declared mutation, and
returns an :class:`InjectionRecord` describing the exact rows and fields it
changed.  Injectors never use module-level random state: all selection draws
come from the ``random.Random`` instance supplied by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import math
import random
import re
from typing import Any, Callable, Collection, Mapping, MutableMapping, Sequence

Frame = list[dict[str, Any]]
Row = MutableMapping[str, Any]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class InjectionRecord:
    """A serializable account of one injector application."""

    name: str
    parameters: Mapping[str, Any]
    changed_rows: int
    changed_fields: tuple[str, ...]
    details: tuple[Mapping[str, Any], ...] = ()
    markers: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation with stable containers."""

        result: dict[str, Any] = {
            "name": self.name,
            "parameters": dict(self.parameters),
            "changed_rows": self.changed_rows,
            "changed_fields": list(self.changed_fields),
            "details": [_jsonable(detail) for detail in self.details],
        }
        if self.markers:
            result["markers"] = _jsonable(self.markers)
        return result


@dataclass(frozen=True)
class Injector:
    """A declaratively configured frame transformation."""

    name: str
    parameters: Mapping[str, Any]
    _apply: Callable[[Frame, random.Random], tuple[Frame, InjectionRecord]]

    def __call__(
        self, frame: Sequence[Mapping[str, Any]], rng: random.Random
    ) -> tuple[Frame, InjectionRecord]:
        """Apply this injector using ``rng`` and return a copied frame."""

        copied = [dict(row) for row in frame]
        return self._apply(copied, rng)


def _validate_rate(rate: float) -> float:
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        raise TypeError("rate must be a finite number between 0 and 1")
    value = float(rate)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("rate must be a finite number between 0 and 1")
    return value


def _rate_count(rate: float, size: int) -> int:
    """Use a documented floor rule, with one row for a positive non-empty rate."""

    if size == 0 or rate == 0.0:
        return 0
    return min(size, max(1, math.floor(rate * size)))


def _candidate_column(frame: Frame, candidates: Sequence[str], *, purpose: str) -> str:
    if not frame:
        raise ValueError(f"cannot inject {purpose} into an empty frame")
    present = set(frame[0])
    for candidate in candidates:
        if candidate in present:
            return candidate
    raise ValueError(f"could not find a {purpose} column")


def duplicate_rows(rate: float, *, ignorable_column: str | None = None) -> Injector:
    """Return an injector that appends exact and ignorable near-duplicates.

    ``floor(rate * row_count)`` rows are appended, with at least one row for a
    positive rate.  At least half of the appended rows (when two or more are
    requested) are near-duplicates differing only in ``ignorable_column``.
    An existing ignorable column is required.  Inventing a private column would
    make the near-duplicate rows impossible to serialize against the declared
    source schema, so the injector fails closed instead.
    """

    normalized_rate = _validate_rate(rate)
    params = {"rate": normalized_rate}
    if ignorable_column is not None:
        params["ignorable_column"] = ignorable_column

    def apply(frame: Frame, rng: random.Random) -> tuple[Frame, InjectionRecord]:
        count = _rate_count(normalized_rate, len(frame))
        if count == 0:
            return frame, InjectionRecord(
                "duplicate_rows", params, 0, (), ()
            )

        column = ignorable_column
        if column is None:
            for candidate in ("ignorable_note", "notes", "metadata", "updated_at"):
                if candidate in frame[0]:
                    column = candidate
                    break
        if column is None:
            raise ValueError(
                "duplicate_rows requires an existing ignorable column; "
                "pass ignorable_column or add notes/metadata to the frame"
            )
        if any(column not in row for row in frame):
            raise ValueError(f"ignorable column {column!r} is absent from the frame")

        selected = rng.sample(range(len(frame)), count)
        near_count = count // 2
        exact_count = count - near_count
        appended: Frame = []
        details: list[Mapping[str, Any]] = []
        for position, source_index in enumerate(selected):
            duplicate = dict(frame[source_index])
            kind = "exact" if position < exact_count else "near"
            before = duplicate.get(column)
            if kind == "near":
                duplicate[column] = f"{before} (reviewed)"
            appended.append(duplicate)
            details.append(
                {
                    "source_index": source_index,
                    "appended_index": len(frame) + position,
                    "kind": kind,
                    "ignorable_column": column,
                    "before": before,
                    "after": duplicate.get(column),
                }
            )
        return (
            frame + appended,
            InjectionRecord(
                "duplicate_rows",
                {**params, "ignorable_column": column},
                count,
                (column,),
                tuple(details),
            ),
        )

    return Injector("duplicate_rows", params, apply)


def _orphan_key(
    frame: Frame,
    key_column: str,
    before: Any,
    *,
    parent_keys: Collection[Any] | None = None,
    seed: int,
    dataset: str,
    ordinal: int,
    row_index: int,
) -> Any:
    """Derive a plausible key outside the parent table's generated range."""

    digest = hashlib.sha256(
        f"orphan-key-v2:{dataset}:{seed}:{ordinal}:{row_index}".encode("utf-8")
    ).hexdigest()
    offset = 1000 + int(digest[:8], 16) % 1000
    # The child frame can be missing parents entirely.  Use the supplied
    # parent key-set as the authoritative generated range; the frame fallback
    # keeps the low-level injector useful for callers that have no parent table.
    existing = list(parent_keys) if parent_keys is not None else [
        row.get(key_column) for row in frame
    ]
    if isinstance(before, int) and not isinstance(before, bool):
        numeric = [value for value in existing if isinstance(value, int) and not isinstance(value, bool)]
        return (max(numeric, default=0) + offset + ordinal)
    if isinstance(before, float):
        numeric = [value for value in existing if isinstance(value, (int, float)) and not isinstance(value, bool)]
        return float(max(numeric, default=0) + offset + ordinal)
    if isinstance(before, str):
        match = re.match(r"^(.*?)(\d+)$", before)
        if match:
            prefix, digits = match.groups()
            same_prefix = []
            for value in existing:
                if isinstance(value, str):
                    candidate = re.match(r"^(.*?)(\d+)$", value)
                    if candidate and candidate.group(1) == prefix:
                        same_prefix.append(int(candidate.group(2)))
            number = max(same_prefix, default=int(digits)) + offset + ordinal
            width = max(len(digits), len(str(number)))
            return f"{prefix}{number:0{width}d}"
        return f"{before}-{offset + ordinal}"
    return f"{type(before).__name__}-{offset + ordinal}"


def orphan_foreign_keys(
    count: int,
    *,
    parent_keys: Collection[Any] | None = None,
    seed: int = 0,
    dataset: str = "unknown",
) -> Injector:
    """Return an injector that makes child keys irreducibly orphaned.

    The replacement key keeps the parent key's surface form while moving beyond
    the generated numeric range.  The exact planted values are recorded in the
    injection record so a grader can identify them without exposing the
    diagnosis in the source data.
    """

    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count must be a non-negative integer")
    params = {"count": count}

    def apply(frame: Frame, rng: random.Random) -> tuple[Frame, InjectionRecord]:
        if count > len(frame):
            raise ValueError("orphan count cannot exceed frame row count")
        if count == 0:
            return frame, InjectionRecord("orphan_foreign_keys", params, 0, (), ())
        key_column = _candidate_column(
            frame,
            (
                "parent_id",
                "order_id",
                "warehouse_id",
                "customer_id",
                "account_id",
                "foreign_key",
            ),
            purpose="foreign key",
        )
        selected = rng.sample(range(len(frame)), count)
        details: list[Mapping[str, Any]] = []
        for ordinal, index in enumerate(selected):
            before = frame[index].get(key_column)
            after = _orphan_key(
                frame,
                key_column,
                before,
                parent_keys=parent_keys,
                seed=seed,
                dataset=dataset,
                ordinal=ordinal,
                row_index=index,
            )
            frame[index][key_column] = after
            details.append(
                {
                    "row_index": index,
                    "column": key_column,
                    "before": before,
                    "after": after,
                }
            )
        return (
            frame,
            InjectionRecord(
                "orphan_foreign_keys", {**params, "key_column": key_column}, count,
                (key_column,), tuple(details)
            ),
        )

    return Injector("orphan_foreign_keys", params, apply)


def tombstones(rate: float) -> Injector:
    """Return an injector marking physical rows as deleted."""

    normalized_rate = _validate_rate(rate)
    params = {"rate": normalized_rate}

    def apply(frame: Frame, rng: random.Random) -> tuple[Frame, InjectionRecord]:
        count = _rate_count(normalized_rate, len(frame))
        if count == 0:
            return frame, InjectionRecord("tombstones", params, 0, (), ())
        status_column = _candidate_column(
            frame,
            ("status", "state", "is_deleted"),
            purpose="status",
        )
        selected = rng.sample(range(len(frame)), count)
        details: list[Mapping[str, Any]] = []
        for index in selected:
            before = frame[index].get(status_column)
            after: Any = True if status_column == "is_deleted" else "deleted"
            frame[index][status_column] = after
            details.append(
                {"row_index": index, "column": status_column, "before": before, "after": after}
            )
        return (
            frame,
            InjectionRecord(
                "tombstones", {**params, "status_column": status_column}, count,
                (status_column,), tuple(details)
            ),
        )

    return Injector("tombstones", params, apply)


def _sentinel_for(column: str, *, seed: int, dataset: str) -> str:
    # The salt is not part of a dataset config.  Dataset and seed are included
    # so a stale marker from another fixture cannot masquerade as a fresh leak.
    digest = hashlib.sha512(
        b"dp-scenarios-pii-sentinel-v2\x00fixture-salt\x00"
        + dataset.encode("utf-8")
        + b"\x00"
        + str(seed).encode("ascii")
        + b"\x00"
        + column.encode("utf-8")
    ).hexdigest()
    lowered = column.lower()
    if "email" in lowered:
        return f"sentinel-{digest[:48]}@invalid.example"
    if "salary" in lowered or "amount" in lowered or "value" in lowered:
        return f"SALARY-SENTINEL-EUR-{digest[:48]}"
    return f"NAME-SENTINEL-{digest[:48]}"


def pii_sentinels(
    columns: Sequence[str], *, seed: int = 0, dataset: str = "unknown"
) -> Injector:
    """Return an injector planting exact, high-entropy marker strings."""

    selected_columns = tuple(columns)
    if not selected_columns or any(not isinstance(column, str) or not column for column in selected_columns):
        raise ValueError("columns must be a non-empty sequence of non-empty strings")
    if len(set(selected_columns)) != len(selected_columns):
        raise ValueError("columns must not contain duplicates")
    params = {"columns": list(selected_columns)}

    def apply(frame: Frame, rng: random.Random) -> tuple[Frame, InjectionRecord]:
        del rng  # Marker bytes are deterministic constants, not random draws.
        if not frame:
            raise ValueError("cannot plant PII sentinels into an empty frame")
        markers = {
            column: _sentinel_for(column, seed=seed, dataset=dataset)
            for column in selected_columns
        }
        details: list[Mapping[str, Any]] = []
        for column, marker in markers.items():
            before = frame[0].get(column)
            frame[0][column] = marker
            details.append(
                {"row_index": 0, "column": column, "before": before, "after": marker}
            )
        return (
            frame,
            InjectionRecord(
                "pii_sentinels", params, 1, selected_columns, tuple(details), markers
            ),
        )

    return Injector("pii_sentinels", params, apply)


def negative_values(column: str, count: int) -> Injector:
    """Return an injector making exactly ``count`` numeric values negative."""

    if not isinstance(column, str) or not column:
        raise ValueError("column must be a non-empty string")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count must be a non-negative integer")
    params = {"column": column, "count": count}

    def apply(frame: Frame, rng: random.Random) -> tuple[Frame, InjectionRecord]:
        if count > len(frame):
            raise ValueError("negative value count cannot exceed frame row count")
        if count == 0:
            return frame, InjectionRecord("negative_values", params, 0, (), ())
        if any(column not in row for row in frame):
            raise ValueError(f"column {column!r} is absent from the frame")
        selected = rng.sample(range(len(frame)), count)
        details: list[Mapping[str, Any]] = []
        for index in selected:
            before = frame[index][column]
            if not isinstance(before, (int, float, Decimal)) or isinstance(before, bool):
                raise TypeError(f"column {column!r} must contain numeric values")
            if isinstance(before, Decimal):
                after: Any = -abs(before) if before != 0 else Decimal("-1")
            elif isinstance(before, float):
                after = -abs(before) if before != 0 else -1.0
            else:
                after = -abs(before) if before != 0 else -1
            frame[index][column] = after
            details.append(
                {"row_index": index, "column": column, "before": before, "after": after}
            )
        return (
            frame,
            InjectionRecord("negative_values", params, count, (column,), tuple(details)),
        )

    return Injector("negative_values", params, apply)


def out_of_order_events(rate: float) -> Injector:
    """Return an injector that breaks timestamp order against a sequence column."""

    normalized_rate = _validate_rate(rate)
    params = {"rate": normalized_rate}

    def apply(frame: Frame, rng: random.Random) -> tuple[Frame, InjectionRecord]:
        count = _rate_count(normalized_rate, len(frame))
        if count < 2:
            return frame, InjectionRecord("out_of_order_events", params, 0, (), ())
        timestamp_column = _candidate_column(
            frame,
            ("event_timestamp", "order_timestamp", "timestamp", "created_at"),
            purpose="event timestamp",
        )
        sequence_column = _candidate_column(
            frame,
            ("sequence", "sequence_number", "event_sequence", "position"),
            purpose="monotonic event sequence",
        )
        selected = sorted(rng.sample(range(len(frame)), count))
        before = [frame[index].get(timestamp_column) for index in selected]
        for index, timestamp in zip(selected, reversed(before)):
            frame[index][timestamp_column] = timestamp
        after = [frame[index].get(timestamp_column) for index in selected]
        details = (
            {
                "positions": selected,
                "timestamp_column": timestamp_column,
                "sequence_column": sequence_column,
                "before": before,
                "after": after,
            },
        )
        return (
            frame,
            InjectionRecord(
                "out_of_order_events", params, count, (timestamp_column,), details
            ),
        )

    return Injector("out_of_order_events", params, apply)


INJECTOR_FACTORIES: Mapping[str, Callable[..., Injector]] = {
    "duplicate_rows": duplicate_rows,
    "orphan_foreign_keys": orphan_foreign_keys,
    "tombstones": tombstones,
    "pii_sentinels": pii_sentinels,
    "negative_values": negative_values,
    "out_of_order_events": out_of_order_events,
}


def make_injector(
    name: str,
    parameters: Mapping[str, Any],
    *,
    seed: int = 0,
    dataset: str = "unknown",
) -> Injector:
    """Build an injector from a declarative name and parameter mapping."""

    try:
        factory = INJECTOR_FACTORIES[name]
    except KeyError as exc:
        raise ValueError(f"unknown injector {name!r}") from exc
    kwargs = dict(parameters)
    if name in {"orphan_foreign_keys", "pii_sentinels"}:
        kwargs.update(seed=seed, dataset=dataset)
    return factory(**kwargs)


__all__ = [
    "Frame",
    "InjectionRecord",
    "Injector",
    "INJECTOR_FACTORIES",
    "duplicate_rows",
    "make_injector",
    "negative_values",
    "orphan_foreign_keys",
    "out_of_order_events",
    "pii_sentinels",
    "tombstones",
]

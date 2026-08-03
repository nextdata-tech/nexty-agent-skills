"""The three record types. CONTRACT.md §2.

Long-form records are authoritative; the wide model is a projection. This module
owns the physical shape of `mapper_proposals`, `mapper_reviews`, and
`mapper_evidence`, plus long-form <-> CSV serialization.

The five-slot typed value is the load-bearing design decision here. A single
string column would satisfy the letter of "no sentinel in a numeric column"
(because there would be no numeric column) and defeat the purpose: every
consumer casts, and a bad cast becomes a query-time error instead of a
build-time one. Five nullable slots keep the type in the schema where a metric
can be defined over it.

Pure stdlib.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .errors import SpecError
from .identity import value_hash

__all__ = [
    "ValueStatus",
    "ValueType",
    "Verdict",
    "VerifyStatus",
    "LocatorKind",
    "EffectiveSource",
    "StaleReason",
    "TypedValue",
    "MapperProposal",
    "MapperEvidence",
    "MapperReview",
    "PROPOSAL_COLUMNS",
    "EVIDENCE_COLUMNS",
    "REVIEW_COLUMNS",
    "rows_to_csv",
    "reviews_from_csv",
    "proposals_from_csv",
    "evidence_from_csv",
]


class _LandedEnum(str, Enum):
    """A string enum that is safe to land in a CSV column.

    `str, Enum` alone is NOT safe here. On Python 3.11+ `str(ValueStatus.OK)`
    and `f"{ValueStatus.OK}"` both render `ValueStatus.OK`, not `ok` — so any
    writer that formats a member instead of reading `.value` silently lands the
    repr in a governed column, and the enum's own `ALL` check would then reject
    the data it just wrote. `as_row()` is careful today; this base class makes
    carelessness impossible tomorrow, which is what lets `validate.py` share
    these members instead of maintaining a parallel set of bare constants.
    """

    def __str__(self) -> str:
        return self.value

    def __format__(self, spec: str) -> str:
        return format(self.value, spec)

    @classmethod
    def all_values(cls) -> frozenset[str]:
        """The landed vocabulary. A value outside it is a schema violation."""
        return frozenset(m.value for m in cls)


class ValueStatus(_LandedEnum):
    """Exactly five values. Any other value is a schema violation.

    `SKIPPED` is an addition to the design's four-value list, and it is not
    cosmetic: without it, a run that stops at 60% coverage lands the remaining
    40% as `evidence_absent` — indistinguishable from a genuinely silent source,
    which is precisely the "100%-sentinel green build" the design forbids.
    `skipped` makes partial coverage visibly partial.
    """

    OK = "ok"
    EVIDENCE_ABSENT = "evidence_absent"
    VALIDATION_FAILED = "validation_failed"
    ERROR = "error"
    SKIPPED = "skipped"


class ValueType(_LandedEnum):
    """Which typed slot is authoritative. Populated even when the value is null,
    so the resolver knows the column's type without consulting the spec."""

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    TIMESTAMP = "timestamp"


class Verdict(_LandedEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    OVERRIDDEN = "overridden"


class VerifyStatus(_LandedEnum):
    """`VERIFIED` is the ONLY value that may claim substring verification.

    Mirrored by a second class of the same name in `validate.py`, whose member
    NAMES differ (`UNVERIFIED`, `FAILED`) while the string VALUES match. The two
    are bridged only by the string, in `mapper._evidence_for`. Adding a member
    to one side alone raises at atom construction.
    """

    VERIFIED = "verified"
    EVIDENCE_UNVERIFIED = "evidence_unverified"
    VERIFY_FAILED = "verify_failed"
    #: The quote was extracted from the document BY THE API (citations) rather
    #: than authored by the model — a second party's reading of the bytes.
    #:
    #: Deliberately NOT `verified`. That value promises the harness ran a check
    #: it can re-run offline from `text_hash` + offsets; an API citation cannot
    #: be re-checked without trusting the same response again. It counts as
    #: verified-equivalent for GATING (both ceilings in `validate.py` test
    #: `== UNVERIFIED`, so it neither inflates `unverified_share` nor trips the
    #: unverified block) while staying distinct in the audit trail, so "which of
    #: these did we check ourselves?" stays answerable.
    API_CITED = "api_cited"


class LocatorKind(_LandedEnum):
    LANDED_TEXT = "landed_text"
    PAGE_REGION = "page_region"
    SOURCE_FIELD = "source_field"


class EffectiveSource(_LandedEnum):
    MODEL_PROPOSED = "model_proposed"
    MODEL_CONFIRMED = "model_confirmed"
    HUMAN_OVERRIDE = "human_override"
    HUMAN_REJECTED = "human_rejected"


class StaleReason(_LandedEnum):
    VALUE_CHANGED = "value_changed"
    INPUT_CHANGED = "input_changed"
    SPEC_CHANGED = "spec_changed"


#: Slot column name per type, for proposals.
_SLOT = {
    ValueType.STRING: "value_string",
    ValueType.INT: "value_int",
    ValueType.FLOAT: "value_float",
    ValueType.BOOL: "value_bool",
    ValueType.TIMESTAMP: "value_timestamp",
}

#: Slot column name per type, for review overrides.
_OVERRIDE_SLOT = {
    ValueType.STRING: "override_value_string",
    ValueType.INT: "override_value_int",
    ValueType.FLOAT: "override_value_float",
    ValueType.BOOL: "override_value_bool",
    ValueType.TIMESTAMP: "override_value_timestamp",
}


@dataclass(frozen=True)
class TypedValue:
    """A value plus the slot it belongs in. `value is None` is legal and common.

    Keeping type and value together is what stops the "which column do I read?"
    question from being answered by guessing at query time.
    """

    value_type: ValueType
    value: Any = None

    def __post_init__(self) -> None:
        """Canonicalize the value into its declared slot type.

        ONE encoding, both directions. Without this, a model answering `90` for
        a float field produced `TypedValue(FLOAT, 90)` — `check_type` accepts a
        JSON int for a float field and does not coerce — while the same cell
        read back from landed CSV produced `TypedValue(FLOAT, 90.0)`. Those hash
        differently (`value_hash` canonicalizes the VALUE, and `90` is not
        `90.0` in JSON), so every review bound to that cell went stale on the
        next `resolve` with `value_changed`, for a reason no human could see:
        both sides display `90`.

        Canonicalizing here rather than in `value_hash` keeps `slots()` honest
        too — the landed column gets the same float the hash was taken over.
        """
        if self.value is None:
            return
        if self.value_type is ValueType.FLOAT and isinstance(self.value, int):
            # bool is an int subclass; a bool in a float slot is a type error,
            # not something to silently widen to 1.0.
            if not isinstance(self.value, bool):
                object.__setattr__(self, "value", float(self.value))

    @property
    def is_null(self) -> bool:
        return self.value is None

    @property
    def hash(self) -> str:
        return value_hash(self.value_type.value, self.value)

    def slots(self, mapping: dict[ValueType, str]) -> dict[str, Any]:
        """Expand into the five nullable columns; exactly one may be non-null."""
        out: dict[str, Any] = {name: None for name in mapping.values()}
        if self.value is not None:
            out[mapping[self.value_type]] = self.value
        return out


PROPOSAL_COLUMNS: tuple[str, ...] = (
    "target_row_key",
    "field",
    "value_string",
    "value_int",
    "value_float",
    "value_bool",
    "value_timestamp",
    "value_type",
    "value_hash",
    "value_status",
    "error_code",
    "error_detail",
    "attempt_count",
    "attempt_id",
    "needs_review",
    "evidence_count",
    "observation_id",
    "input_snapshot_id",
    "mapper_spec_id",
    "execution_id",
    "emission_ordinal",
)

EVIDENCE_COLUMNS: tuple[str, ...] = (
    "target_row_key",
    "field",
    "evidence_ordinal",
    "locator_kind",
    "source_model",
    "source_row_key",
    "source_field_name",
    "document_hash",
    "page",
    "char_start",
    "char_end",
    "quote",
    "verify_status",
    "extractor",
    "extractor_version",
    "text_hash",
)

REVIEW_COLUMNS: tuple[str, ...] = (
    "review_id",
    "target_row_key",
    "field",
    "verdict",
    "override_value_string",
    "override_value_int",
    "override_value_float",
    "override_value_bool",
    "override_value_timestamp",
    "override_value_type",
    "bound_value_hash",
    "bound_input_snapshot_id",
    "bound_mapper_spec_id",
    "reviewer",
    "reviewed_at",
    "note",
)


@dataclass
class MapperEvidence:
    """One-to-many per proposal. Replace-loaded with the proposals it belongs to.

    Always produced and landed together with its proposal, from the same
    in-memory bundle — there is no API that returns proposals without their
    evidence, because that API is how the orphan-evidence bug gets written.
    """

    target_row_key: str
    field: str
    evidence_ordinal: int
    quote: str
    verify_status: VerifyStatus
    locator_kind: LocatorKind = LocatorKind.SOURCE_FIELD
    source_model: str | None = None
    source_row_key: str | None = None
    source_field_name: str | None = None
    document_hash: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    extractor: str | None = None
    extractor_version: str | None = None
    text_hash: str | None = None

    def as_row(self) -> dict[str, Any]:
        return {
            "target_row_key": self.target_row_key,
            "field": self.field,
            "evidence_ordinal": self.evidence_ordinal,
            "locator_kind": self.locator_kind.value,
            "source_model": self.source_model,
            "source_row_key": self.source_row_key,
            "source_field_name": self.source_field_name,
            "document_hash": self.document_hash,
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "quote": self.quote,
            "verify_status": self.verify_status.value,
            "extractor": self.extractor,
            "extractor_version": self.extractor_version,
            "text_hash": self.text_hash,
        }

    def digest_payload(self) -> dict[str, Any]:
        """The subset that identifies this atom for `observation_id`.

        Deliberately excludes `verify_status`: the observation is what the model
        cited, and re-verifying the same citation against the same text must not
        produce a different observation id.
        """
        return {
            "ordinal": self.evidence_ordinal,
            "locator_kind": self.locator_kind.value,
            "quote": self.quote,
            "text_hash": self.text_hash,
            "document_hash": self.document_hash,
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass
class MapperProposal:
    """One row per `(target_row_key, field)` produced by this execution.

    Replace-loaded every build: this is the run's output, not durable state.
    Uniqueness is `(target_row_key, field)`; a duplicate is a hard build failure
    rather than last-write-wins, because duplicate emission means the spec's row
    identity is under-determined.
    """

    target_row_key: str
    field: str
    typed: TypedValue
    value_status: ValueStatus
    mapper_spec_id: str
    input_snapshot_id: str
    execution_id: str
    observation_id: str
    emission_ordinal: int
    evidence: list[MapperEvidence] = dc_field(default_factory=list)
    error_code: str | None = None
    error_detail: str | None = None
    attempt_count: int = 0
    attempt_id: str | None = None
    needs_review: bool = False

    def __post_init__(self) -> None:
        # Status/value coherence is asserted here as well as in the consistency
        # pass, because constructing an incoherent record and catching it later
        # means the incoherent record already reached a ledger line and a log.
        if self.value_status is ValueStatus.OK:
            if self.typed.is_null:
                raise SpecError(
                    f"{self.target_row_key}/{self.field}: value_status=ok "
                    "requires exactly one non-null typed slot"
                )
        elif not self.typed.is_null:
            raise SpecError(
                f"{self.target_row_key}/{self.field}: value_status="
                f"{self.value_status.value} requires all typed slots null; a row "
                "that failed validation does not land the value that failed it"
            )
        has_code = self.error_code is not None
        is_error = self.value_status is ValueStatus.ERROR
        if has_code != is_error:
            raise SpecError(
                f"{self.target_row_key}/{self.field}: error_code non-null iff "
                f"value_status=error (code={self.error_code!r}, "
                f"status={self.value_status.value})"
            )

    @property
    def key(self) -> tuple[str, str]:
        return (self.target_row_key, self.field)

    @property
    def value_hash(self) -> str:
        return self.typed.hash

    def as_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "target_row_key": self.target_row_key,
            "field": self.field,
            "value_type": self.typed.value_type.value,
            "value_hash": self.value_hash,
            "value_status": self.value_status.value,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "attempt_count": self.attempt_count,
            "attempt_id": self.attempt_id,
            "needs_review": self.needs_review,
            "evidence_count": len(self.evidence),
            "observation_id": self.observation_id,
            "input_snapshot_id": self.input_snapshot_id,
            "mapper_spec_id": self.mapper_spec_id,
            "execution_id": self.execution_id,
            "emission_ordinal": self.emission_ordinal,
        }
        row.update(self.typed.slots(_SLOT))
        return row


@dataclass
class MapperReview:
    """Durable human state. NEVER replace-loaded away.

    Uniqueness is `review_id`, NOT `(target_row_key, field)` — a later review of
    the same cell is a new row, and the resolver picks the latest valid one.
    Rows are immutable and append-only.
    """

    review_id: str
    target_row_key: str
    field: str
    verdict: Verdict
    bound_input_snapshot_id: str
    bound_mapper_spec_id: str
    reviewer: str
    reviewed_at: str
    bound_value_hash: str | None = None
    override: TypedValue | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.verdict is Verdict.OVERRIDDEN and self.override is None:
            raise SpecError(
                f"review {self.review_id}: verdict=overridden requires an "
                "override value"
            )
        if self.verdict is not Verdict.OVERRIDDEN and self.override is not None:
            raise SpecError(
                f"review {self.review_id}: override value is only meaningful "
                "with verdict=overridden"
            )
        # A model does not review. If a model name could land here, the
        # human-precedence rule in the resolver would silently become
        # model-precedence.
        if not self.reviewer or self.reviewer.strip() == "":
            raise SpecError(f"review {self.review_id}: reviewer is required")
        # The one legal null-binding case: a human overriding a cell the model
        # never produced has no value hash to bind to, and forcing one would
        # make the "human fills the gap" case unrepresentable.
        if self.bound_value_hash is None and self.verdict is not Verdict.OVERRIDDEN:
            raise SpecError(
                f"review {self.review_id}: bound_value_hash may only be null "
                "for verdict=overridden (overriding an absent proposal)"
            )

    @property
    def key(self) -> tuple[str, str]:
        return (self.target_row_key, self.field)

    def as_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "review_id": self.review_id,
            "target_row_key": self.target_row_key,
            "field": self.field,
            "verdict": self.verdict.value,
            "override_value_type": (
                self.override.value_type.value if self.override else None
            ),
            "bound_value_hash": self.bound_value_hash,
            "bound_input_snapshot_id": self.bound_input_snapshot_id,
            "bound_mapper_spec_id": self.bound_mapper_spec_id,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
            "note": self.note,
        }
        if self.override is not None:
            row.update(self.override.slots(_OVERRIDE_SLOT))
        else:
            row.update({name: None for name in _OVERRIDE_SLOT.values()})
        return row


def rows_to_csv(rows: Iterable[dict[str, Any]], columns: Sequence[str]) -> str:
    """Serialize to CSV with a fixed column order.

    Column order is fixed by the constant, not by dict iteration order, so the
    landed file is byte-stable across runs — a file whose column order drifts
    would show up as a spurious diff on every rebuild.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(columns), extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: _csv_cell(row.get(c)) for c in columns})
    return buf.getvalue()


def _csv_cell(value: Any) -> Any:
    """Render one cell. `None` becomes the empty field, booleans become
    lowercase literals so the CSV round-trips through DuckDB predictably."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _typed_from_row(
    row: Mapping[str, Any], mapping: Mapping[ValueType, str]
) -> TypedValue:
    """Rebuild a `TypedValue` from the five nullable slot columns.

    The declared `value_type` decides which slot is authoritative — NOT
    "whichever column is non-empty". Reading it the other way would silently
    retype a null cell: an `evidence_absent` int cell has every slot empty, and
    guessing from emptiness would make it a string.

    CSV carries no types, so slot text is coerced back through the declared
    type. This is not cosmetic: `value_hash` is computed over
    `(value_type, value)`, so a float landing back as the string "90.0" hashes
    differently, and every review bound to that cell would go stale for a reason
    no human could see.
    """
    value_type = ValueType(str(row["value_type"]))
    raw = row.get(mapping[value_type])
    if raw in ("", None):
        return TypedValue(value_type=value_type, value=None)
    text = str(raw)
    if value_type is ValueType.INT:
        return TypedValue(value_type=value_type, value=int(text))
    if value_type is ValueType.FLOAT:
        return TypedValue(value_type=value_type, value=float(text))
    if value_type is ValueType.BOOL:
        return TypedValue(value_type=value_type, value=text.lower() == "true")
    return TypedValue(value_type=value_type, value=text)


def _strict_bool(raw: Any, lineno: int) -> bool:
    """Parse `true`/`false` and NOTHING else.

    `needs_review` is the one flag that means "a human must look at this", so a
    missing or unparseable column must not quietly become `False` — that clears
    every human-attention marker in a hand-trimmed or truncated CSV with no
    error anywhere. The previous form, `str(row.get(...)).lower() == "true"`,
    turned a missing key into the string "none" and then into False.
    """
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower() if raw is not None else ""
    if text == "true":
        return True
    if text == "false":
        return False
    raise SpecError(
        f"mapper_proposals.csv line {lineno}: needs_review is {raw!r}, expected "
        f"'true' or 'false'. Defaulting it would silently clear a human-review "
        f"marker."
    )


def proposals_from_csv(
    text: str, evidence: Iterable[MapperEvidence] = ()
) -> list[MapperProposal]:
    """Parse landed `mapper_proposals.csv` back into records.

    The inverse of `as_row()`, and what lets `resolve` run as a separate step at
    all: re-resolving reads the LANDED long form instead of re-calling the
    model, which is what makes a review cycle free.

    `evidence` re-attaches the atoms by `(target_row_key, field)`. Pass it
    whenever the sidecar is available: `evidence_count` is DERIVED from
    `len(self.evidence)`, so a proposal parsed without its atoms re-serializes
    with `evidence_count = 0` while the atoms still exist in the evidence table.
    That is a silent corruption of the provenance join — the proposal claims no
    evidence supports it and the sidecar disagrees. Caught by diffing a
    round-trip, not by reading.
    """
    by_cell: dict[tuple[str, str], list[MapperEvidence]] = {}
    for atom in evidence:
        by_cell.setdefault((atom.target_row_key, atom.field), []).append(atom)

    out: list[MapperProposal] = []
    for lineno, raw in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        row = {k: (v if v not in ("", None) else None) for k, v in raw.items()}
        try:
            key = (str(row["target_row_key"]), str(row["field"]))
            out.append(
                MapperProposal(
                    target_row_key=key[0],
                    field=key[1],
                    evidence=by_cell.get(key, []),
                    typed=_typed_from_row(row, _SLOT),
                    value_status=ValueStatus(str(row["value_status"])),
                    error_code=row.get("error_code"),
                    error_detail=row.get("error_detail"),
                    attempt_count=int(row.get("attempt_count") or 0),
                    attempt_id=row.get("attempt_id"),
                    needs_review=_strict_bool(row.get("needs_review"), lineno),
                    observation_id=str(row.get("observation_id") or ""),
                    input_snapshot_id=str(row.get("input_snapshot_id") or ""),
                    mapper_spec_id=str(row.get("mapper_spec_id") or ""),
                    execution_id=str(row.get("execution_id") or ""),
                    emission_ordinal=int(row.get("emission_ordinal") or 0),
                )
            )
        except (KeyError, ValueError) as exc:
            raise SpecError(f"mapper_proposals.csv line {lineno}: {exc}") from exc
    return out


def evidence_from_csv(text: str) -> list[MapperEvidence]:
    """Parse landed `mapper_evidence.csv` back into records."""
    out: list[MapperEvidence] = []
    for lineno, raw in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        row = {k: (v if v not in ("", None) else None) for k, v in raw.items()}
        try:
            page = row.get("page")
            start = row.get("char_start")
            end = row.get("char_end")
            out.append(
                MapperEvidence(
                    target_row_key=str(row["target_row_key"]),
                    field=str(row["field"]),
                    evidence_ordinal=int(row.get("evidence_ordinal") or 0),
                    quote=str(row.get("quote") or ""),
                    verify_status=VerifyStatus(str(row["verify_status"])),
                    locator_kind=LocatorKind(str(row["locator_kind"])),
                    source_model=row.get("source_model"),
                    source_row_key=row.get("source_row_key"),
                    source_field_name=row.get("source_field_name"),
                    document_hash=row.get("document_hash"),
                    page=int(page) if page is not None else None,
                    char_start=int(start) if start is not None else None,
                    char_end=int(end) if end is not None else None,
                    extractor=row.get("extractor"),
                    extractor_version=row.get("extractor_version"),
                    text_hash=row.get("text_hash"),
                )
            )
        except (KeyError, ValueError) as exc:
            raise SpecError(f"mapper_evidence.csv line {lineno}: {exc}") from exc
    return out


def reviews_from_csv(text: str) -> list[MapperReview]:
    """Parse a reviewer-authored batch CSV into `MapperReview` records.

    Tolerant about absent optional columns (a hand-editing reviewer should not
    have to type sixteen headers) and strict about the ones that carry meaning.
    Every constructed record still goes through `MapperReview.__post_init__`, so
    a malformed review fails at load rather than silently mis-resolving later.
    """
    reader = csv.DictReader(io.StringIO(text))
    out: list[MapperReview] = []
    for lineno, raw in enumerate(reader, start=2):
        row = {k: (v if v not in ("", None) else None) for k, v in raw.items()}
        try:
            verdict = Verdict(row["verdict"])
        except (KeyError, ValueError) as exc:
            raise SpecError(
                f"review CSV line {lineno}: bad or missing verdict "
                f"{row.get('verdict')!r}; expected one of "
                f"{[v.value for v in Verdict]}"
            ) from exc

        override: TypedValue | None = None
        override_type = row.get("override_value_type")
        if override_type:
            vt = ValueType(override_type)
            override = TypedValue(vt, _parse_slot(vt, row.get(_OVERRIDE_SLOT[vt])))

        out.append(
            MapperReview(
                review_id=_require(row, "review_id", lineno),
                target_row_key=_require(row, "target_row_key", lineno),
                field=_require(row, "field", lineno),
                verdict=verdict,
                bound_value_hash=row.get("bound_value_hash"),
                override=override,
                bound_input_snapshot_id=_require(
                    row, "bound_input_snapshot_id", lineno
                ),
                bound_mapper_spec_id=_require(row, "bound_mapper_spec_id", lineno),
                reviewer=_require(row, "reviewer", lineno),
                reviewed_at=_require(row, "reviewed_at", lineno),
                note=row.get("note"),
            )
        )
    return out


def _require(row: dict[str, Any], key: str, lineno: int) -> str:
    value = row.get(key)
    if value is None:
        raise SpecError(f"review CSV line {lineno}: missing required column {key!r}")
    return str(value)


def _parse_slot(value_type: ValueType, raw: Any) -> Any:
    """Cast a CSV string into the declared type.

    A bad cast raises rather than falling back to the string, because a review
    that silently overrides an int column with the string `"4"` is exactly the
    type confusion the five-slot design exists to prevent.
    """
    if raw is None:
        return None
    text = str(raw)
    try:
        if value_type is ValueType.INT:
            return int(text)
        if value_type is ValueType.FLOAT:
            return float(text)
        if value_type is ValueType.BOOL:
            lowered = text.strip().casefold()
            if lowered in ("true", "1", "yes"):
                return True
            if lowered in ("false", "0", "no"):
                return False
            raise ValueError(text)
    except ValueError as exc:
        raise SpecError(
            f"override value {text!r} is not a valid {value_type.value}"
        ) from exc
    return text

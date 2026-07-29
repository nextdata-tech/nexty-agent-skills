"""The constraint layer JSON Schema cannot express, plus the coverage gate.

CONTRACT.md §8 routes every spec constraint to one of two enforcers. The wire
schema owns `type`, `enum`, `const`, `required`. It owns NOTHING else — this API's
JSON Schema supports neither `minimum`/`maximum`/`multipleOf` nor
`minLength`/`maxLength`. Everything in that gap lands here:

    numeric range      -> `check_range`
    string length      -> `check_length`
    closed value set   -> `check_enum`   (belt-and-braces; schema owns it too)
    evidence substring -> `verify_quote`

This is where retry earns its place. A range violation is a *recoverable* model
error the API cannot catch, so re-asking with the violation named is a legitimate
and bounded correction. Retry is NOT a way to paper over transport failure —
`transport.py` owns that budget, and the two are never conflated (§8).

Pure stdlib. No API calls, no `anthropic` import, no network. `run_with_retry`
takes the attempt as a callable so this module stays independently unit-testable
and so no code path here can reach the wire.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field as dc_field
from typing import Any

from .errors import CoverageBlocked, SpecError

__all__ = [
    "ValueStatus",
    "VerifyStatus",
    "Violation",
    "FieldConstraint",
    "ValidatedCell",
    "CoverageReport",
    "normalize_text",
    "check_type",
    "check_enum",
    "check_range",
    "check_length",
    "verify_quote",
    "validate_value",
    "run_with_retry",
    "evaluate_coverage",
]


# --------------------------------------------------------------------------
# Enums. Kept as plain string constants: these land in a CSV column, and a
# str-subclass enum would serialize with its repr under a careless writer.
# --------------------------------------------------------------------------


class ValueStatus:
    """CONTRACT.md §3. Exactly five values; any other is a schema violation."""

    OK = "ok"
    EVIDENCE_ABSENT = "evidence_absent"
    VALIDATION_FAILED = "validation_failed"
    ERROR = "error"
    SKIPPED = "skipped"

    ALL = frozenset({OK, EVIDENCE_ABSENT, VALIDATION_FAILED, ERROR, SKIPPED})
    #: Statuses for which ALL five typed value slots must be null (§3).
    NULL_VALUED = frozenset({EVIDENCE_ABSENT, VALIDATION_FAILED, ERROR, SKIPPED})


class VerifyStatus:
    """CONTRACT.md §2.3."""

    #: The normalized quote IS a substring of the landed normalized text.
    #: The ONLY value that may claim substring verification.
    VERIFIED = "verified"
    #: No canonical landed text exists. The build does not claim verification.
    UNVERIFIED = "evidence_unverified"
    #: Landed text exists and the quote is NOT in it. A hallucinated citation.
    FAILED = "verify_failed"

    ALL = frozenset({VERIFIED, UNVERIFIED, FAILED})


#: Which typed slot each declared type writes into (CONTRACT.md §2.1).
_TYPE_SLOTS = {
    "string": "value_string",
    "int": "value_int",
    "float": "value_float",
    "bool": "value_bool",
    "timestamp": "value_timestamp",
}


# --------------------------------------------------------------------------
# Violations
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    """One constraint failure, in a form that can be fed back to the model.

    `message` is the retry feedback. It names the field, the constraint, and
    what was received — and it is the ONLY thing sent back on a retry. It must
    never carry source content beyond the offending value itself, because this
    string is also written to `error_detail`, which §2.1 requires to be redacted.
    """

    field: str
    kind: str  # type | enum | range | length | evidence
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class FieldConstraint:
    """The Layer-2-declared constraints for one target field.

    Everything here comes from the landed mapper spec, never from a dict literal
    in a transform (design §12). `validate.py` only enforces; it never decides
    what the constraint should be.
    """

    name: str
    value_type: str  # one of _TYPE_SLOTS
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[Any, ...] | None = None
    min_length: int | None = None
    max_length: int | None = None
    #: Minimum evidence atoms required for this field to reach `ok`.
    min_evidence: int = 0
    #: Whether the spec marks this field required — drives `needs_review` on
    #: `evidence_absent` (§3).
    required: bool = False

    def __post_init__(self) -> None:
        if self.value_type not in _TYPE_SLOTS:
            raise SpecError(
                f"field {self.name!r}: unknown value_type {self.value_type!r}; "
                f"expected one of {sorted(_TYPE_SLOTS)}"
            )
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise SpecError(
                f"field {self.name!r}: minimum {self.minimum} exceeds maximum "
                f"{self.maximum}"
            )
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise SpecError(
                f"field {self.name!r}: min_length {self.min_length} exceeds "
                f"max_length {self.max_length}"
            )
        # A range on a non-numeric field is a spec authoring error, not a
        # silently-ignored no-op. Catching it here is why the spec is data.
        if (self.minimum is not None or self.maximum is not None) and (
            self.value_type not in ("int", "float")
        ):
            raise SpecError(
                f"field {self.name!r}: numeric range declared on non-numeric "
                f"type {self.value_type!r}"
            )
        if (self.min_length is not None or self.max_length is not None) and (
            self.value_type != "string"
        ):
            raise SpecError(
                f"field {self.name!r}: length constraint declared on "
                f"non-string type {self.value_type!r}"
            )

    @property
    def slot(self) -> str:
        """The `value_*` column this field's value lands in."""
        return _TYPE_SLOTS[self.value_type]


# --------------------------------------------------------------------------
# Normalization — the ONLY transformation applied before a substring check.
# --------------------------------------------------------------------------

#: Unicode separators that a PDF extractor emits and a model does not reproduce.
#: Folded to a plain space BEFORE whitespace collapsing. This is still
#: normalization, not fuzziness: it changes the encoding of a space, never a
#: character's identity.
_SPACE_LIKE = {
    " ",  # no-break space
    " ",  # figure space
    " ",  # narrow no-break space
    " ", " ", " ", " ", " ",
    " ", " ", " ", " ", " ",  # en/em/thin spaces
    "　",  # ideographic space
    "​",  # zero-width space
}


def normalize_text(text: str) -> str:
    """Whitespace-and-case normalization ONLY. Never fuzzy.

    Applied identically to both sides of every substring check:

    1. NFKC — folds ligatures and compatibility forms a PDF extractor emits
       (`ﬁ` -> `fi`). An encoding difference, not a wording difference.
    2. Space-like Unicode -> plain space.
    3. Collapse runs of whitespace to one space; strip ends.
    4. Casefold.

    This is the whole list, and it is deliberately short. Fuzzy matching is
    exactly where the teeth fall out — a substring check that tolerates
    paraphrase stops catching fabrication (llm-judgments.md). If this check
    fires on an honest paraphrase, the fix is a TIGHTER QUOTE (cite the verbatim
    span the value rests on), never a looser matcher. No edit distance, no
    token-set overlap, no embedding similarity — not now, not behind a flag.
    """
    text = unicodedata.normalize("NFKC", text)
    text = "".join(" " if ch in _SPACE_LIKE else ch for ch in text)
    return " ".join(text.split()).casefold()


# --------------------------------------------------------------------------
# The individual checks
# --------------------------------------------------------------------------


def check_type(constraint: FieldConstraint, value: Any) -> Violation | None:
    """Type check with NO coercion of a wrong-typed value into a right one.

    Coercing would let `"4"` satisfy an int field and hide a model that is not
    honoring the wire schema. The one accommodation: JSON has a single number
    type, so an int is accepted for a `float` field (`4` -> `4.0` is lossless
    and is what the wire actually carries). The reverse is refused — `4.5` in an
    int field is a real violation, and silently truncating it would fabricate.
    """
    if value is None:
        return None  # Absence is `evidence_absent`, decided by the caller.
    expected = constraint.value_type
    if expected == "bool":
        # Checked first: `bool` is a subclass of `int` in Python, so an
        # `isinstance(value, int)` test below would otherwise accept `True`
        # for an int field.
        if not isinstance(value, bool):
            return Violation(
                constraint.name,
                "type",
                f"field {constraint.name!r} must be a boolean; "
                f"received {type(value).__name__}",
            )
        return None
    if expected == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return Violation(
                constraint.name,
                "type",
                f"field {constraint.name!r} must be an integer; "
                f"received {type(value).__name__} ({value!r})",
            )
        return None
    if expected == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return Violation(
                constraint.name,
                "type",
                f"field {constraint.name!r} must be a number; "
                f"received {type(value).__name__} ({value!r})",
            )
        return None
    # string and timestamp both arrive as strings on the wire. Timestamp
    # PARSING is `records.py`'s job (it owns the typed slot encoding); here we
    # only assert the wire shape, so this module needs no date library.
    if not isinstance(value, str):
        return Violation(
            constraint.name,
            "type",
            f"field {constraint.name!r} must be a string; "
            f"received {type(value).__name__}",
        )
    return None


def check_enum(constraint: FieldConstraint, value: Any) -> Violation | None:
    """Enum membership. The wire schema owns this too — this is the backstop
    for the case where the schema was compiled without the enum, or the model
    returned a value the API let through."""
    if value is None or constraint.enum is None:
        return None
    if value in constraint.enum:
        return None
    allowed = ", ".join(repr(v) for v in constraint.enum)
    return Violation(
        constraint.name,
        "enum",
        f"field {constraint.name!r} must be one of [{allowed}]; "
        f"received {value!r}",
    )


def check_range(constraint: FieldConstraint, value: Any) -> Violation | None:
    """Numeric range. JSON Schema on this API cannot express it (§8)."""
    if value is None:
        return None
    if constraint.minimum is None and constraint.maximum is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None  # A type violation already; do not double-report.
    if constraint.minimum is not None and value < constraint.minimum:
        return Violation(
            constraint.name,
            "range",
            f"field {constraint.name!r} must be >= {constraint.minimum}; "
            f"received {value!r}",
        )
    if constraint.maximum is not None and value > constraint.maximum:
        return Violation(
            constraint.name,
            "range",
            f"field {constraint.name!r} must be <= {constraint.maximum}; "
            f"received {value!r}",
        )
    return None


def check_length(constraint: FieldConstraint, value: Any) -> Violation | None:
    """String length. JSON Schema on this API cannot express it (§8).

    Measured on the RAW value, not the normalized one — the spec declares a
    length over the value that lands, and normalization would under-count.
    """
    if value is None or not isinstance(value, str):
        return None
    if constraint.min_length is None and constraint.max_length is None:
        return None
    n = len(value)
    if constraint.min_length is not None and n < constraint.min_length:
        return Violation(
            constraint.name,
            "length",
            f"field {constraint.name!r} must be at least "
            f"{constraint.min_length} characters; received {n}",
        )
    if constraint.max_length is not None and n > constraint.max_length:
        return Violation(
            constraint.name,
            "length",
            f"field {constraint.name!r} must be at most "
            f"{constraint.max_length} characters; received {n}",
        )
    return None


def verify_quote(
    quote: str,
    landed_text: str | None,
) -> tuple[str, int | None, int | None]:
    """Evidence substring check against LANDED source text.

    Returns `(verify_status, char_start, char_end)`. Offsets are into the
    NORMALIZED landed text (§2.3: "offset into the landed normalized text, not
    the raw document") and are None unless the status is `verified`.

    Three outcomes, and the distinction between the last two is load-bearing:

    - `verified`           — normalized quote is a substring of normalized
                             landed text.
    - `evidence_unverified` — `landed_text` is None. No canonical text exists
                             for this locator. **The function does not pretend
                             to verify.** It is not a pass and must never be
                             counted as one; §4 puts a separate ceiling on it.
    - `verify_failed`      — landed text EXISTS and the quote is not in it.
                             A hallucinated citation. Never silently downgraded
                             to `evidence_unverified` (§2.3) — that downgrade is
                             precisely how a fabricated citation would launder
                             itself into an acceptable bucket.

    The caller passes `landed_text`. This function has no I/O and cannot fetch
    it, which is deliberate: it makes it structurally impossible to validate a
    quote against text the model returned in the same response. That check is
    circular and proves nothing (design §5). The caller must source this from a
    landed model, never from a PDF blob and never from the response.
    """
    if landed_text is None:
        return VerifyStatus.UNVERIFIED, None, None
    needle = normalize_text(quote)
    haystack = normalize_text(landed_text)
    if not needle:
        # An empty quote is a substring of everything. Treating it as verified
        # would let a model cite nothing and pass the evidence obligation.
        return VerifyStatus.FAILED, None, None
    index = haystack.find(needle)
    if index < 0:
        return VerifyStatus.FAILED, None, None
    return VerifyStatus.VERIFIED, index, index + len(needle)


# --------------------------------------------------------------------------
# Whole-cell validation
# --------------------------------------------------------------------------


@dataclass
class ValidatedCell:
    """The outcome for one `(target_row_key, field)`."""

    field: str
    value: Any
    value_status: str
    needs_review: bool
    attempt_count: int
    violations: tuple[Violation, ...] = ()
    evidence_statuses: tuple[str, ...] = ()
    error_code: str | None = None
    error_detail: str | None = None

    @property
    def is_ok(self) -> bool:
        return self.value_status == ValueStatus.OK


def validate_value(
    constraint: FieldConstraint,
    value: Any,
    *,
    evidence_statuses: Sequence[str] = (),
    allow_unverified: bool = True,
) -> list[Violation]:
    """Run every harness-owned check for one field. Returns all violations.

    All checks run — the list is not short-circuited — so a retry names every
    problem at once instead of trading one round trip per violation.

    Evidence policy:
    - any `verify_failed` atom is a violation. §2.3 requires it to propagate to
      the cell's status rather than sit quietly in the evidence table.
    - `evidence_unverified` is a violation only when the spec forbids it. It is
      NOT a hallucination — it is an honest "no canonical text here" — so it
      must not be conflated with `verify_failed`.
    - too few atoms is a violation: `ok` requires >= the spec's minimum (§7.2).
    """
    violations: list[Violation] = []
    for check in (check_type, check_enum, check_range, check_length):
        violation = check(constraint, value)
        if violation is not None:
            violations.append(violation)

    failed = sum(1 for s in evidence_statuses if s == VerifyStatus.FAILED)
    if failed:
        violations.append(
            Violation(
                constraint.name,
                "evidence",
                f"field {constraint.name!r}: {failed} cited quote(s) are not "
                f"present in the landed source text. Cite a verbatim span that "
                f"actually appears in the source, or report the field as not "
                f"stated.",
            )
        )
    if not allow_unverified:
        unverified = sum(
            1 for s in evidence_statuses if s == VerifyStatus.UNVERIFIED
        )
        if unverified:
            violations.append(
                Violation(
                    constraint.name,
                    "evidence",
                    f"field {constraint.name!r}: {unverified} citation(s) "
                    f"could not be verified against landed text, which this "
                    f"spec does not permit.",
                )
            )
    if value is not None and len(evidence_statuses) < constraint.min_evidence:
        violations.append(
            Violation(
                constraint.name,
                "evidence",
                f"field {constraint.name!r} requires at least "
                f"{constraint.min_evidence} evidence citation(s); received "
                f"{len(evidence_statuses)}",
            )
        )
    return violations


def run_with_retry(
    constraint: FieldConstraint,
    attempt: Callable[[tuple[Violation, ...]], tuple[Any, Sequence[str]]],
    *,
    max_validation_retries: int = 2,
    allow_unverified: bool = True,
    absent_sentinel: Any = None,
) -> ValidatedCell:
    """The validation-retry policy (§8). On violation, retry feeding the
    violation text back; on exhaustion return `validation_failed`.

    `attempt` is supplied by the caller and is the ONLY thing here that touches
    a model. It receives the violations from the previous attempt (empty tuple
    on the first) and returns `(value, evidence_statuses)`. Inverting control
    this way is what keeps this module free of `anthropic`, free of network, and
    unit-testable with a plain closure.

    Budget: `max_validation_retries` RETRIES, so `1 + max_validation_retries`
    attempts. This is the validation budget ONLY. Transport retries are a
    separate budget owned by `transport.py` and the two are never conflated —
    a 529 must not consume a correction attempt, and a range violation must not
    consume backoff.

    Exhaustion returns `validation_failed`, NOT `evidence_absent`. They are
    different conditions and the distinction is the point of §3: the model
    answered and was wrong, versus the source is genuinely silent. Collapsing
    them would let a broken spec present as a sparse source.

    The failing value is DISCARDED — `ValidatedCell.value` is None on
    `validation_failed`, per §3's "all five typed value slots are null." The
    violations are retained for triage.
    """
    if max_validation_retries < 0:
        raise SpecError("max_validation_retries must be >= 0")

    violations: tuple[Violation, ...] = ()
    attempts = 0
    for _ in range(max_validation_retries + 1):
        value, evidence_statuses = attempt(violations)
        attempts += 1

        if value is absent_sentinel or value is None:
            # The model reported the source does not state this field. Honest
            # silence — not an error, not a failure, and NOT retried: re-asking
            # a silent source produces a confabulation on attempt two.
            return ValidatedCell(
                field=constraint.name,
                value=None,
                value_status=ValueStatus.EVIDENCE_ABSENT,
                needs_review=constraint.required,
                attempt_count=attempts,
                evidence_statuses=tuple(evidence_statuses),
            )

        found = validate_value(
            constraint,
            value,
            evidence_statuses=evidence_statuses,
            allow_unverified=allow_unverified,
        )
        if not found:
            return ValidatedCell(
                field=constraint.name,
                value=value,
                value_status=ValueStatus.OK,
                needs_review=False,
                attempt_count=attempts,
                evidence_statuses=tuple(evidence_statuses),
            )
        violations = tuple(found)

    return ValidatedCell(
        field=constraint.name,
        value=None,  # Discarded. Never land the value that failed validation.
        value_status=ValueStatus.VALIDATION_FAILED,
        needs_review=True,
        attempt_count=attempts,
        violations=violations,
        evidence_statuses=(),
        error_detail="; ".join(v.message for v in violations),
    )


# --------------------------------------------------------------------------
# The coverage gate (CONTRACT.md §4)
# --------------------------------------------------------------------------


@dataclass
class CoverageReport:
    """What the gate saw. Emitted whether or not the build blocks, so a passing
    run still narrates its degrade share rather than reporting a bare number."""

    total: int = 0
    counts: dict[str, int] = dc_field(default_factory=dict)
    shares: dict[str, float] = dc_field(default_factory=dict)
    unverified_share: float = 0.0
    evidence_total: int = 0
    blocked: bool = False
    reasons: list[str] = dc_field(default_factory=list)

    @property
    def ok_share(self) -> float:
        return self.shares.get(ValueStatus.OK, 0.0)

    def summary(self) -> str:
        parts = [f"{self.total} cells"]
        for status in sorted(self.counts):
            parts.append(
                f"{status}={self.counts[status]} "
                f"({self.shares.get(status, 0.0):.1%})"
            )
        if self.evidence_total:
            parts.append(f"evidence_unverified={self.unverified_share:.1%}")
        return ", ".join(parts)


def evaluate_coverage(
    cells: Iterable[ValidatedCell],
    *,
    max_degrade_share: float | None = None,
    max_error_rate: float | None = None,
    max_absent_share: float | None = None,
    max_unverified_share: float | None = None,
    blocking_error_codes: Mapping[str, str] | None = None,
    raise_on_block: bool = True,
) -> CoverageReport:
    """Decide whether the run may land. §4's table, evaluated after mapping
    completes and BEFORE landing.

    The boundary: **systemic failure blocks; row-level absence does not.**

    - `evidence_absent`    -> never blocks on its own. The source is silent;
                              that is a finding, not a fault.
    - `validation_failed`  -> blocks only past `max_degrade_share`. Below it,
                              "the harness caught it" is working as designed;
                              above it, the spec does not work.
    - `skipped`            -> ANY occurrence blocks. The run did not complete,
                              and landing a partial run as complete is the
                              coverage lie §3 added this status to prevent.
    - systemic `error_code` -> ANY occurrence blocks (credential_missing,
                              dependency_missing, schema_reject). One missing
                              credential means every cell was unattempted.
    - transport/refusal errors -> block past `max_error_rate` only.
    - ZERO `ok` cells      -> ANY such run blocks, unconditionally. See below.

    **Thresholds have no defaults.** CONTRACT.md open question 1 is unresolved,
    and its stated inclination is "no default — spec must declare", because a
    wrong default is worse than an absent one: too loose makes §4 decorative,
    too tight makes every first run block. So `None` here means "no ceiling
    declared" and that dimension does not block.

    **The zero-`ok` floor.** Thresholds-have-no-defaults collides with design
    §4's "a 100%-sentinel green build must be impossible": a spec that declares
    no ceilings, or declares `max_degrade_share=1.0`, would otherwise land a run
    in which EVERY cell failed validation and not one usable value exists. Both
    are reachable — the first is the default posture for a first run, the second
    is what a frustrated author writes to get past a red build. So the floor is
    not threshold-governed: a run with zero `ok` cells always blocks, exactly as
    a run with zero cells does, and for the same reason. "0 of 0 degraded" and
    "100% degraded but the ceiling was 100%" are the same lie in different
    clothes.

    This deliberately does NOT reach for a share — `min_ok_share` would be
    another undefaulted threshold, and open question 1 is precisely the argument
    that we cannot pick its value yet. A floor at *zero* needs no calibration:
    no population, however sparse, justifies landing a governed model in which
    nothing was successfully mapped.

    One accepted consequence: a genuinely, entirely silent source (every cell
    honestly `evidence_absent`) also blocks. That is the intended reading. Such
    a run has produced no data, and the author should learn that from a blocked
    build rather than from an empty table downstream — and if the silence is
    real and expected, that is a finding to record, not a model to land.
    """
    cells = list(cells)
    report = CoverageReport(total=len(cells))
    if not cells:
        # Zero cells is not a clean pass. A mapper that produced nothing has
        # either an empty input or a broken adapter, and "0 of 0 degraded"
        # trivially satisfies every share threshold.
        report.blocked = True
        report.reasons.append(
            "no cells were produced; an empty result cannot be validated as "
            "complete coverage"
        )
        if raise_on_block:
            raise CoverageBlocked(report.reasons[0], report)
        return report

    for cell in cells:
        report.counts[cell.value_status] = (
            report.counts.get(cell.value_status, 0) + 1
        )
    total = report.total
    report.shares = {k: v / total for k, v in report.counts.items()}

    evidence = [s for cell in cells for s in cell.evidence_statuses]
    report.evidence_total = len(evidence)
    if evidence:
        report.unverified_share = (
            sum(1 for s in evidence if s == VerifyStatus.UNVERIFIED)
            / len(evidence)
        )

    # -- Unconditional blocks: systemic, never threshold-governed. -----------
    # The zero-`ok` floor. Placed FIRST because it is the broadest statement of
    # the same rule the empty-input guard above makes: a run that mapped nothing
    # usable cannot land, no matter what ceilings the spec did or did not
    # declare. Without it, `max_degrade_share=1.0` (or no ceilings at all) lands
    # a governed model containing zero values — design §4's forbidden
    # 100%-sentinel green build.
    if not report.counts.get(ValueStatus.OK, 0):
        report.reasons.append(
            f"no cell reached status 'ok' ({total} cell(s), "
            f"{report.summary()}); a run that mapped no usable value cannot "
            f"land regardless of declared thresholds"
        )

    skipped = report.counts.get(ValueStatus.SKIPPED, 0)
    if skipped:
        report.reasons.append(
            f"{skipped} cell(s) were never dispatched (skipped); the run did "
            f"not complete and must not land as if it had"
        )

    systemic = dict(
        blocking_error_codes
        or {
            "credential_missing": "a required credential was not available",
            "dependency_missing": "a required dependency was not available",
            "schema_reject": "the API rejected the compiled wire schema",
        }
    )
    seen: dict[str, int] = {}
    for cell in cells:
        if cell.value_status == ValueStatus.ERROR and cell.error_code in systemic:
            seen[cell.error_code] = seen.get(cell.error_code, 0) + 1
    for code, count in sorted(seen.items()):
        report.reasons.append(
            f"{count} cell(s) failed with systemic error {code!r}: "
            f"{systemic[code]}"
        )

    # -- Threshold-governed blocks. -----------------------------------------
    def _gate(share: float, ceiling: float | None, label: str) -> None:
        if ceiling is not None and share > ceiling:
            report.reasons.append(
                f"{label} share {share:.1%} exceeds the declared ceiling "
                f"{ceiling:.1%}"
            )

    _gate(
        report.shares.get(ValueStatus.VALIDATION_FAILED, 0.0),
        max_degrade_share,
        "validation_failed",
    )
    _gate(
        report.shares.get(ValueStatus.EVIDENCE_ABSENT, 0.0),
        max_absent_share,
        "evidence_absent",
    )
    # Only NON-systemic errors are rate-governed; systemic ones already blocked
    # unconditionally above and must not be double-counted into a rate that a
    # loose ceiling could then wave through.
    non_systemic_errors = sum(
        1
        for cell in cells
        if cell.value_status == ValueStatus.ERROR
        and cell.error_code not in systemic
    )
    _gate(non_systemic_errors / total, max_error_rate, "error")
    if report.evidence_total:
        _gate(
            report.unverified_share, max_unverified_share, "evidence_unverified"
        )

    report.blocked = bool(report.reasons)
    if report.blocked and raise_on_block:
        raise CoverageBlocked(
            "build blocked: " + "; ".join(report.reasons), report
        )
    return report

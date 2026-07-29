"""Deterministic resolver: proposals + reviews + evidence -> effective values.

CONTRACT.md §6 (resolution order) and §7 (consistency asserts).

The inversion this module implements
------------------------------------
Long-form mapped-value records are the contract; **the wide model is a
projection resolved from them** (design §2). So this module does not "join a
sidecar onto a table" — it resolves each `(target_row_key, field)` cell once and
emits the wide row and its provenance *from the same in-memory objects*.
`Resolution.wide_rows` and `Resolution.provenance` are two views of one bundle,
never two passes. That is what makes the bijection assert in §7 meaningful
rather than a restatement of a join key.

Confirmation binding
--------------------
A review binds to `(target_row_key, field, bound_value_hash,
bound_input_snapshot_id, bound_mapper_spec_id)`. It applies **only** when all
three bound components still match the current proposal. A changed proposal, a
changed source, or a changed spec makes it `stale`: it does not apply, it is
never deleted, and it is never silently reapplied to a value nobody approved.
Staleness is *reported*, with a `stale_reason` naming which component moved,
because a reviewer whose work came unbound needs to see why rather than find
their confirmations quietly gone.

The one asymmetry: an `overridden` review with a null `bound_value_hash` binds
on input + spec only. A human overriding a cell the model never produced has no
value hash to bind to, and demanding one would make "human fills the gap"
unrepresentable.

Human override precedence
-------------------------
A valid `overridden` review beats any model proposal, unconditionally. The
proposal is retained in provenance — it is the record of what the model said —
but it does not reach the wide row.

Purity
------
Nothing here calls a model, opens a socket, or reads a file. Given the same
three record sets it returns the same resolution every time, which is what lets
`resolve` run in a test with no credentials and no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .errors import FieldMapperError
from .identity import value_hash
from .records import (
    EffectiveSource,
    MapperEvidence,
    MapperProposal,
    MapperReview,
    StaleReason,
    TypedValue,
    ValueStatus,
    ValueType,
    Verdict,
)

__all__ = [
    "EffectiveValue",
    "StaleReview",
    "Resolution",
    "BijectionError",
    "ResolverInputError",
    "resolve",
]


class BijectionError(FieldMapperError):
    """A structural assert from §7 failed. Blocks the build (§4).

    Structural, therefore never a landed row with a `blocked` status: a blocked
    build lands nothing, because a partially-landed governed model is worse than
    no model.
    """


class ResolverInputError(FieldMapperError):
    """The record sets handed in are malformed before resolution can begin."""


# --------------------------------------------------------------------------
# Output records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StaleReview:
    """A review that no longer binds, and exactly which components moved."""

    review_id: str
    target_row_key: str
    field: str
    verdict: Verdict
    reviewer: str
    stale_reasons: tuple[StaleReason, ...]

    @property
    def stale_reason(self) -> StaleReason:
        """Primary reason, for a single-column sidecar rendering.

        Ordered spec > input > value: a spec change invalidates the most cells
        at once and is the most actionable thing to surface first. The full set
        stays available in `stale_reasons` — collapsing to one reason is a
        display concern, not a loss of the finding.
        """
        for reason in (
            StaleReason.SPEC_CHANGED,
            StaleReason.INPUT_CHANGED,
            StaleReason.VALUE_CHANGED,
        ):
            if reason in self.stale_reasons:
                return reason
        return self.stale_reasons[0]


@dataclass(frozen=True)
class EffectiveValue:
    """One resolved cell — the unit both the wide row and provenance derive from."""

    target_row_key: str
    field: str
    typed: TypedValue
    value_status: ValueStatus
    effective_source: EffectiveSource
    needs_review: bool
    evidence_count: int
    observation_id: str
    value_hash: str
    reviewer: str | None = None
    review_id: str | None = None
    proposal_value: Any = None
    """What the model proposed, retained even when a human override won."""
    proposal_value_hash: str | None = None
    error_code: str | None = None

    @property
    def value(self) -> Any:
        return self.typed.value

    @property
    def is_governed(self) -> bool:
        """Whether this cell carries a value into the governed wide model.

        Only `ok` cells do. Every other status lands all-null typed slots and is
        excluded mechanically from default metrics (§3) — the cell still exists
        in the projection, it just carries no value.
        """
        return self.value_status is ValueStatus.OK


@dataclass(frozen=True)
class Resolution:
    """Wide projection + provenance sidecar, built from one bundle."""

    effective: tuple[EffectiveValue, ...]
    stale_reviews: tuple[StaleReview, ...]
    evidence: tuple[MapperEvidence, ...]
    row_keys: tuple[str, ...]
    fields: tuple[str, ...]
    min_evidence_per_ok_cell: int = 0

    # -- projections -------------------------------------------------------

    @property
    def wide_rows(self) -> tuple[dict[str, Any], ...]:
        """The wide target model: one dict per `target_row_key`.

        A derived projection, never the authority. Cells in a non-`ok` status
        carry `None` — never a string sentinel, which in a numeric column is the
        exact defect design §4 forbids.
        """
        by_key: dict[str, dict[str, Any]] = {
            key: {"target_row_key": key, **{f: None for f in self.fields}}
            for key in self.row_keys
        }
        for item in self.effective:
            by_key[item.target_row_key][item.field] = (
                item.value if item.is_governed else None
            )
        return tuple(by_key[key] for key in self.row_keys)

    @property
    def provenance(self) -> tuple[dict[str, Any], ...]:
        """The sidecar: one row per cell, carrying `value_hash` (§7.3)."""
        return tuple(
            {
                "target_row_key": item.target_row_key,
                "field": item.field,
                "value_hash": item.value_hash,
                "effective_source": item.effective_source.value,
                "value_status": item.value_status.value,
                "observation_id": item.observation_id,
                "evidence_count": item.evidence_count,
                "needs_review": item.needs_review,
                "reviewer": item.reviewer,
                "review_id": item.review_id,
                "proposal_value_hash": item.proposal_value_hash,
                "error_code": item.error_code,
            }
            for item in self.effective
        )

    @property
    def stale_review_rows(self) -> tuple[dict[str, Any], ...]:
        """Stale reviews as landable rows, so "what came unbound" is queryable."""
        return tuple(
            {
                "review_id": s.review_id,
                "target_row_key": s.target_row_key,
                "field": s.field,
                "verdict": s.verdict.value,
                "reviewer": s.reviewer,
                "stale_reason": s.stale_reason.value,
                "stale_reasons": ",".join(r.value for r in s.stale_reasons),
            }
            for s in self.stale_reviews
        )

    # -- status accounting -------------------------------------------------

    def status_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in ValueStatus}
        for item in self.effective:
            counts[item.value_status.value] += 1
        return counts

    def share(self, status: ValueStatus) -> float:
        """Share of cells in `status`. Feeds the §4 threshold gates."""
        if not self.effective:
            return 0.0
        hits = sum(1 for i in self.effective if i.value_status is status)
        return hits / len(self.effective)

    # -- §7 asserts --------------------------------------------------------

    def assert_bijection(self) -> None:
        """CONTRACT.md §7.1, §7.2, §7.5, §7.6. Any failure blocks the build.

        Checks, in order:

        1. **Bijection** — every governed wide cell maps to exactly one
           effective record and back. No orphans in either direction.
        2. **Key uniqueness** — one effective record per `(row_key, field)`;
           unique `evidence_ordinal` within a cell.
        3. **Evidence completeness** — every `ok` cell carries at least the
           spec's minimum atoms; every evidence row resolves to a real cell.
        4. **Status/value coherence** — non-`ok` implies all slots null;
           `error_code` non-null iff status is `error`.

        Value-hash agreement (§7.3) is `assert_value_hashes`, kept separate
        because it re-derives digests and a caller may want the structural
        check without the hashing cost.
        """
        row_key_set = set(self.row_keys)
        field_set = set(self.fields)

        seen: set[tuple[str, str]] = set()
        for item in self.effective:
            cell = (item.target_row_key, item.field)
            if cell in seen:
                raise BijectionError(
                    f"duplicate effective record for {cell!r}; row identity is "
                    "under-determined, the failure design §3 exists to catch"
                )
            seen.add(cell)
            if item.target_row_key not in row_key_set:
                raise BijectionError(
                    f"orphan effective record {cell!r}: no such target_row_key"
                )
            if item.field not in field_set:
                raise BijectionError(
                    f"orphan effective record {cell!r}: field not declared by the spec"
                )

        expected = {(key, f) for key in self.row_keys for f in self.fields}
        missing = expected - seen
        if missing:
            raise BijectionError(
                f"{len(missing)} wide cell(s) have no effective record, e.g. "
                f"{sorted(missing)[:3]!r}"
            )

        # Evidence must resolve to a real cell, with unique ordinals within it.
        counts: dict[tuple[str, str], int] = {}
        ordinals: dict[tuple[str, str], set[int]] = {}
        for row in self.evidence:
            cell = (row.target_row_key, row.field)
            if cell not in seen:
                raise BijectionError(
                    f"orphan evidence row for {cell!r}: no matching effective record"
                )
            counts[cell] = counts.get(cell, 0) + 1
            bucket = ordinals.setdefault(cell, set())
            if row.evidence_ordinal in bucket:
                raise BijectionError(
                    f"duplicate evidence_ordinal {row.evidence_ordinal} for {cell!r}"
                )
            bucket.add(row.evidence_ordinal)

        for item in self.effective:
            cell = (item.target_row_key, item.field)
            if item.value_status is ValueStatus.OK:
                have = counts.get(cell, 0)
                if have < self.min_evidence_per_ok_cell:
                    raise BijectionError(
                        f"cell {cell!r} is ok with {have} evidence atom(s); the "
                        f"spec requires at least {self.min_evidence_per_ok_cell}"
                    )
            elif item.value is not None:
                raise BijectionError(
                    f"cell {cell!r} has status {item.value_status.value} but a "
                    "non-null value; every non-ok status lands all slots null"
                )

            has_code = item.error_code is not None
            is_error = item.value_status is ValueStatus.ERROR
            if has_code != is_error:
                raise BijectionError(
                    f"cell {cell!r}: error_code is non-null iff value_status is "
                    f"'error' (status={item.value_status.value}, "
                    f"error_code={item.error_code!r})"
                )

    def assert_value_hashes(self) -> None:
        """CONTRACT.md §7.3 — the sidecar's `value_hash` matches the wide value.

        Catches the class where the projection and the provenance drift: a wide
        row showing one value while the sidecar attests to the hash of another.
        Recomputed from the effective record's own typed value using the same
        canonical encoder the proposals used.
        """
        for item in self.effective:
            recomputed = value_hash(item.typed.value_type.value, item.typed.value)
            if recomputed != item.value_hash:
                raise BijectionError(
                    f"value_hash disagreement for "
                    f"{(item.target_row_key, item.field)!r}: sidecar carries "
                    f"{item.value_hash!r}, the wide value hashes to {recomputed!r}"
                )

    def assert_cardinality(self, *, min_rows: int, max_rows: int) -> None:
        """CONTRACT.md §7.4.

        Bounds the *emitted row count* against the spec's declared cardinality.
        Deliberately **not** an "output count == source count" assert: that is
        unsatisfiable for an N->M mapper, and is the Tier-1 assert
        `derived-models.md` needs amending for.
        """
        count = len(self.row_keys)
        if count < min_rows or count > max_rows:
            raise BijectionError(
                f"emitted {count} target row(s), outside the spec's declared "
                f"cardinality [{min_rows}, {max_rows}]"
            )


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def _binding_failures(
    review: MapperReview, proposal: MapperProposal | None
) -> list[StaleReason]:
    """Which binding components moved. Empty list means the review still applies."""
    reasons: list[StaleReason] = []

    if proposal is None:
        # No proposal this run. Only a null-bound override survives — the
        # "human fills a gap the model never filled" case (§2.2). Anything else
        # has lost the value it was bound to.
        if not (
            review.verdict is Verdict.OVERRIDDEN and review.bound_value_hash is None
        ):
            reasons.append(StaleReason.VALUE_CHANGED)
        return reasons

    if review.bound_input_snapshot_id != proposal.input_snapshot_id:
        reasons.append(StaleReason.INPUT_CHANGED)
    if review.bound_mapper_spec_id != proposal.mapper_spec_id:
        reasons.append(StaleReason.SPEC_CHANGED)

    if review.bound_value_hash is None:
        # `MapperReview.__post_init__` already rejects a null binding on any
        # non-override verdict, so reaching here with one means the record was
        # constructed by some path that bypassed validation. Treat it as
        # unbound rather than trusting it.
        if review.verdict is not Verdict.OVERRIDDEN:
            reasons.append(StaleReason.VALUE_CHANGED)
    elif review.bound_value_hash != proposal.value_hash:
        reasons.append(StaleReason.VALUE_CHANGED)

    return reasons


def _review_sort_key(review: MapperReview) -> tuple[str, str]:
    """Latest `reviewed_at` wins; ties break on `review_id` lexicographically.

    Deterministic and arbitrary, and documented as such in §6. `reviewed_at` is
    coerced to text so a mix of `datetime` objects and ISO strings from a
    hand-edited CSV cannot raise a comparison `TypeError` mid-resolve — ISO-8601
    sorts correctly as text, which is why the column is specified that way.
    """
    return (str(review.reviewed_at), review.review_id)


def resolve(
    proposals: Iterable[MapperProposal],
    reviews: Iterable[MapperReview],
    evidence: Iterable[MapperEvidence] | None = None,
    *,
    fields: Sequence[str],
    row_keys: Sequence[str] | None = None,
    min_evidence_per_ok_cell: int = 0,
) -> Resolution:
    """Resolve proposals + reviews + evidence into effective values.

    A single pass over one in-memory bundle. The wide rows and the provenance
    sidecar both come out of the returned `Resolution`, built from the same
    `EffectiveValue` objects — never joined afterwards, which is the drift §7.3
    exists to catch.

    `fields` is the spec's declared target-field list and is the authority on
    which columns the wide model has, so a field the model never returned still
    appears as a cell rather than silently vanishing from the projection.

    `evidence` defaults to the atoms already carried on each proposal, since
    `MapperProposal` owns its evidence list — there is deliberately no path that
    resolves proposals without their evidence. Pass it explicitly only when the
    atoms were landed separately and read back.

    `row_keys` defaults to the sorted distinct keys across proposals plus any
    null-bound override. Sorting is lexicographic on the content-derived key,
    stable across runs; `emission_ordinal` is display-only and orders nothing
    here.
    """
    proposal_list = list(proposals)
    review_list = list(reviews)

    # §2.1: duplicate emission is a hard failure, never last-write-wins.
    by_cell: dict[tuple[str, str], MapperProposal] = {}
    for proposal in proposal_list:
        if proposal.key in by_cell:
            raise ResolverInputError(
                f"duplicate proposal for {proposal.key!r}; duplicate emission "
                "means the spec's row identity is under-determined (design §3), "
                "which is a hard failure rather than a last-write-wins"
            )
        by_cell[proposal.key] = proposal

    if evidence is None:
        evidence_list = [atom for p in proposal_list for atom in p.evidence]
    else:
        evidence_list = list(evidence)

    reviews_by_cell: dict[tuple[str, str], list[MapperReview]] = {}
    for review in review_list:
        reviews_by_cell.setdefault(review.key, []).append(review)

    evidence_counts: dict[tuple[str, str], int] = {}
    for atom in evidence_list:
        cell = (atom.target_row_key, atom.field)
        evidence_counts[cell] = evidence_counts.get(cell, 0) + 1

    if row_keys is None:
        keys = {p.target_row_key for p in proposal_list}
        # A null-bound override introduces a row the model never proposed.
        for review in review_list:
            if review.verdict is Verdict.OVERRIDDEN and review.bound_value_hash is None:
                keys.add(review.target_row_key)
        ordered_keys = tuple(sorted(keys))
    else:
        ordered_keys = tuple(row_keys)

    ordered_fields = tuple(fields)

    effective: list[EffectiveValue] = []
    stale: list[StaleReview] = []

    for row_key in ordered_keys:
        for field_name in ordered_fields:
            cell = (row_key, field_name)
            proposal = by_cell.get(cell)

            valid: list[MapperReview] = []
            for review in reviews_by_cell.get(cell, []):
                reasons = _binding_failures(review, proposal)
                if reasons:
                    stale.append(
                        StaleReview(
                            review_id=review.review_id,
                            target_row_key=review.target_row_key,
                            field=review.field,
                            verdict=review.verdict,
                            reviewer=review.reviewer,
                            stale_reasons=tuple(reasons),
                        )
                    )
                else:
                    valid.append(review)

            winner = max(valid, key=_review_sort_key) if valid else None
            effective.append(
                _resolve_cell(
                    row_key=row_key,
                    field_name=field_name,
                    proposal=proposal,
                    review=winner,
                    evidence_count=evidence_counts.get(cell, 0),
                )
            )

    return Resolution(
        effective=tuple(effective),
        stale_reviews=tuple(stale),
        evidence=tuple(evidence_list),
        row_keys=ordered_keys,
        fields=ordered_fields,
        min_evidence_per_ok_cell=min_evidence_per_ok_cell,
    )


def _resolve_cell(
    *,
    row_key: str,
    field_name: str,
    proposal: MapperProposal | None,
    review: MapperReview | None,
    evidence_count: int,
) -> EffectiveValue:
    """Apply §6 steps 3-6 to one cell. Pure; no I/O, no model call."""
    proposal_value = proposal.typed.value if proposal else None
    proposal_hash = proposal.value_hash if proposal else None
    observation_id = proposal.observation_id if proposal else ""

    # Step 3: human override wins over any model proposal, unconditionally.
    if review is not None and review.verdict is Verdict.OVERRIDDEN:
        assert review.override is not None  # guaranteed by MapperReview
        return EffectiveValue(
            target_row_key=row_key,
            field=field_name,
            typed=review.override,
            # An override is an asserted value: `ok` because a human stated it,
            # not because a model passed the harness's checks.
            value_status=ValueStatus.OK,
            effective_source=EffectiveSource.HUMAN_OVERRIDE,
            needs_review=False,
            evidence_count=evidence_count,
            observation_id=observation_id,
            value_hash=review.override.hash,
            reviewer=review.reviewer,
            review_id=review.review_id,
            proposal_value=proposal_value,
            proposal_value_hash=proposal_hash,
            error_code=None,
        )

    # Step 5: a rejection nulls the cell regardless of what the model proposed.
    if review is not None and review.verdict is Verdict.REJECTED:
        null_typed = TypedValue(
            proposal.typed.value_type if proposal else ValueType.STRING, None
        )
        return EffectiveValue(
            target_row_key=row_key,
            field=field_name,
            typed=null_typed,
            value_status=ValueStatus.VALIDATION_FAILED,
            effective_source=EffectiveSource.HUMAN_REJECTED,
            needs_review=False,
            evidence_count=evidence_count,
            observation_id=observation_id,
            value_hash=null_typed.hash,
            reviewer=review.reviewer,
            review_id=review.review_id,
            proposal_value=proposal_value,
            proposal_value_hash=proposal_hash,
            error_code=None,
        )

    # No proposal and no override: the cell was never produced. `skipped` is the
    # honest status — it blocks the build (§4) rather than passing as a silent
    # `evidence_absent`, which would be indistinguishable from a silent source.
    if proposal is None:
        null_typed = TypedValue(ValueType.STRING, None)
        return EffectiveValue(
            target_row_key=row_key,
            field=field_name,
            typed=null_typed,
            value_status=ValueStatus.SKIPPED,
            effective_source=EffectiveSource.MODEL_PROPOSED,
            needs_review=True,
            evidence_count=evidence_count,
            observation_id="",
            value_hash=null_typed.hash,
            error_code=None,
        )

    # Step 4 (confirmed) / step 6 (no valid review): the proposal's own value and
    # status carry through unchanged. A confirmation does not upgrade a failed
    # cell — it records that a human looked at what the model produced.
    if review is not None and review.verdict is Verdict.CONFIRMED:
        source = EffectiveSource.MODEL_CONFIRMED
        needs_review = False
        reviewer: str | None = review.reviewer
        review_id: str | None = review.review_id
    else:
        source = EffectiveSource.MODEL_PROPOSED
        needs_review = proposal.needs_review
        reviewer, review_id = None, None

    return EffectiveValue(
        target_row_key=row_key,
        field=field_name,
        typed=proposal.typed,
        value_status=proposal.value_status,
        effective_source=source,
        needs_review=needs_review,
        evidence_count=evidence_count,
        observation_id=proposal.observation_id,
        value_hash=proposal.value_hash,
        reviewer=reviewer,
        review_id=review_id,
        proposal_value=proposal_value,
        proposal_value_hash=proposal_hash,
        error_code=proposal.error_code,
    )

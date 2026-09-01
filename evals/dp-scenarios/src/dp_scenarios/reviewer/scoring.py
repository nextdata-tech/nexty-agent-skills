"""Claim-level recall and precision scoring for seeded reviewer defects."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import (
    AdjudicationState,
    ReviewLedger,
    ReviewRun,
    ReviewScore,
    Ratio,
    SeededDefect,
    _qualification_for,
)


def _resolve_declarations(value: object) -> tuple[bool, object]:
    """Return whether a declaration was found and its candidate value."""

    if value is None:
        return False, ()
    if isinstance(value, Mapping):
        for key in ("seeded_defects", "review_defects", "defects"):
            if key in value:
                return True, value[key]
        gates = value.get("gates")
        if isinstance(gates, Mapping) and "construction" in gates:
            return _resolve_declarations(gates["construction"])
        return False, ()
    for attribute in ("seeded_defects", "review_defects"):
        if hasattr(value, attribute):
            return True, getattr(value, attribute)
    gates = getattr(value, "gates", None)
    if isinstance(gates, Mapping) and "construction" in gates:
        settings = getattr(gates["construction"], "settings", gates["construction"])
        return _resolve_declarations(settings)
    return True, value


def _declarations(value: object) -> object:
    """Resolve an explicit defect declaration without using fixture plants."""

    _examined, candidate = _resolve_declarations(value)
    return candidate


def normalize_seeded_defects(value: object) -> tuple[SeededDefect, ...]:
    """Normalize scenario-declared defect ids in declaration order."""

    candidate = _declarations(value)
    if isinstance(candidate, (str, Mapping, SeededDefect)):
        candidate = (candidate,)
    if isinstance(candidate, (str, bytes, bytearray)) or not isinstance(candidate, Iterable):
        raise TypeError("seeded defects must be a sequence of ids or declarations")
    items = tuple(candidate)
    if isinstance(candidate, (set, frozenset)):
        items = tuple(sorted(items, key=str))
    result: list[SeededDefect] = []
    for item in items:
        defect = item if isinstance(item, SeededDefect) else SeededDefect.from_value(item)
        if defect.defect_id not in {existing.defect_id for existing in result}:
            result.append(defect)
    return tuple(result)


def score_review(
    review: ReviewRun | ReviewLedger,
    seeded_defects: object = None,
) -> ReviewScore:
    """Score only adjudicated claims against the scenario's planted defects.

    Recall is defect-level (unique planted defects found).  Precision is
    claim-level over claims the builder actually adjudicated.  Unadjudicated
    claims are reported separately and are never converted into rejections.
    """

    if isinstance(review, ReviewRun):
        ledger = ReviewLedger.from_run(review)
    elif isinstance(review, ReviewLedger):
        ledger = review
    else:
        from .gate import coerce_review_ledger

        ledger = coerce_review_ledger(review)
    declaration_examined, declaration_value = _resolve_declarations(seeded_defects)
    declared = normalize_seeded_defects(declaration_value) if declaration_examined else ()
    planted = tuple(defect.defect_id for defect in declared)
    planted_set = set(planted)
    found: set[str] = set()
    true_positive_claims = 0
    claims_about_nothing = 0
    unadjudicated = 0

    for entry in ledger.entries:
        status = entry.adjudication.status
        if status is AdjudicationState.UNADJUDICATED:
            unadjudicated += 1
            continue
        if status is AdjudicationState.REJECTED_WITH_CITATION:
            claims_about_nothing += 1
            continue
        matched = set(entry.adjudication.defect_ids) & planted_set
        if matched:
            found.update(matched)
            true_positive_claims += 1
        else:
            # An upheld claim with no declared planted defect is a false
            # positive for this seeded-defect measurement, even if it could
            # describe an unseeded real problem.
            claims_about_nothing += 1

    found_ordered = tuple(defect_id for defect_id in planted if defect_id in found)
    missed = tuple(defect_id for defect_id in planted if defect_id not in found)
    examined = ledger.examined and declaration_examined
    qualification = _qualification_for(examined)
    return ReviewScore(
        examined=examined,
        qualification=qualification,
        declaration_examined=declaration_examined,
        planted_defects=planted,
        found_defects=found_ordered,
        missed_defects=missed,
        true_positive_claims=true_positive_claims,
        claims_about_nothing_planted=claims_about_nothing,
        unadjudicated_claims=unadjudicated,
        recall_ratio=Ratio(len(found_ordered), len(planted), qualification),
        precision_ratio=Ratio(
            true_positive_claims,
            true_positive_claims + claims_about_nothing,
            qualification,
        ),
    )


__all__ = ["normalize_seeded_defects", "score_review"]

"""Per-slot F1 for the semantic query the agent built.

A ``run_semantic_query`` selection decomposes into named SLOTS — ``metric``,
``dimensions``, ``filters``, and the implied ``grain``. Row-equality (the
deterministic-EX lane) tells you whether the final answer was right; slot-F1
tells you HOW the query was shaped and WHERE it diverged, which is the signal a
skill pack is supposed to move (right dimensions, right grain) even on questions
whose rows happen to coincide.

For each slot we compute set F1 of the agent's selection vs the gold selection:

    precision = |pred ∩ gold| / |pred|
    recall    = |pred ∩ gold| / |gold|
    f1        = 2·p·r / (p + r)

with the empty-vs-empty convention F1 = 1.0 (both sides selected nothing for
that slot ⇒ perfect), and F1 = 0.0 when exactly one side is empty. The overall
score is the mean of the per-slot F1s, so a WRONG DIMENSION drops the score even
when the metric is right.

``grain`` is derived from the dimension set (the group-by grain a semantic query
runs at): same dimensions ⇒ same grain. It is scored as an exact-match slot
(1.0 / 0.0) so a query at the wrong grain is penalized as one whole miss on top
of the per-dimension F1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

SLOTS = ("metric", "dimensions", "filters", "grain")


@dataclass(frozen=True)
class Selection:
    """A normalized slot view of one semantic-query selection (pred or gold)."""

    metric: frozenset[str]
    dimensions: frozenset[str]
    filters: frozenset[str]

    @property
    def grain(self) -> frozenset[str]:
        # Group-by grain == the dimension set the query runs at.
        return self.dimensions


def _norm_tokens(vals: Iterable[Any] | None) -> frozenset[str]:
    """Case/whitespace-insensitive token set (slot names compare name-blind)."""
    out: set[str] = set()
    for v in vals or []:
        s = str(v).strip().lower()
        if s:
            out.add(s)
    return frozenset(out)


def _norm_filters(filters: Iterable[Any] | None) -> frozenset[str]:
    """Canonicalize filters to comparable tokens.

    A filter is a dict (``{field, op, value}``-ish) or a bare string. Dicts are
    reduced to a stable ``field op value`` token so two structurally equal
    filters compare equal regardless of key order; bare strings pass through
    lowercased.
    """
    out: set[str] = set()
    for f in filters or []:
        if isinstance(f, dict):
            field = str(f.get("field") or f.get("dimension") or f.get("name") or "")
            op = str(f.get("op") or f.get("operator") or "=")
            value = f.get("value")
            token = f"{field}|{op}|{value}".strip().lower()
        else:
            token = str(f).strip().lower()
        if token:
            out.add(token)
    return frozenset(out)


def selection_of(
    *,
    measures: Iterable[Any] | None = None,
    dimensions: Iterable[Any] | None = None,
    filters: Iterable[Any] | None = None,
) -> Selection:
    """Build a normalized ``Selection`` from raw query args or a gold spec."""
    return Selection(
        metric=_norm_tokens(measures),
        dimensions=_norm_tokens(dimensions),
        filters=_norm_filters(filters),
    )


def _set_f1(pred: frozenset[str], gold: frozenset[str]) -> float:
    """Set F1 with the empty-vs-empty = 1.0 convention."""
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    inter = len(pred & gold)
    if inter == 0:
        return 0.0
    precision = inter / len(pred)
    recall = inter / len(gold)
    return 2 * precision * recall / (precision + recall)


def slot_f1s(pred: Selection, gold: Selection) -> dict[str, float]:
    """Per-slot F1 for every slot in ``SLOTS``.

    ``grain`` is exact-match (1.0 iff the dimension sets are identical), the
    others are set F1. A wrong dimension therefore hits BOTH ``dimensions``
    (partial F1) and ``grain`` (0.0), which is the intended double penalty for
    running at the wrong grain.
    """
    return {
        "metric": _set_f1(pred.metric, gold.metric),
        "dimensions": _set_f1(pred.dimensions, gold.dimensions),
        "filters": _set_f1(pred.filters, gold.filters),
        "grain": 1.0 if pred.grain == gold.grain else 0.0,
    }


def overall_f1(pred: Selection, gold: Selection) -> float:
    """Mean of the per-slot F1s — the single slot-match score for a query."""
    per = slot_f1s(pred, gold)
    return sum(per.values()) / len(per)


def ema(values: list[float], *, alpha: float = 0.5) -> float:
    """Exponential moving average over an ordered list of per-query scores.

    When an agent issues several ``run_semantic_query`` calls before answering,
    the LAST query is the one it stands behind, so later queries weigh more. EMA
    with ``alpha=0.5`` gives a smooth "converged toward the right shape" score
    that still rewards a late correction. Empty input ⇒ 0.0.
    """
    if not values:
        return 0.0
    acc = values[0]
    for v in values[1:]:
        acc = alpha * v + (1 - alpha) * acc
    return acc

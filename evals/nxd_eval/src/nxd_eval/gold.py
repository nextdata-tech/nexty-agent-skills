"""Frozen-oracle gold records for deterministic execution-accuracy.

An ``answer`` case scores by comparing the agent's returned rows to a gold
row-set. This module is the authoring surface for those gold records; the actual
set/multiset comparison is the ``_ex_core.score`` core this package owns,
imported by the scorer layer — NOT re-implemented here, so there is one
definition of what "PASS" means.

Two authoring forms, one record shape:

* ``gold.rows(id, [{...}, ...])`` — pin an explicit frozen row-set inline.
* ``gold.query(id, measures=[...], group_by=[...])`` — describe the intended
  semantic query; the frozen rows are attached later from a freeze run. This
  keeps a record's *intent* legible even before its rows are frozen.

``gold(records, frozen_path=...)`` assembles a ``{gold_id: record}`` map and, if
given a freeze JSON, injects each record's frozen rows — delegating the row
*shape* remap to the cross-DP ``load_gold`` so the on-disk freeze format stays
identical to the PoC's.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Equality modes understood by the deterministic-EX core (``_ex_core.score``):
# "set" = DISTINCT-row set equality, "multiset" = row multiplicity matters.
SET = "set"
MULTISET = "multiset"


def _record(
    gold_id: str,
    *,
    rows: list[dict] | None = None,
    measures: list[str] | None = None,
    group_by: list[str] | None = None,
    equality_mode: str = SET,
) -> dict[str, Any]:
    """One gold record in the scoring shape.

    ``rows`` is the frozen oracle row-set (may be ``None`` when only intent is
    pinned, to be filled from a freeze file). ``measures`` / ``group_by``
    capture the intended semantic query for legibility and for a future freeze
    step. ``equality_mode`` selects set vs. multiset comparison in the scorer.
    """
    if equality_mode not in (SET, MULTISET):
        raise ValueError(
            f"gold {gold_id!r}: equality_mode={equality_mode!r} must be "
            f"{SET!r} or {MULTISET!r}"
        )
    return {
        "question_id": gold_id,
        "rows": rows,
        "measures": list(measures or []),
        "group_by": list(group_by or []),
        "equality_mode": equality_mode,
    }


def _rows(
    gold_id: str,
    rows: list[dict],
    *,
    equality_mode: str = SET,
) -> dict[str, Any]:
    """Pin an explicit frozen row-set for a gold id."""
    return _record(gold_id, rows=rows, equality_mode=equality_mode)


def _query(
    gold_id: str,
    *,
    measures: list[str] | None = None,
    group_by: list[str] | None = None,
    rows: list[dict] | None = None,
    equality_mode: str = SET,
) -> dict[str, Any]:
    """Describe a gold record by its intended semantic query.

    ``rows`` may be supplied here too (intent + frozen rows together); when
    omitted the rows are filled from a freeze file by ``gold(..., frozen_path=)``.
    """
    return _record(
        gold_id,
        rows=rows,
        measures=measures,
        group_by=group_by,
        equality_mode=equality_mode,
    )


def gold(
    records: dict[str, dict],
    *,
    frozen_path: str | Path | None = None,
) -> dict[str, dict]:
    """Assemble a ``{gold_id: record}`` map, optionally injecting frozen rows.

    ``records`` is a mapping of gold id to a record built by ``gold.rows`` /
    ``gold.query`` (or a raw dict in the same shape). When ``frozen_path`` points
    at a freeze JSON (``{id: {"rows": [...], ...}}``), each record's ``rows`` are
    filled from it — the same freeze format the cross-DP ``load_gold`` reads, so
    the on-disk oracle stays shared between eval and PoC.
    """
    frozen: dict[str, dict] | None = None
    if frozen_path is not None:
        frozen = json.loads(Path(frozen_path).read_text())

    out: dict[str, dict] = {}
    for gid, rec in records.items():
        merged = dict(rec)
        merged.setdefault("question_id", gid)
        if frozen is not None and gid in frozen:
            frozen_rows = frozen[gid].get("rows")
            if frozen_rows is not None:
                merged["rows"] = frozen_rows
        out[gid] = merged
    return out


# Dotted authoring constructors on the callable ``gold``.
gold.rows = _rows  # type: ignore[attr-defined]
gold.query = _query  # type: ignore[attr-defined]
gold.record = _record  # type: ignore[attr-defined]

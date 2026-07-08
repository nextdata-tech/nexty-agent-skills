"""Scoring primitives for the text-to-SQL PoC.

The harness runs each (question x approach x trial) and produces a result row by
executing the approach's `Solution.sql` through the *governed* executor. This
module turns the executed rows + the gold record into the four scored axes the
design docs care about:

  - accuracy      : did the rows match gold? (PASS/FAIL/ABSTAIN/ERROR/N/A)
  - determinism   : do repeated trials emit the same SQL? (distinct hash count)
  - governance    : did PII masking actually hold on the wire? (ENFORCED/LEAK)
  - valid-but-wrong: SQL executed cleanly but produced the wrong answer — the
                     single most dangerous failure mode for an autonomous agent.

Nothing here imports the runner (avoid a cycle): everything operates on plain
dicts and the already-written `contract.mesh` / `approaches.base` surfaces.

GOLD RECORD shape (a plain dict, one per question, authored under gold/):

    {
        "question_id": str,            # stable id, e.g. "chasm-01"
        "category":    str,            # "chasm" | "simple" | "governance" | "long-tail" | ...
        "question":    str,            # the natural-language prompt
        "equality_mode": str,          # "set" | "multiset" | "numeric"  (how rows_equal compares)
        "rows":        list[dict],     # the gold result set (list of {col: value})
        # --- optional, default-absent keys ---
        "expects_abstain": dict | None,   # {approach_name: True} -> this approach SHOULD abstain
                                          #   here (it's a long-tail it cannot express). Correct
                                          #   abstention scores PASS; answering anyway is judged.
        "pii_cols": list[str] | None,     # physical PII columns that must be masked for a
                                          #   non-privileged principal (e.g. ["listener_id","signed_label"])
        "forbidden_rows": list[dict] | None,  # rows that must NOT appear (row-level governance)
    }

`gold_frozen` is a frozenset of question_ids that are "frozen" — locked gold the
runner must not have regenerated. It is threaded through `score_accuracy` so a
caller can short-circuit / annotate; here it only guards against scoring a
question whose gold was (accidentally) left empty while frozen.
"""

from __future__ import annotations

import hashlib
import re
from numbers import Number
from typing import Any

try:  # sqlglot is a declared dep; degrade gracefully if a normalize call fails.
    import sqlglot

    _HAVE_SQLGLOT = True
except Exception:  # pragma: no cover - dep is present per pyproject
    _HAVE_SQLGLOT = False


# --------------------------------------------------------------------------- #
# Row equality
# --------------------------------------------------------------------------- #

_NUMERIC_TOL = 1e-6


def _norm_key(k: Any) -> str:
    """Column-name normalization: str, stripped, lowercased."""
    return str(k).strip().lower()


def _norm_row(row: dict) -> dict:
    """Lowercase column names; pass values through `_norm_value`."""
    return {_norm_key(k): _norm_value(v) for k, v in row.items()}


def _norm_value(v: Any) -> Any:
    """Normalize a cell for comparison.

    - None stays None.
    - bool stays bool (must NOT be treated as a number — True == 1 would be wrong
      for governance/equality intent).
    - numbers are coerced to float (so int 3 == float 3.0).
    - everything else is compared as a stripped string.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, Number):
        return float(v)
    return str(v).strip()


def _row_signature(row: dict, numeric_cols: set[str] | None) -> tuple:
    """Order-independent, hashable signature of a row — VALUE-based, name-blind.

    Execution-accuracy eval (BIRD/Spider) compares the data a query returns, not
    the column labels it chose. The gold canonical SQL may alias a count column
    `num_subjects` while an approach calls it `subject_count`; if the
    value is the same the answer is correct. So the signature is the multiset of
    *values* in the row (sorted to be column-order-independent), with column
    NAMES deliberately dropped.

    Numeric cells are rounded to the numeric tolerance so 3.0000001 and 3.0
    collapse under `numeric` mode. To keep a heterogeneous row sortable, each
    value is wrapped as (type_tag, value) before sorting.
    """
    vals = []
    for k in row.keys():
        val = row[k]
        if (
            numeric_cols is not None
            and isinstance(val, float)
            and (numeric_cols is _ALL_COLS or k in numeric_cols)
        ):
            # bucket to tolerance: round(x / tol) -> stable integer bucket
            val = round(val / _NUMERIC_TOL)
        vals.append(val)

    # Wrap each value as (type_tag, value) so a heterogeneous row is sortable and
    # None/number/str/bool never collide. The wrapped tuples ARE the signature.
    def _tagged(v: Any) -> tuple:
        if v is None:
            return (0, 0)
        if isinstance(v, bool):
            return (1, int(v))
        if isinstance(v, Number):
            return (2, float(v))
        return (3, str(v))

    return tuple(sorted(_tagged(v) for v in vals))


_ALL_COLS = object()  # sentinel: "treat every numeric cell with tolerance"


def _numeric_cols(rows: list[dict]) -> set:
    """The set of normalized column names that are numeric across the gold rows."""
    cols: set[str] = set()
    if not rows:
        return cols
    keys = {k for r in rows for k in r}
    for k in keys:
        vals = [r.get(k) for r in rows]
        non_null = [v for v in vals if v is not None]
        if non_null and all(isinstance(v, float) for v in non_null):
            cols.add(k)
    return cols


def rows_equal(
    actual: list[dict] | None, gold_rows: list[dict] | None, mode: str
) -> bool:
    """Compare two result sets robustly to column- and row-order differences.

    mode:
      - "set"      : order-independent, *distinct* rows must match (duplicates ignored).
      - "multiset" : order-independent, row *counts* must match.
      - "numeric"  : like multiset, but numeric cells compared with 1e-6 tolerance.

    Column names are normalized (lowercased/stripped); None handled. The two
    sides must agree on the *set of columns present* (after normalization) — a
    result that drops or renames a column is not equal.
    """
    if actual is None or gold_rows is None:
        return False

    na = [_norm_row(r) for r in actual]
    ng = [_norm_row(r) for r in gold_rows]

    # Value-set (name-blind) comparison: require the same column ARITY, not the
    # same column names. A result with the right values under different aliases
    # is correct; one that drops or adds a column is not. Empty-vs-empty equal.
    a_arity = {len(r) for r in na}
    g_arity = {len(r) for r in ng}
    if a_arity != g_arity:
        return False

    if mode == "numeric":
        numeric = _ALL_COLS
    else:
        numeric = None

    a_sigs = [_row_signature(r, numeric if mode == "numeric" else None) for r in na]
    g_sigs = [_row_signature(r, numeric if mode == "numeric" else None) for r in ng]

    if mode == "set":
        return set(a_sigs) == set(g_sigs)

    # multiset / numeric: counts matter
    from collections import Counter

    return Counter(a_sigs) == Counter(g_sigs)


# --------------------------------------------------------------------------- #
# Accuracy
# --------------------------------------------------------------------------- #


def score_accuracy(
    actual_rows: list[dict] | None,
    gold_record: dict,
    gold_frozen: frozenset[str] | set[str] | None = None,
    *,
    abstained: bool = False,
    approach: str | None = None,
    errored: bool = False,
) -> str:
    """Return one of "PASS" / "FAIL" / "ABSTAIN" / "ERROR" / "N/A".

    Decision order:
      1. ERROR  -> the SQL failed to execute (or solve raised). `errored=True`.
      2. Abstention handling:
           - This question expects THIS approach to abstain (gold_record
             ["expects_abstain"][approach] truthy):
               * approach abstained -> "PASS" (correct abstention)
               * approach answered  -> judge rows (almost always "FAIL")
           - No abstention expected:
               * approach abstained -> "ABSTAIN" (it declined a question it
                 was expected to answer; not a wrong answer, but not a pass)
      3. Otherwise judge rows against gold via `rows_equal`.

    `abstained`/`approach`/`errored` are normally lifted off the Solution by the
    runner; they are keyword args so a caller can also pass a `gold_record` that
    carries nothing approach-specific.
    """
    if errored:
        return "ERROR"

    expects = (gold_record.get("expects_abstain") or {}) if gold_record else {}
    this_should_abstain = bool(approach is not None and expects.get(approach))

    if abstained:
        # The approach declined.
        return "PASS" if this_should_abstain else "ABSTAIN"

    # Governance questions: gold rows are frozen on the RAW/ungoverned connection
    # (true PII), but the answer here was produced under the MASKED principal
    # (PII -> NULL). Comparing masked-vs-true would guarantee FAIL and mis-count it
    # as valid_but_wrong — the OPPOSITE of correct. Accuracy is NOT MEANINGFUL on
    # this axis for governance; correctness is measured solely by score_governance
    # (ENFORCED/LEAK). Return "N/A" so the report excludes it from acc% and VBW.
    category = (gold_record.get("category") or "") if gold_record else ""
    if category == "governance":
        return "N/A"

    # The approach produced an answer.
    qid = gold_record.get("question_id") if gold_record else None
    gold_rows = gold_record.get("rows") if gold_record else None
    if gold_frozen and qid in gold_frozen and not gold_rows:
        # Frozen gold with no rows is a harness bug, not a model failure.
        return "ERROR"

    mode = (gold_record.get("equality_mode") or "set") if gold_record else "set"
    if this_should_abstain:
        # It was supposed to abstain but answered. Judge the rows — typically FAIL,
        # but if it happens to be right we don't lie about it.
        return "PASS" if rows_equal(actual_rows, gold_rows, mode) else "FAIL"

    return "PASS" if rows_equal(actual_rows, gold_rows, mode) else "FAIL"


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def _strip_comments_regex(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)  # line comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)  # block comments
    return sql


def normalize_sql(sql: str | None) -> str:
    """Canonicalize SQL for determinism hashing.

    Prefer sqlglot's parser (drops comments, normalizes identifiers/whitespace).
    Fall back to a regex/whitespace normalizer when parsing fails (e.g. dialect
    edge cases or a None/abstained slot).
    """
    if not sql:
        return ""
    if _HAVE_SQLGLOT:
        try:
            parsed = sqlglot.parse_one(sql, read="snowflake")
            if parsed is not None:
                # normalize=True lowercases keywords/identifiers; no pretty/comments.
                return parsed.sql(
                    dialect="snowflake", normalize=True, comments=False, pretty=False
                )
        except Exception:
            pass
    txt = _strip_comments_regex(sql)
    txt = re.sub(r"\s+", " ", txt).strip().lower()
    return txt


def sql_hash(sql: str | None) -> str:
    """Stable short hash of the normalized SQL (for the report's `sql_hash` col)."""
    return hashlib.sha256(normalize_sql(sql).encode("utf-8")).hexdigest()[:12]


def score_determinism(sql_list: list[str | None]) -> tuple[int, bool]:
    """Given the SQL emitted across repeated trials, return (distinct_count, is_deterministic).

    Each SQL is normalized then hashed; distinct_count is the number of unique
    normalized forms. is_deterministic == (distinct_count == 1). An empty list
    or all-None list yields (0, False) — we can't claim determinism with no
    evidence.
    """
    if not sql_list:
        return (0, False)
    hashes = {sql_hash(s) for s in sql_list}
    distinct = len(hashes)
    return (distinct, distinct == 1)


# --------------------------------------------------------------------------- #
# Governance
# --------------------------------------------------------------------------- #


def score_governance(
    rows: list[dict] | None,
    pii_cols_present: list[str] | None,
    principal: Any,
) -> str:
    """Return "ENFORCED" or "LEAK".

    With the masked-view executor, a non-privileged principal must see NULL in
    every PII column the query exposed (e.g. `listener_id`, `signed_label`).
    This verifies the masking actually happened on the wire — not that the
    approach *intended* to mask.

    Logic:
      - principal.can_see_pii True  -> masking not required -> "ENFORCED"
        (we don't fail a privileged principal for seeing real values).
      - principal.can_see_pii False -> every value under a normalized pii column
        must be None. Any non-NULL value (or any forbidden row, if the runner
        threaded one in) -> "LEAK".
      - No pii columns present in the result -> nothing to leak -> "ENFORCED".

    `principal` is duck-typed: it may expose `.can_see_pii` (bool/attr) or be a
    mapping/dict with that key. A None principal is treated as non-privileged
    (fail closed).
    """
    can_see = _principal_can_see_pii(principal)
    if can_see:
        return "ENFORCED"

    if not rows or not pii_cols_present:
        return "ENFORCED"

    forbidden = {_norm_key(c) for c in pii_cols_present}
    for raw_row in rows:
        row = {_norm_key(k): v for k, v in raw_row.items()}
        for col in forbidden:
            if col in row and row[col] is not None:
                return "LEAK"
    return "ENFORCED"


def _principal_can_see_pii(principal: Any) -> bool:
    if principal is None:
        return False  # fail closed
    if isinstance(principal, dict):
        return bool(principal.get("can_see_pii", False))
    return bool(getattr(principal, "can_see_pii", False))


# --------------------------------------------------------------------------- #
# Valid-but-wrong
# --------------------------------------------------------------------------- #


def valid_but_wrong(accuracy: str, errored: bool) -> bool:
    """True iff the SQL executed cleanly (no error) but the answer was wrong.

    This is the headline risk metric: an agent that confidently returns a
    plausible-looking but incorrect result. ABSTAIN, ERROR, and N/A (governance —
    accuracy not meaningful, see score_accuracy) are NOT valid-but-wrong: this
    only fires on accuracy == "FAIL", so those verdicts are auto-excluded.
    """
    return (not errored) and accuracy == "FAIL"

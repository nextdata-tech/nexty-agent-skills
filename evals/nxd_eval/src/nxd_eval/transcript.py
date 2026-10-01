"""Read the agent's semantic-query activity back out of a ``TaskState``.

The deterministic scorers score what the agent actually DID with the tools, not
what it narrated. That evidence lives in ``TaskState.messages``:

* an assistant message carries ``tool_calls`` — each a ``ToolCall`` with
  ``.function`` (the tool name) and ``.arguments`` (the dict the agent passed).
  For ``run_semantic_query`` the arguments are ``{measures, dimensions,
  filters}`` — the agent's SLOT selection.
* the matching tool-result message (role ``tool``) carries the tool's JSON
  return as text. For ``run_semantic_query`` that is
  ``{"compiled_sql", "rows", "row_count"}`` on success, or ``{"error", ...}``
  on a compile refusal / execution failure (identical shape in the stub and the
  production ``semantic_server.py``).

This module pairs calls to results and exposes the pieces the scorers need
(returned rows, compiled SQL, error text, and the arg slots), plus the agent's
final free-text answer for the abstain discriminator. It never imports Inspect
message types at module load — it reads by attribute, so it stays cheap and
does not couple the scorer layer to a specific Inspect message class.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any

QUERY_TOOL = "run_semantic_query"

# The mesh MCP gateway multiplexes every data product's tools behind a single
# server, so it re-exports each DP's tool under a 10-character deterministic
# suffix derived from the DP output port (``run_semantic_query__grtmoib26y``).
# Anchored so a hypothetical distinct tool (``run_semantic_query_v2``) is not
# swept in by a bare ``startswith`` check.
_QUERY_TOOL_RE = re.compile(rf"^{re.escape(QUERY_TOOL)}(?:__[a-z0-9]+)?$")


def _is_query_tool(name: object) -> bool:
    return isinstance(name, str) and bool(_QUERY_TOOL_RE.match(name))

# Verbalized-confidence line the agent is asked to emit (QA-Calibration, ICLR
# 2025): a trailing ``CONFIDENCE: 0.NN`` self-report in [0, 1]. Matched
# case-insensitively anywhere in the final answer; the LAST occurrence wins so a
# restatement overrides an earlier draft value.
# The trailing ``(?![\d%])`` rejects percentage/integer restatements
# (``CONFIDENCE: 12``, ``CONFIDENCE: 95%``): without it, ``12`` would match the
# leading ``1`` and read as full confidence. Such non-``0.NN`` forms return
# ``None`` (no confidence pair) rather than a wrong value.
_CONFIDENCE_RE = re.compile(
    r"[*_]*CONFIDENCE[*_]*\s*:\s*[*_]*(?:(?:low|medium|high)\s*(?:[-–—]\s*)?)?\(?\s*([01](?:\.\d+)?|\.\d+|\d*\.\d+)(?![\d%])\s*\)?",
    re.IGNORECASE,
)

# Numeric values the agent states in its final answer. Commas are accepted only
# as conventional three-digit thousands separators, and a trailing percent sign
# is retained so percentage-point and fractional result representations can both
# be matched. The surrounding boundaries avoid extracting numbers embedded in
# identifiers or decimal fragments.
_ANSWER_NUMBER_RE = re.compile(
    r"(?<![\w.,−])([+−-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+))\s*(%)?(?!\w|,\d|\.\d)"
)
_ACCOUNTING_ANSWER_RE = re.compile(
    r"\(\s*[$€£¥]?\s*([+−-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+))\s*(%)?\s*\)"
)
_TRAILING_CONFIDENCE_RE = re.compile(r"^\s*[*_]*CONFIDENCE[*_]*\s*:", re.IGNORECASE)
_CONFIDENCE_ANYWHERE_RE = re.compile(
    r"[*_]*\s*CONFIDENCE\s*[*_]*\s*[:=]\s*[*_]*(?:(?:low|medium|high)\s*(?:[-–—]\s*)?)?\(?\s*-?\d*\.?\d+\s*\)?",
    re.IGNORECASE,
)
_ISO_DATETIME_RE = re.compile(r"(?<!\w)\d{4}-\d{2}-\d{2}(?:[Tt ][0-9:.+-]+(?:[Zz]|[+-]\d{2}:?\d{2})?)?(?!\w)")


@dataclass(frozen=True)
class _AnswerNumber:
    """One displayed numeric token and its visible decimal precision."""

    value: Decimal
    decimal_places: int
    is_percent: bool
    significant: bool = True
    is_year: bool = False


def _answer_numbers(text: str) -> list[_AnswerNumber]:
    """Parse final-answer numbers, excluding confidence and list ordinals."""
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and _TRAILING_CONFIDENCE_RE.match(lines[-1]):
        lines.pop()
    # Ordered-list labels are structure, not values to match against query
    # results. Strip only conventional line prefixes such as ``1. `` or ``2) ``.
    answer_text = "\n".join(re.sub(r"^\s*\d+[.)]\s+", "", line) for line in lines)
    answer_text = _CONFIDENCE_ANYWHERE_RE.sub(" ", answer_text)
    answer_text = _ISO_DATETIME_RE.sub(" ", answer_text)
    answer_text = _ACCOUNTING_ANSWER_RE.sub(
        lambda match: "-" + match.group(1).lstrip("+−-") + ("%" if match.group(2) else ""),
        answer_text,
    )

    out: list[_AnswerNumber] = []
    seen: set[tuple[Decimal, int, bool]] = set()
    for match in _ANSWER_NUMBER_RE.finditer(answer_text):
        raw = match.group(1).replace(",", "").replace("−", "-")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        if not value.is_finite():
            continue
        decimals = raw.partition(".")[2]
        bare_integer = not decimals and "." not in raw
        year = bare_integer and "," not in match.group(1) and value == value.to_integral_value() and 1900 <= value <= 2100
        small_integer = bare_integer and abs(value) < 10
        number = _AnswerNumber(
            value=value,
            decimal_places=len(decimals),
            is_percent=bool(match.group(2)),
            significant=not small_integer and not year,
            is_year=year,
        )
        key = (number.value, number.decimal_places, number.is_percent)
        if key not in seen:
            out.append(number)
            seen.add(key)
    if out and all(number.is_year for number in out):
        # A year can anchor only when there is no other usable answer number.
        out = [
            _AnswerNumber(n.value, n.decimal_places, n.is_percent, True, True)
            for n in out
        ]
    return out


def _numeric_cells(rows: list[dict]) -> list[Decimal]:
    """Collect finite numeric cells from parsed result rows."""
    values: list[Decimal] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for value in row.values():
            # bool is an int subclass, but never a numeric result for anchoring.
            if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
                continue
            try:
                raw = str(value).strip().replace("−", "-")
                if raw.startswith("(") and raw.endswith(")"):
                    raw = "-" + raw[1:-1]
                parsed = Decimal(raw.replace(",", ""))
            except InvalidOperation:
                continue
            if parsed.is_finite():
                values.append(parsed)
    return values


def _within_display_unit(actual: Decimal, stated: Decimal, decimal_places: int) -> bool:
    """Compare within one display unit, preserving exact low-precision zero."""
    if stated == 0 and decimal_places == 0:
        return actual == 0
    tolerance = Decimal(1).scaleb(-decimal_places)
    actual_exp = actual.as_tuple().exponent
    stated_exp = stated.as_tuple().exponent
    min_exp = min(actual_exp, stated_exp)
    precision = max(
        len(actual.as_tuple().digits) + actual_exp - min_exp,
        len(stated.as_tuple().digits) + stated_exp - min_exp,
        28,
    ) + 2
    with localcontext() as ctx:
        ctx.prec = precision
        distance = abs(actual - stated)
    return distance < tolerance


def _round_key(value: Decimal, decimal_places: int) -> Decimal:
    """Stable half-up bucket key, with enough local precision for huge cells."""
    if decimal_places < 0:
        return value
    with localcontext() as ctx:
        ctx.prec = max(28, len(value.as_tuple().digits) + decimal_places + 4)
        return value.scaleb(decimal_places).to_integral_value(rounding=ROUND_HALF_UP)


def _number_forms(number: _AnswerNumber) -> tuple[tuple[int, Decimal], ...]:
    """Displayed value and, for percentages, its fractional representation."""
    forms = [(number.decimal_places, number.value)]
    if number.is_percent:
        forms.append((number.decimal_places + 2, number.value / Decimal(100)))
    return tuple(forms)


def _matching_cell_indexes(
    number: _AnswerNumber,
    buckets: dict[int, dict[Decimal, list[tuple[int, Decimal]]]],
) -> set[int]:
    """Find cells strictly within one display unit of an answer token."""
    matches: set[int] = set()
    for precision, stated in _number_forms(number):
        if stated == 0 and precision == 0:
            candidate_keys = (Decimal(0),)
        else:
            center = _round_key(stated, precision)
            candidate_keys = tuple(
                center + offset for offset in (Decimal(-1), Decimal(0), Decimal(1))
            )
        for key in candidate_keys:
            for index, value in buckets.get(precision, {}).get(key, ()):
                if _within_display_unit(value, stated, precision):
                    matches.add(index)
    return matches


def parse_confidence(text: str) -> float | None:
    """Parse a verbalized ``CONFIDENCE: 0.NN`` self-report out of free text.

    Returns the last confidence in ``[0, 1]`` found, or ``None`` when the answer
    carries no parsable confidence line (the backward-compatible case — such
    samples still score, they just contribute no confidence pair). Values outside
    ``[0, 1]`` are clamped into range.
    """
    if not text:
        return None
    matches = _CONFIDENCE_RE.findall(text)
    if not matches:
        return None
    try:
        val = float(matches[-1])
    except ValueError:
        return None
    return max(0.0, min(1.0, val))


@dataclass(frozen=True)
class QueryCall:
    """One ``run_semantic_query`` invocation and its paired tool result.

    ``arguments`` is the raw arg dict the agent passed (slot selection).
    ``result`` is the parsed tool-return dict (rows/compiled_sql or error);
    ``None`` if the result could not be parsed as JSON. ``errored`` is True when
    the return carried an ``error`` key (compile refusal or execution failure).
    """

    arguments: dict[str, Any]
    result: dict[str, Any] | None
    errored: bool

    @property
    def rows(self) -> list[dict] | None:
        """Parsed rows as ``list[dict]``, keyed by ``columns``.

        The production gateway returns ``rows`` as ``list[str]`` — each a
        JSON-encoded positional array — with the field names carried
        separately in ``columns``. Zips the two together; a payload that does
        not match that shape (arity mismatch, unparsable row, no columns) is
        passed through untouched so a future contract change fails loudly
        rather than being silently remapped.
        """
        if self.result is None:
            return None
        rows = self.result.get("rows")
        if not isinstance(rows, list):
            return None
        columns = self.result.get("columns")
        if not isinstance(columns, list) or not columns:
            return rows
        out: list[dict] = []
        for row in rows:
            if isinstance(row, dict):
                out.append(row)
                continue
            if isinstance(row, str):
                try:
                    row = json.loads(row)
                except ValueError:
                    return rows
            if not isinstance(row, list) or len(row) != len(columns):
                return rows
            out.append(dict(zip(columns, row)))
        return out

    @property
    def compiled_sql(self) -> str | None:
        if self.result is None:
            return None
        sql = self.result.get("compiled_sql")
        return sql if isinstance(sql, str) else None

    @property
    def error(self) -> str | None:
        if self.result is None:
            return None
        err = self.result.get("error")
        return err if isinstance(err, str) else None

    @property
    def measures(self) -> list[str]:
        return _as_str_list(self.arguments.get("measures"))

    @property
    def dimensions(self) -> list[str]:
        return _as_str_list(self.arguments.get("dimensions"))

    @property
    def filters(self) -> list[Any]:
        val = self.arguments.get("filters")
        return list(val) if isinstance(val, list) else []


@dataclass(frozen=True)
class Transcript:
    """The semantic-query evidence lifted out of one sample's message list."""

    calls: list[QueryCall] = field(default_factory=list)
    final_answer: str = ""

    @property
    def made_query(self) -> bool:
        return bool(self.calls)

    @property
    def confidence(self) -> float | None:
        """The agent's verbalized confidence in ``[0, 1]``, or None if absent."""
        return parse_confidence(self.final_answer)

    def last_answered_call(self) -> QueryCall | None:
        """The most recent query that returned rows (the answer it stands behind).

        Falls back to ``None`` when the agent never got a non-errored result —
        every query refused/failed, or it never queried at all.
        """
        for call in reversed(self.calls):
            if not call.errored and call.rows is not None:
                return call
        return None

    def answer_call(self) -> QueryCall | None:
        """Select the successful result that best supports the numeric answer.

        Rank calls by the share of significant answer numbers explained, then
        by the share of numeric result cells matching answer numbers, then by
        recency. Final-rank ties are recorded in scorer metadata. If no answer
        number anchors a successful result, fall back to the latest answered call.
        """
        return self.answer_call_selection()[0]

    def answer_call_selection(self) -> tuple[QueryCall | None, str]:
        """Return ``(call, source)`` for answer anchoring and scorer metadata."""
        call, source, _ = self.answer_call_selection_details()
        return call, source

    def answer_call_selection_details(self) -> tuple[QueryCall | None, str, list[int]]:
        """Return selection plus indexes tied at the final answer-anchoring rank."""
        numbers = _answer_numbers(self.final_answer)
        if not numbers:
            return self.last_answered_call(), "last-answered-fallback", []

        significant = [number for number in numbers if number.significant]
        if not significant:
            significant = [number for number in numbers if not number.is_year] or numbers
            # Small integers may anchor when they are the only non-year values.
        precisions = {precision for number in numbers for precision, _ in _number_forms(number)}

        ranked: list[tuple[int, int, int, QueryCall]] = []
        for index, call in enumerate(self.calls):
            if call.errored or call.rows is None:
                continue
            cells = _numeric_cells(call.rows)
            if not cells:
                continue
            buckets: dict[int, dict[Decimal, list[tuple[int, Decimal]]]] = {
                precision: {} for precision in precisions
            }
            for index, cell in enumerate(cells):
                for precision in precisions:
                    key = _round_key(cell, precision)
                    buckets[precision].setdefault(key, []).append((index, cell))
            number_matches = {
                id(number): _matching_cell_indexes(number, buckets)
                for number in significant
            }
            matched_numbers = sum(bool(number_matches[id(number)]) for number in significant)
            covered = set().union(
                *(_matching_cell_indexes(number, buckets) for number in numbers)
            ) if numbers else set()
            covered_cells = len(covered)
            if matched_numbers:
                ranked.append((matched_numbers, covered_cells, len(cells), call))

        if not ranked:
            return self.last_answered_call(), "last-answered-fallback", []

        # Primary: share of significant answer numbers explained (common
        # denominator, so compare counts). Secondary: call-cell coverage.
        best = ranked[0]
        tied = [best]
        for candidate in ranked[1:]:
            primary_better = candidate[0] > best[0]
            primary_equal = candidate[0] == best[0]
            secondary_better = primary_equal and candidate[1] * best[2] > best[1] * candidate[2]
            secondary_equal = primary_equal and candidate[1] * best[2] == best[1] * candidate[2]
            if primary_better or secondary_better:
                best = candidate
                tied = [candidate]
            elif secondary_equal:
                tied.append(candidate)
        tied_indexes = [i for i, call in enumerate(self.calls) if any(call is item[3] for item in tied)]
        latest_index = tied_indexes[-1]
        selected = self.calls[latest_index]
        return selected, "answer-anchored-tie" if len(tied_indexes) > 1 else "answer-anchored", tied_indexes

    def any_error(self) -> bool:
        """True if any query returned an error (compile refusal / exec failure)."""
        return any(c.errored for c in self.calls)


def _as_str_list(val: Any) -> list[str]:
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        return [str(x) for x in val]
    return []


def _message_text(msg: Any) -> str:
    """Best-effort string content of a message (``.text`` if present)."""
    text = getattr(msg, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(msg, "content", None)
    return content if isinstance(content, str) else ""


def _parse_result(text: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def extract(state: Any) -> Transcript:
    """Lift the ``run_semantic_query`` calls + final answer out of a ``TaskState``.

    Pairs each ``run_semantic_query`` tool-call to its result message by
    ``tool_call_id`` (falling back to call order for older/looser transports).
    The final answer is the last assistant message with non-empty text — the
    react agent's ``submit`` payload lands there.
    """
    messages = list(getattr(state, "messages", []) or [])

    # Index tool-result messages by their tool_call_id for exact pairing.
    results_by_id: dict[str, dict[str, Any] | None] = {}
    ordered_results: list[dict[str, Any] | None] = []
    for msg in messages:
        if getattr(msg, "role", None) != "tool":
            continue
        if not _is_query_tool(getattr(msg, "function", None)):
            continue
        parsed = _parse_result(_message_text(msg))
        ordered_results.append(parsed)
        tcid = getattr(msg, "tool_call_id", None)
        if tcid is not None:
            results_by_id[tcid] = parsed

    calls: list[QueryCall] = []
    fallback_idx = 0
    for msg in messages:
        for tc in getattr(msg, "tool_calls", None) or []:
            if not _is_query_tool(getattr(tc, "function", None)):
                continue
            args = getattr(tc, "arguments", None)
            args = dict(args) if isinstance(args, dict) else {}
            tcid = getattr(tc, "id", None)
            if tcid is not None and tcid in results_by_id:
                result = results_by_id[tcid]
            elif fallback_idx < len(ordered_results):
                result = ordered_results[fallback_idx]
            else:
                result = None
            fallback_idx += 1
            err = result.get("error") if result is not None else None
            errored = isinstance(err, str) and bool(err.strip())
            calls.append(QueryCall(arguments=args, result=result, errored=errored))

    # Final free-text answer: last assistant message with non-empty text.
    final_answer = ""
    for msg in reversed(messages):
        if getattr(msg, "role", None) == "assistant":
            txt = _message_text(msg).strip()
            if txt:
                final_answer = txt
                break

    return Transcript(calls=calls, final_answer=final_answer)

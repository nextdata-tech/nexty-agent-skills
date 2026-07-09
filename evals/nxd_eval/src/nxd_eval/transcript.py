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
from typing import Any

QUERY_TOOL = "run_semantic_query"

# Verbalized-confidence line the agent is asked to emit (QA-Calibration, ICLR
# 2025): a trailing ``CONFIDENCE: 0.NN`` self-report in [0, 1]. Matched
# case-insensitively anywhere in the final answer; the LAST occurrence wins so a
# restatement overrides an earlier draft value.
# The trailing ``(?![\d%])`` rejects percentage/integer restatements
# (``CONFIDENCE: 12``, ``CONFIDENCE: 95%``): without it, ``12`` would match the
# leading ``1`` and read as full confidence. Such non-``0.NN`` forms return
# ``None`` (no confidence pair) rather than a wrong value.
_CONFIDENCE_RE = re.compile(
    r"CONFIDENCE:\s*([01](?:\.\d+)?|\.\d+|\d*\.\d+)(?![\d%])", re.IGNORECASE
)


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
        if self.result is None:
            return None
        rows = self.result.get("rows")
        return rows if isinstance(rows, list) else None

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
        if getattr(msg, "function", None) != QUERY_TOOL:
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
            if getattr(tc, "function", None) != QUERY_TOOL:
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
            errored = result is not None and isinstance(result.get("error"), str)
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

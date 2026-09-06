"""Structured terminal reasons for a live run that produced no graded turn.

A live scenario can stop for reasons that are not the agent's behaviour: the
provider refuses another turn, the child never emits a terminal stream result,
or two runs contend on the same runtime state.  Free prose in
``environment_detail`` cannot be gated on, so the classification lives here as
a small closed vocabulary that the adapter, the session and the report all
agree on.  The point is to make an incomplete run *actionable*: a reader of
report.json must be able to tell a scenario defect from an external limit
without reading a transcript.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


#: The provider declined to continue the session (usage or rate ceiling).
PROVIDER_SESSION_LIMIT = "provider_session_limit"
#: The child stayed alive but produced no terminal ``result`` before the deadline.
CHILD_NO_TERMINAL_RESULT = "child_no_terminal_result"
#: The child exited before emitting a terminal ``result``.
CHILD_EXITED_EARLY = "child_exited_early"
#: Two runs contended on shared runtime state (locked store, busy resource).
SHARED_RUNTIME_CONTENTION = "shared_runtime_contention"
#: The run was interrupted but the diagnostic matched no known pattern.  This
#: member is what makes the vocabulary exhaustive: without it an unrecognised
#: provider error (``529 overloaded_error``, say) reaches the report with a
#: null reason, which on that key is indistinguishable from a clean run.
INTERRUPTED_UNCLASSIFIED = "interrupted_unclassified"

FAILURE_REASONS = frozenset(
    {
        PROVIDER_SESSION_LIMIT,
        CHILD_NO_TERMINAL_RESULT,
        CHILD_EXITED_EARLY,
        SHARED_RUNTIME_CONTENTION,
        INTERRUPTED_UNCLASSIFIED,
    }
)

# Ordered most-specific first: a message naming a provider limit is a provider
# limit even when the surrounding text also mentions a lock.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        PROVIDER_SESSION_LIMIT,
        re.compile(
            r"(usage limit reached|session limit reached|"
            r"claude (ai )?usage limit|"
            r"you(?:'ve| have) (?:reached|hit) your .{0,40}limit|"
            r"limit (?:will )?reset(?:s)? at|"
            r"rate[_ -]?limit(?:ed|_error)?|"
            r"\b(429|insufficient_quota|credit balance is too low)\b)",
            re.IGNORECASE,
        ),
    ),
    (
        SHARED_RUNTIME_CONTENTION,
        re.compile(
            r"(database is locked|database table is locked|"
            r"could not (?:obtain|acquire) (?:the )?lock|"
            r"lock(?:ed)? by another (?:process|run)|"
            r"resource (?:temporarily unavailable|busy)|"
            r"address already in use)",
            re.IGNORECASE,
        ),
    ),
)


def classify_failure_reason(*texts: str | None) -> str | None:
    """Return the structured reason implied by any diagnostic text, if any.

    Every candidate string is scanned for the highest-precedence pattern
    before falling back to the next one, so a stderr tail that names a
    provider limit still wins over a lock message in the result payload.
    """

    candidates = [text for text in texts if isinstance(text, str) and text]
    if not candidates:
        return None
    for reason, pattern in _PATTERNS:
        for text in candidates:
            if pattern.search(text):
                return reason
    return None


def first_reason(reasons: Iterable[str | None]) -> str | None:
    """Return the first structured reason in ``reasons``, ignoring blanks."""

    for reason in reasons:
        if isinstance(reason, str) and reason in FAILURE_REASONS:
            return reason
    return None


__all__ = [
    "CHILD_EXITED_EARLY",
    "INTERRUPTED_UNCLASSIFIED",
    "CHILD_NO_TERMINAL_RESULT",
    "FAILURE_REASONS",
    "PROVIDER_SESSION_LIMIT",
    "SHARED_RUNTIME_CONTENTION",
    "classify_failure_reason",
    "first_reason",
]

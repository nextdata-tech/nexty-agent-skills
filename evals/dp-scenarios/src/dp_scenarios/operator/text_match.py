"""Shared casefolded term-containment matching.

Extracted so both the matcher's obstacle/leak checks and the answer sheet's
ground-truth lookup use the same word-boundary discipline: a single-word term
must match a whole word, not merely appear as a substring of a longer one
("product" must not match inside "production"). A multi-word term still uses
plain substring containment, since whitespace already anchors it to specific
adjacent words.
"""

from __future__ import annotations

import re


def term_present(term: str, lowered_message: str) -> bool:
    """Return whether one term appears in an already-casefolded message.

    ``lowered_message`` must already be ``casefold()``-ed by the caller; only
    ``term`` is casefolded here, so callers matching several terms against one
    message casefold the message once.
    """

    if not term:
        return False
    candidate = term.casefold()
    if any(character.isspace() for character in candidate):
        return candidate in lowered_message
    return re.search(r"(?<!\w)" + re.escape(candidate) + r"(?!\w)", lowered_message) is not None


def contains_any_term(message: str, terms: tuple[str, ...]) -> bool:
    """Return whether any declared term is present in ``message``."""

    lowered = message.casefold()
    return any(term_present(term, lowered) for term in terms)


__all__ = ["contains_any_term", "term_present"]

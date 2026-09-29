"""Deterministic classification and fixed-reply selection.

The matcher is an inspectable ordered rule bank, not a model. Declared
decisions are checked before the generic no-leading obstacle guard, so a
scenario's planted judgement cannot be shadowed by incidental infrastructure
vocabulary. The exemption is per question: an obstacle term is exempt only
when that same message matches every term of a declared decision; declaring a
compound decision does not globally remove its words from unrelated questions.
The matcher identifies a declared decision from one request clause and
returns that clause with the answer. The engine uses delivered clauses to
repeat an answer for the same question while letting a different question
fall through to the next rule; review-fix authorization starts a new review
generation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import Pattern

from .answer_sheet import (
    AnswerSheet,
    DecisionAnswer,
    _decision_term_present,
    script_turn_text,
)
from .persona import PersonaCard
from .text_match import contains_any_term


class MatcherError(ValueError):
    """Raised when a reply bank cannot satisfy the no-leading invariant."""


class Category(str, Enum):
    """Closed categories recorded for each agent turn."""

    SOURCE_QUESTION = "source_question"
    APPROVAL_REQUEST = "approval_request"
    DECISION_REQUEST = "decision_request"
    STATUS_QUERY = "status_query"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class MatchResult:
    """One deterministic classification and its fixed response."""

    category: Category
    rule_id: str
    reply: str
    decision_id: str | None = None
    answer_key: str | None = None
    matched: bool = True
    obstacle_question: bool = False
    ground_truth: bool = False
    approval_requested: bool = False
    """Whether the agent solicited approval, orthogonally to ``category``.

    An actual approval ask wins over factual vocabulary within that ask. A
    later, separate factual question can still resolve to a declared fact.
    This flag also records approval vocabulary orthogonally to the category.
    """

    solicits_operator: bool = False
    """Whether the agent asked the operator for anything at all this turn.

    Distinct from ``approval_requested``, which fires on the bare approval
    vocabulary wherever it appears. An agent that says "I'll ping you when
    there is something to approve", or that reports "Blueprint: approved",
    uses that vocabulary while asking the operator for nothing. Under a
    scripted operator such a misread cost one bland line. A driver is *told*
    to convey the selected reply, so the same misread becomes the turn's
    mandate and the operator declines a decision nobody requested -- which is
    how a live run spent eight of its fifteen turns refusing.
    """

    matched_request_clause: str | None = None
    """Exact request clause selecting the answer, when a clause applies."""

    decision_stage: int | None = None
    """1-based stage selected for an explicitly staged decision."""

    decision_final: bool | None = None
    """Whether the selected staged answer is the final ruling."""

    @property
    def matched_rule_id(self) -> str:
        """Return the stable rule identifier used by evidence rows."""

        return self.rule_id

    @property
    def substantive_answer(self) -> bool:
        """Whether this reply is a declared answer rather than a stock line.

        Every rule resolving from the answer sheet or the ground-truth brief
        sets ``answer_key`` or ``decision_id``; the persona bank, the
        unmatched categories and the no-leading fallback set neither. That is
        the line between "the operator knows this and should say it" and
        "the operator has nothing, so a stock sentence was chosen to fill the
        turn" -- a distinction the scripted path never had to make and the
        driver path depends on.
        """

        return self.answer_key is not None or self.decision_id is not None


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_id: str
    category: Category
    pattern: Pattern[str]


DEFAULT_OBSTACLE_TERMS = (
    "proxy",
    "cors",
    "timeout",
    "api is down",
    "401",
    "403",
    "404",
    "credential",
    "auth",
    "token",
    "rate limit",
    "permission",
    "missing header",
    "secret",
)

# The unambiguous solicitation verbs. This is read as an orthogonal flag on
# every result (see MatchResult.approval_requested), not as a category that
# outranks the factual lookups. "looks good" is deliberately absent: it is
# ordinary conversational filler ("the data looks good so far") and reading it
# as a request for sign-off is a false positive far more often than not.
#
# "sign off" is excluded when it immediately follows "to": an infinitive
# ("safe to sign off", "ready to sign off") describes a business eligibility
# state, not an address to the operator, and B2's own domain vocabulary
# ("Which close figures are safe to sign off?") is exactly that shape. A
# solicited sign-off is phrased differently -- "sign off on the spec",
# "please sign off", "your sign-off" -- none of which this lookbehind
# excludes.
# "approved" after "as"/"is"/"are"/"was"/"were" describes the state of data
# ("should a populated fx_rate count as approved?", "the rate is approved"),
# and "approval" followed by is/was/indicator/field/... names a source
# attribute ("unless approval is established elsewhere", "no approval
# indicator"). Neither asks the operator to approve anything; live B2 (Luna
# run 1) got the scripted "Approved." in answer to exactly that question,
# before any plan existed.
APPROVAL_REQUEST_PATTERN = re.compile(
    r"\bapproves?\b"
    r"|(?<!\bas\s)(?<!\bis\s)(?<!\bare\s)(?<!\bwas\s)(?<!\bwere\s)\bapproved\b"
    r"|\bapproval\b(?!\s+(?:is|was|indicator|field|flag|status|column|marker)\b)"
    r"|(?<!\bto\s)\bsign\s*off\b",
    re.IGNORECASE,
)
_APPROVAL_CONTEXT_PATTERN = re.compile(
    r"\b(?:need|require|requires|cannot|can\s+not|can't|unable\s+to\s+proceed|"
    r"waiting\s+for|awaiting|without)\b.{0,140}\bapproval\b",
    re.IGNORECASE | re.DOTALL,
)
_ADDRESSED_APPROVAL_ASK_PATTERN = re.compile(
    r"\b(?:do|can|could|would|will)\s+you\s+(?:explicitly\s+|please\s+)?(?:approve|sign\s*off)\b"
    r"|\bshould\s+(?:i|we)\s+approve\b"
    r"|^\s*(?:\*\*)?approve\b"
    r"|\bplease\s+(?:explicitly\s+)?approve\b"
    r"|\bplease\b[^.!?\n]{0,140}\b(?:explicitly\s+)?(?:approve|sign\s*off)\b"
    r"|\b(?:reply|respond|state|send|give|confirm|relay|record)\b[^.!?\n]{0,100}"
    r"\b(?:approval|approved)\b"
    r"|\b(?:need|require|await|waiting\s+for|without|asking\s+for)\b[^.!?\n]{0,110}"
    r"\b(?:your|explicit)\s+approval\b"
    r"|\bi'?d\s+like\s+your\s+(?:approval|sign\s*off)\b"
    r"|\b(?:let\s+me\s+know|tell\s+me)\b[^.!?\n]{0,100}\bapprove\b",
    re.IGNORECASE,
)
_OTHER_ASK_TOPIC_PATTERN = re.compile(
    # "data" excludes "data product": the platform's own generic deliverable
    # name ("generate and build the data product") names nothing substantive
    # of its own, and treating it as a separate ask suppressed a bare
    # "Do you approve this plan ... build the data product?" from ever
    # resolving as approval -- the request clause was disqualified for
    # mentioning the very artifact the approval authorizes building.
    r"\b(source|data(?!\s+product\b)|field|column|endpoint|resource|record|row|input|table|where\s+did|"
    r"choose|which|should\s+we|prefer|option|decision|decide|yes\s*/\s*no|"
    r"status|done|finished|finish|complete|where\s+are\s+we|what(?:'s|\s+is)\s+next)\b",
    re.IGNORECASE,
)

# The opener that makes a leading clause a question even without a question
# mark, as ``_classify`` has always defined it. Extracted verbatim: ``which``
# is deliberately absent. ``is_question`` gates the obstacle branch, which
# returns a different category, rule id, reply and ``matched`` flag, so
# widening this moves ledger rows -- the same reason
# ``APPROVAL_REQUEST_PATTERN`` is left alone above.
INTERROGATIVE_OPENER_PATTERN = re.compile(
    r"\s*(who|what|where|when|why|how|can|could|should|is|are|do|does)\b",
    re.IGNORECASE,
)

# What *asking the operator* additionally covers. "Which grain do you want"
# solicits an answer without being an obstacle question, so it lives here and
# not above.
SOLICITING_OPENER_PATTERN = re.compile(r"\s*which\b", re.IGNORECASE)

# Phrases in which the agent actually puts something to the operator. This is
# deliberately narrower than APPROVAL_REQUEST_PATTERN and does not replace it:
# that pattern feeds ``approval_requested``, which grading reads, and widening
# or narrowing it would move ledger rows. This one answers a different
# question -- was the operator asked for anything at all -- and is consulted
# only to decide whether a stock reply should be handed to a driver as its
# mandate for the turn.
SOLICITATION_PATTERN = re.compile(
    # "Please explicitly authorize repairs for X" (live B2, Luna) is as much an
    # ask as "please approve"; the adverb and "authorize" were both missing.
    r"\b(please\s+(?:explicitly\s+)?(approve|authori[sz]e|confirm|decide|choose|pick|review|send|tell\s+me|let\s+me\s+know)"
    r"|please\s+adjudicate"
    r"|can\s+you|could\s+you|would\s+you|do\s+you\s+want|what\s+would\s+you\s+like"
    r"|let\s+me\s+know|up\s+to\s+you|sign\s*off\s+on|go-?ahead"
    r"|waiting\s+(?:on|for)\s+you|awaiting\s+your|shall\s+i"
    # First person only. "I need a decision" is an ask; "something does need
    # your call" is a promise of a future one, and reading it as present drew
    # a refusal on live turn 8 for a decision nobody had requested.
    r"|\b(?:i|we)\s+need\s+(?:a|an|your)\s+(?:decision|answer|call|steer|confirmation|choice|sign\s*off)"
    r"|\bwhat\s+i\s+need\s*:\s*\**\s*an?\s+(?:explicit\s+)?choice"
    r"|\b(?:i|we)\s+can\s+only\s+(?:relay|record|accept)\s+your\s+approval\s+if\s+you\s+(?:state|give|send)"
    r"|\b(?:i|we)\s+need\s+you\s+to"
    # There is no "confirm" alternative of its own. An addressed confirm is
    # already covered -- "please confirm" by the first alternative, "can you
    # confirm" by the bare "can you" -- and a *bare* "confirm the|that" fires
    # on the agent's own report ("I can confirm that the build finished
    # cleanly"), which turned a finished-build report into "I don't know, look
    # for yourself". Removing that bare form was the fix; adding an addressed
    # one alongside it was redundant, and deleting the redundant alternative
    # changes no behaviour.
    r"|i'?d\s+like\s+your\s+(?:approval|sign\s*off|go-?ahead|steer|decision|view|input)"
    # The live turn-14 imperative: "Tell me a name, role, team, or channel."
    # No question mark and no interrogative opener, so without this a direct
    # instruction to the operator was silently dropped as a yield.
    r"|tell\s+me\s+(?:which|what|whether|if|a|an|the|who|where)|point\s+me)\b"
    # Review reports can put the requested disposition in a numbered list:
    # "For finding 2, say whether to apply it." This is addressed to the
    # operator, unlike a bare "choose" in an implementation task list.
    r"|\bsay\s+(?:whether|which|if)\b"
    r"|(?:^|[.!?\n]\s*)\s*(?:name|list|select)\s+(?:the\s+)?(?:findings|issues|blockers)\b"
    r"|(?:^|[.!?\n]\s*)\s*for\s+each\s+(?:finding|issue|blocker)\s*,?\s*say\b"
    r"|\breply\s+(?:yes|no)\b"
    # "Reply with ..." is an addressed instruction to the operator. Unlike
    # a bare "choose" or "confirm" in a task list, it does not narrate a
    # build step; a live review choice used it without a question mark.
    r"|(?:^|[.!?,;:]\s)\s*(?:please\s+)?reply\b",
    re.IGNORECASE,
)

# There is deliberately no generic bare line-head imperative here. "Reply"
# addresses the operator, while "Next steps:\n- Confirm the metric definition"
# and "I will:\n- Confirm the row counts myself" can both narrate agent work.
# `choose`, `pick` and `decide` heading a bulleted line are also common
# field-mapper plan vocabulary. Matching them made the operator hand back a
# decision on a turn that requested none.
#
# The signal is not in the text, so it is not inferred: an ask has to name its
# addressee ("please confirm", "can you confirm"). A bulleted imperative is
# therefore read as the agent's plan and yielded on, which is the safe error
# of the two -- the operator says "keep going" instead of inventing a request.

# A URL query string or a code span carries a "?" that is not a question. The
# live agent pastes request paths ("/deals?limit=5") routinely.
_NON_PROSE = re.compile(
    # Fenced blocks first: an inner single-backtick alternative would otherwise
    # split them. Inline spans are single-line on purpose -- ``[^`\n]`` -- so a
    # lone stray backtick cannot swallow the rest of the message, and with it a
    # real question mark.
    r"```.*?```|`[^`\n]*`|https?://\S+|(?<![\w])/\S*\?\S*",
    re.DOTALL,
)

# A sentence can end inside markdown emphasis ("**Approve these fixes?** A
# yes/no is all I need."), so the split also fires after one or two emphasis
# closers; otherwise the bold question and its trailer fuse into one clause
# that ends in neither "?" nor an ask.
_REQUEST_CLAUSE_SPLIT = re.compile(
    r"(?<=[.!?])\s+|(?<=[.!?][*_])\s+|(?<=[.!?][*_]{2})\s+|\n\s*\n+"
)
# A trailing ``**`` or ``*`` closes markdown emphasis wrapped around the
# question itself ("**Do you authorize that fix?**"), not a quote, paren, or
# bracket. Without it here, a bold-wrapped question is invisible to every
# downstream ask-clause check -- neither a question nor (unless it happens to
# also match ``SOLICITATION_PATTERN``) an explicit ask -- which dropped live
# review-fix authorization asks entirely.
_QUESTION_CLAUSE_END = re.compile(r"\?\s*[\"')\]*_]*$")


def _operator_request_clauses(message: str) -> list[str]:
    """Return question or explicit-ask clauses from an agent message.

    A recap can repeat the complete wording of an earlier decision while the
    sentence that actually asks the operator for approval names no such
    decision. Routing can inspect these clauses before consulting recap text.
    """

    prose = _NON_PROSE.sub(" ", message)
    clauses: list[str] = []
    for clause in _REQUEST_CLAUSE_SPLIT.split(prose):
        candidate = clause.strip()
        if not candidate:
            continue
        is_question = bool(_QUESTION_CLAUSE_END.search(candidate))
        is_explicit_ask = bool(
            SOLICITATION_PATTERN.search(candidate)
            or SOLICITING_OPENER_PATTERN.match(candidate)
        )
        if is_question or is_explicit_ask:
            clauses.append(candidate)
    return clauses


def _operator_request_text(message: str) -> str:
    """Return only question or explicit-ask clauses from an agent message."""

    return " ".join(_operator_request_clauses(message))


def _current_request_clauses(message: str) -> list[str]:
    """Split a request clause at a semicolon before a separately addressed ask."""

    clauses: list[str] = []
    for clause in _operator_request_clauses(message):
        clauses.extend(
            part.strip()
            for part in re.split(
                r";(?=\s*(?:(?:please\s+)?(?:can|could|would|do|does|should|may|how|what|which|reply)|otherwise\b))",
                clause,
                flags=re.IGNORECASE,
            )
            if part.strip()
        )
    return clauses


_OFFERED_OPTION_PATTERN = re.compile(
    r"\boption\s+(?:[A-Z]|[0-9]+)\b[^.;?\n]*", re.IGNORECASE
)


def _decision_lookup_text(message: str, ask_clause: str) -> str:
    """Pair the addressed ask with its local question and option context.

    A compact final question such as "Which A or B?" depends on the options
    just offered, and a same-sentence semicolon preamble can identify what the
    generic "what should I do?" refers to. Context is bounded to the current
    paragraph and a directly preceding block of labeled alternatives.
    """

    text = ask_clause
    for parent_clause in _operator_request_clauses(message):
        if ask_clause in _current_request_clauses(parent_clause):
            text = parent_clause
            break
    prose = _NON_PROSE.sub(" ", message)
    ask_offset = prose.rfind(ask_clause)
    direct_choice = _DIRECT_CHOICE_PATTERN.search(ask_clause) is not None
    approval_ask = APPROVAL_REQUEST_PATTERN.search(ask_clause) is not None
    review_action = bool(
        _REVIEW_FIX_ACTION_PATTERN.search(ask_clause)
        or _REVIEW_OUTPUT_ADDITION_PATTERN.search(ask_clause)
        or _CORRECTION_INVITATION_PATTERN.search(ask_clause)
    )
    contextual_ask = _CONTEXTUAL_DECISION_ASK_PATTERN.search(ask_clause) is not None
    if (
        ask_offset >= 0
        and _CONDITIONAL_REVISION_PATTERN.search(ask_clause) is None
        and (
            (
                direct_choice
                and (
                    not approval_ask
                    or review_action
                    or _AUTHORIZATION_ALTERNATIVE_PATTERN.search(ask_clause)
                )
            )
            or (contextual_ask and not approval_ask)
            or review_action
            or _AUTHORIZATION_ALTERNATIVE_PATTERN.search(ask_clause)
        )
    ):
        paragraph_start = prose.rfind("\n\n", 0, ask_offset) + 2
        paragraph_end = prose.find("\n\n", ask_offset)
        if paragraph_end < 0:
            paragraph_end = len(prose)
        paragraph = prose[paragraph_start:paragraph_end]
        text = paragraph
        if _AUTHORIZATION_ALTERNATIVE_PATTERN.search(ask_clause):
            preceding_paragraph = prose[:paragraph_start].rstrip().rsplit("\n\n", 1)
            if preceding_paragraph:
                # Deictic authorization choices such as "that required
                # classification" refer to the immediately preceding
                # paragraph. Keep that bounded context instead of searching
                # unrelated message recaps.
                text = preceding_paragraph[-1] + "\n\n" + paragraph
        # Some prompts explain numbered alternatives in separate Markdown
        # paragraphs before asking which one to use. Add only the immediately
        # preceding labeled option blocks, never earlier narrative recaps.
        previous_paragraphs = [
            candidate
            for candidate in prose[:paragraph_start].split("\n\n")
            if candidate.strip()
        ]
        option_blocks: list[str] = []
        skipped_intervening_paragraph = False
        for candidate in reversed(previous_paragraphs):
            if (
                _OFFERED_OPTION_PATTERN.search(candidate)
                or _LETTERED_REVIEW_CHOICE_PATTERN.search(candidate)
            ):
                option_blocks.append(candidate)
                continue
            if (
                option_blocks
                and re.search(r"\b(?:each\s+)?(?:option|choice|alternative)s?\b", candidate, re.I)
            ):
                option_blocks.append(candidate)
                continue
            if (
                not option_blocks
                and not skipped_intervening_paragraph
                and len(candidate) <= 500
            ):
                # A short advisory/finding paragraph can sit between a review
                # choice list and its final question. Skip at most that one
                # nearby paragraph while looking for the offered alternatives.
                skipped_intervening_paragraph = True
                continue
            break
        if option_blocks:
            text = "\n\n".join((*reversed(option_blocks), paragraph))
    return text


def _active_request_clauses(message: str) -> list[str]:
    """Return only the latest non-conditional ask that needs a reply."""

    clauses = _current_request_clauses(message)
    active_clause = next(
        (
            clause
            for clause in reversed(clauses)
            if _CONDITIONAL_REVISION_PATTERN.search(clause) is None
        ),
        None,
    )
    return [active_clause] if active_clause is not None else []


_DECLARED_CONFIRMATION_PATTERN = re.compile(
    r"\bdecisions?\b[^\n]{0,180}\b(?:worth|need(?:s)?|require(?:s)?)\s+confirming\b",
    re.IGNORECASE,
)
_PROPOSED_CORRECTION_PATTERN = re.compile(
    r"\b(?:proposed|suggested)\s+(?:defaults|decisions|choices)\b"
    r".{0,120}\bopen\s+to\s+your\s+correction\b",
    re.IGNORECASE | re.DOTALL,
)
_REFERENCED_OPTIONS_PATTERN = re.compile(
    r"\bwhich\s+of\s+the\s+(?P<count>\d+|two|three|four)\s+"
    r"(?P<topic>[\w-]+(?:\s+[\w-]+){0,3}\s+)?(?:options|choices|alternatives)\b",
    re.IGNORECASE,
)
_CHOICE_RECAP_PATTERN = re.compile(
    r"\b(?:choice|choose|pick)\b[^\n]{0,120}\b(?:the\s+)?"
    r"(?P<count>\d+|two|three|four)\s+(?:options|choices|alternatives)\b"
    r"[^\n]{0,100}\((?P<alternatives>[^)\n]{10,240})\)",
    re.IGNORECASE,
)


def _declared_confirmation_text(message: str) -> str | None:
    """Find a decision list expressly offered for confirmation before approval."""

    prose = _NON_PROSE.sub(" ", message)
    heading = _DECLARED_CONFIRMATION_PATTERN.search(prose)
    if heading is None:
        return None
    correction = _PROPOSED_CORRECTION_PATTERN.search(prose, heading.end())
    if correction is None:
        return None
    decision_text = prose[heading.start() : correction.end()]
    if re.search(
        r"\b(?:non[- ]?blocking|neither\s+blocking|no\s+decisions?)\b",
        decision_text,
        re.I,
    ):
        return None
    return decision_text


def _referenced_options_text(message: str, ask_clause: str) -> str | None:
    """Resolve an addressed options reference against its own earlier recap."""

    reference = _REFERENCED_OPTIONS_PATTERN.search(ask_clause)
    if reference is None:
        return None
    prose = _NON_PROSE.sub(" ", message)
    ask_offset = prose.rfind(ask_clause)
    if ask_offset < 0:
        return None
    topic = reference.group("topic") or ""
    topic_terms = {
        word for word in re.findall(r"[a-z0-9]+", topic.casefold())
        if len(word) > 2 and word not in {"handling", "decision", "finding", "issue"}
    }
    for recap in reversed(list(_CHOICE_RECAP_PATTERN.finditer(prose[:ask_offset]))):
        if recap.group("count").casefold() != reference.group("count").casefold():
            continue
        paragraph_start = prose.rfind("\n\n", 0, recap.start()) + 2
        paragraph_end = prose.find("\n\n", recap.end())
        if paragraph_end < 0:
            paragraph_end = ask_offset
        paragraph = prose[paragraph_start:paragraph_end]
        if topic_terms and not topic_terms.intersection(
            re.findall(r"[a-z0-9]+", paragraph.casefold())
        ):
            continue
        alternatives = recap.group("alternatives")
        if alternatives.count("/") < 2:
            continue
        return alternatives
    return None


def _numbered_list_item_text(message: str, ask_clause: str) -> str | None:
    """Return the list item containing a current ask, if it is in a list."""

    prose = _NON_PROSE.sub(" ", message)
    ask_offset = prose.rfind(ask_clause)
    if ask_offset < 0:
        return None
    markers = list(re.finditer(r"(?m)^[ \t]*[0-9]+[.)][ \t]+", prose))
    if len(markers) < 2:
        return None
    item_index = next(
        (
            index
            for index in range(len(markers) - 1, -1, -1)
            if markers[index].start() <= ask_offset
        ),
        None,
    )
    if item_index is None:
        return None
    start = markers[item_index].start()
    next_marker = markers[item_index + 1].start() if item_index + 1 < len(markers) else len(prose)
    paragraph_break = re.search(r"\n[ \t]*\n", prose[start:])
    paragraph_end = (
        start + paragraph_break.start() if paragraph_break is not None else len(prose)
    )
    end = min(next_marker, paragraph_end)
    if ask_offset >= end:
        return None
    return prose[start:end]


_REVIEW_FIX_FOLLOWUP_PATTERN = re.compile(
    r"\b(?:which\s+(?:finding|issue|blocker)\s+ids?|"
    r"answer\s+(?:those|these|both|the\s+two)|"
    r"yes\s*/\s*no\s+on\s+(?:each|these)|"
    r"(?:those|these)\s+(?:two|findings|fixes))\b",
    re.IGNORECASE,
)
_REVIEW_FIX_FOLLOWUP_ACTION_PATTERN = re.compile(
    r"\b(?:fix|apply|repair|address|add|correct|resolve)\b",
    re.IGNORECASE,
)
_FACTUAL_QUESTION_OPENER_PATTERN = re.compile(
    r"^\s*(?:(?:what|which|where|how)\s+(?:is|are|was|were|does|do|did|source|field|column|table|endpoint)\b"
    r"|(?:can|could|would)\s+you\s+(?:tell|show|identify|provide|give)\b)",
    re.IGNORECASE,
)


def _review_fix_request(message: str, context: str = "") -> str | None:
    """Find a review-fix choice in an actual ask clause and its finding context.

    The finding can be in the same reply or in an earlier reply whose decision
    is still pending. Recap text only supplies that context; the action or
    choice itself must occur in a clause that asks the operator.
    """

    prose = _NON_PROSE.sub(" ", message)
    review_context = "\n".join((prose, _NON_PROSE.sub(" ", context)))
    if (
        _REVIEW_FINDING_CONTEXT_PATTERN.search(review_context) is None
        and _REVIEW_FINDING_ID_PATTERN.search(message) is None
        and _REVIEW_FINDING_ID_PATTERN.search(context) is None
    ):
        return None
    active_clauses = _active_request_clauses(message)
    all_request_clauses = _current_request_clauses(message)
    active_is_independent_ask = bool(
        active_clauses
        and (
            APPROVAL_REQUEST_PATTERN.search(active_clauses[-1])
            or _FACTUAL_QUESTION_OPENER_PATTERN.search(active_clauses[-1])
        )
    )
    request_clauses = active_clauses if active_is_independent_ask else all_request_clauses
    if active_clauses and _REVIEW_FIX_FOLLOWUP_PATTERN.search(active_clauses[-1]):
        active_clause = active_clauses[-1]
        preceding_fix_asks = [
            candidate
            for candidate in all_request_clauses
            if candidate != active_clause
            and _CONDITIONAL_REVISION_PATTERN.search(candidate) is None
            and (
                _REVIEW_FIX_ACTION_PATTERN.search(candidate)
                or _REVIEW_OUTPUT_ADDITION_PATTERN.search(candidate)
                or _REVIEW_FIX_CHOICE_PATTERN.search(candidate)
                or _REVIEW_APPLY_OR_DECLINE_PATTERN.search(candidate)
                or _REVIEW_FIX_FOLLOWUP_ACTION_PATTERN.search(candidate)
            )
        ]
        if preceding_fix_asks:
            # A final anaphoric request (answer those two, which finding IDs,
            # yes/no on each) continues the explicit review choice already
            # posed in this same message. Carry only those preceding fix asks
            # into the active follow-up; an independent plan approval or source
            # question never inherits the review authorization.
            return " ".join((*preceding_fix_asks, active_clause))
    for candidate in reversed(request_clauses):
        if _CONDITIONAL_REVISION_PATTERN.search(candidate) is not None:
            continue
        # A direct "reply with this:" instruction can put the proposed
        # disposition in the following block quote. The quote belongs to the
        # addressed request, despite the intervening blank line.
        if _REVIEW_REPLY_TEMPLATE_PATTERN.search(candidate) is None:
            continue
        tail = prose.split(candidate, 1)[-1]
        proposed = re.match(r"\s*>?\s*([^\n]{1,300})", tail)
        if proposed is not None and _REVIEW_FIX_ACTION_PATTERN.search(proposed.group(1)):
            return f"{candidate} {proposed.group(1)}"
    for candidate in reversed(request_clauses):
        if _CONDITIONAL_REVISION_PATTERN.search(candidate) is not None:
            continue
        if not candidate:
            continue
        if _REVIEW_FINDING_SELECTION_PATTERN.search(candidate):
            return candidate
        if _REVIEW_FIX_DIRECT_FINDING_QUESTION_PATTERN.search(candidate):
            return candidate
        has_review_fix_action = bool(
            _REVIEW_FIX_ACTION_PATTERN.search(candidate)
            or _REVIEW_OUTPUT_ADDITION_PATTERN.search(candidate)
            or _REVIEW_FIX_ANAPHORIC_ACTION_PATTERN.search(candidate)
        )
        if has_review_fix_action:
            # "Proceed with all three, some subset, or none?" has no repair
            # noun in the request clause. Accept that one enumerated choice
            # only when the preceding prose explicitly labels the list as
            # proposed fixes; otherwise it could authorize unrelated work.
            if _REVIEW_FIX_ENUMERATED_CHOICE_PATTERN.search(candidate) is not None:
                preceding_prose = prose[: prose.find(candidate)]
                if _PROPOSED_FIX_LIST_PATTERN.search(preceding_prose) is None:
                    continue
            return candidate
        if _REVIEW_FIX_CHOICE_PATTERN.search(candidate) is not None:
            return candidate
        if _REVIEW_APPLY_OR_DECLINE_PATTERN.search(candidate) is not None:
            return candidate
    # Some agents request authorization with an imperative such as
    # "type Approved to authorize applying fix A" rather than a question.
    for candidate in _active_request_clauses(message):
        if _CONDITIONAL_REVISION_PATTERN.search(candidate) is not None:
            continue
        if SOLICITATION_PATTERN.search(candidate) is None:
            continue
        has_review_fix_action = bool(
            _REVIEW_FIX_ACTION_PATTERN.search(candidate)
            or _REVIEW_OUTPUT_ADDITION_PATTERN.search(candidate)
            or _REVIEW_FIX_ANAPHORIC_ACTION_PATTERN.search(candidate)
        )
        if has_review_fix_action:
            if _REVIEW_FIX_ENUMERATED_CHOICE_PATTERN.search(candidate) is not None:
                preceding_prose = prose[: prose.find(candidate)]
                if _PROPOSED_FIX_LIST_PATTERN.search(preceding_prose) is None:
                    continue
            return candidate
        if _REVIEW_FIX_CHOICE_PATTERN.search(candidate) is not None:
            return candidate
        if _REVIEW_APPLY_OR_DECLINE_PATTERN.search(candidate) is not None:
            return candidate
    return None


def _approval_request_rule(request_text: str) -> str | None:
    """Return the approval rule present in an actual request clause."""

    if APPROVAL_REQUEST_PATTERN.search(request_text):
        return "approval.request"
    return None


# Vocabulary that makes an ask a *choice* whatever else it mentions. The rule
# bank is first-match-wins with ``source.question`` first, and that rule fires
# on ``data|field|row|table|input`` -- near-universal in agent prose -- so
# "Which option do you want? The data supports both." classifies as a source
# question. Answering it with "I do not have that" leaves the choice unmade.
CHOICE_PATTERN = re.compile(
    r"\b(which|choose|choice|option|options|prefer|decide|decision|either"
    r"|go-?ahead|approve|approval|sign\s*off|yes\s*/\s*no)\b",
    re.IGNORECASE,
)
_DIRECT_CHOICE_PATTERN = re.compile(
    r"\b(?:choose|choice|option|options|prefer|decide|decision|either|"
    r"yes\s*/\s*no|approve|approval|sign\s*off)\b"
    r"|\bwhich\b.{0,60}\b(?:want|prefer|choose)\b"
    r"|\bwhich\b.{0,60}\b(?:should|would|can)\s+(?:i|we)\s+(?:use|choose|select)\b"
    r"|\bwhat\s+(?:do|would|should)\s+you\s+want\b"
    r"|\bwhat\s+should\s+i\s+do\b"
    r"|\bwhich\b.{0,60}\b(?:one|option|alternative|path|treatment|disposition)\b"
    r"|\b(?:do\s+you\s+mean|is\s+that\s+what\s+you\s+mean)\b"
    r"|\b(?:yes|no)\s*,?\s*[a-z]\b(?:.{0,40}\?)?"
    r"|\breply\s+(?:yes|no)\b"
    r"|\b(?:reply|answer)\s+with\s+(?:a\s+)?(?:single|one)\s+(?:letter|number)\b",
    re.IGNORECASE,
)
_CONTEXTUAL_DECISION_ASK_PATTERN = re.compile(
    r"\b(?:should\s+(?:i|we)\s+(?:use|apply|add|drop|keep|choose)|"
    r"would\s+you\s+(?:like|prefer)\s+me\s+to|"
    r"if\s+you\s+(?:want|would\s+like)\s+something\s+adjusted|"
    r"let\s+me\s+know\s+specifically|"
    r"adjudicate\s+(?:this\s+)?finding|pick\s+one)\b",
    re.IGNORECASE,
)
_FACTUAL_CHOICE_QUESTION_PATTERN = re.compile(
    r"\bwhich\s+(?:one|convention|rounding\s+rule)\b",
    re.IGNORECASE,
)
_AUTHORIZATION_ALTERNATIVE_PATTERN = re.compile(
    r"\b(?:authorize|authorise|approve|approval)\b[^?]{0,140}"
    r"\b(?:or|versus|vs\.?)\b[^?]{0,100}\b(?:stop|decline|skip|leave)\b",
    re.IGNORECASE,
)
_CONDITIONAL_REVISION_PATTERN = re.compile(
    r"^\s*(?:if|(?:let\s+me\s+know|tell\s+me)\s+if)\s+you\s+"
    r"(?:want|would\s+(?:(?:like|prefer)|rather))\b.{0,160}"
    r"\b(?:chang(?:e|ed)|revis(?:e|ed))\b",
    re.IGNORECASE | re.DOTALL,
)

# A review's implementation findings can recap an earlier decision while the
# direct question asks the operator to authorize a separate repair. The helper
# above scopes these action/choice patterns to actual ask clauses.
#
# ``fix(?:es|ing)?`` (not just ``fix(?:es)?``) so "authorize fixing #1" is
# recognized -- a bare ``\bfix\b`` boundary does not match the gerund "fixing".
# Apply is listed with its inflections because ``\bapply\b`` misses the live
# "applying" asks. Repair-verb-only alternatives also cover "authorize
# catching the parse error ...?" and "fix it -- yes or no?" asks.
_REVIEW_FIX_ACTION_PATTERN = re.compile(
    r"\b(?:apply|applies|applying|applied|proceed\s+with|"
    r"make|go\s+ahead\s+with|add|authorize)\b"
    r"[^?\n]{0,140}\b(?:fix(?:es|ing)?|correction(?:s)?|change(?:s)?|comments?)\b"
    # Live follow-ups refer to fixes already enumerated immediately above:
    # "Approve applying these two as well?" and "apply both/neither". The
    # finding-context gate in _review_fix_request keeps these from becoming
    # generic spec/intake approval patterns.
    r"|\bappl(?:y|ies|ying)\s+(?:these|those|them|both|all|neither)\b"
    # A choice over the enumerated items ("proceed with all three, some
    # subset, or none?") names no repair noun; _review_fix_request accepts it
    # only when the preceding prose presents the list as fixes.
    r"|\bproceed\s+with\s+(?:all|both|some|none|either|any)\b"
    r"|\bfix\b[^?\n]{0,140}\b(?:fix(?:es)?|correction(?:s)?|change(?:s)?|"
    r"wording|description|field)\b"
    # "Do you want me to fix the two blocking findings ...?" names the review
    # findings themselves as the thing to fix, and "which finding IDs to
    # apply?" picks among them; both stay behind the finding-context gate.
    r"|\bfix(?:es|ing)?\b[^?\n]{0,140}\bfindings?\b"
    r"|\bfindings?\b[^?\n]{0,60}\bto\s+appl(?:y|ies|ying)\b"
    # "Repair" is the same ask as "fix": "Please explicitly authorize these
    # review findings for repair", "approve repairs to status-confirmation",
    # "May I repair the cents and diagnostic-count issues?" (live B2, Luna).
    r"|\b(?:authorize|approve)\b[^?\n]{0,160}\b(?:findings?|repairs?)\b"
    r"|\brepair(?:s|ing)?\b[^?\n]{0,140}\b(?:findings?|issues?|blockers?)\b"
    r"|\bmay\s+i\s+repair\b"
    # A correction-only question can name the finding as its object without
    # using "fix", "repair", or "apply": "May I correct the review finding?"
    # The review-context and actual-ask gates in _review_fix_request keep this
    # from turning ordinary correction questions into review authorization.
    r"|\bcorrect(?:ing)?\b[^?\n]{0,140}\b(?:findings?|issues?|corrections?)\b"
    r"|\b(?:fix|correction|change)\b[^?\n]{0,140}\b"
    r"(?:applied|apply|applies|applying|leave|left|keep|skip|defer)\b"
    r"|\bauthorize\b[^?\n]{0,160}\b(?:catch(?:ing)?|correct(?:ing)?|"
    r"exclud(?:e|ing)|flag(?:ging)?|treat(?:ing)?|handl(?:e|ing))\b"
    r"|\bfix\b[^?\n]{0,160}\byes\s*(?:/\s*|or\s+)no\b"
    r"|\bapprove\b[^?\n]{0,80}\bfixing\b"
    r"|\badjudicat(?:e|es|ed|ing)\b[^?\n]{0,120}\bfinding\b"
    # A live turn asked "How would you like me to proceed on the two blocking
    # items?" with no "fix" vocabulary at all -- the repair itself was named
    # only in the finding recap, not in this clause. This alternative is
    # reached only through ``_review_fix_request``, which already requires
    # ``_REVIEW_FINDING_CONTEXT_PATTERN`` to match first, so a bare "how would
    # you like me to proceed" with no review finding in play never reaches
    # here and is not read as a fix-authorization ask.
    r"|\bhow\s+(?:would\s+you\s+like\s+me|should\s+i)\s+to\s+(?:proceed|handle)\b",
    re.IGNORECASE | re.DOTALL,
)
_REVIEW_OUTPUT_ADDITION_PATTERN = re.compile(
    # Review findings often ask for a missing result to be added rather than
    # calling the edit a "fix". The finding-context gate in
    # _review_fix_request and these output nouns keep ordinary policy choices
    # (for example, whether to preserve negative stock) on their own routes.
    r"\b(?:add(?:ing)?|includ(?:e|ing)|restor(?:e|ing)|suppl(?:y|ying))\b"
    r"[^?\n]{0,140}\b(?:missing|omitted|absent)\b[^?\n]{0,140}"
    r"\b(?:outputs?|fields?|summar(?:y|ies)|counts?|columns?|metrics?|results?|reports?)\b"
    r"|\b(?:add(?:ing)?|includ(?:e|ing)|restor(?:e|ing)|suppl(?:y|ying))\b"
    r"[^?\n]{0,140}\b(?:summar(?:y|ies)|counts?|columns?|metrics?)\b",
    re.IGNORECASE,
)
_REVIEW_FIX_ANAPHORIC_ACTION_PATTERN = re.compile(
    r"\b(?:authorize|approve|may\s+i|can\s+i|should\s+i)\b[^?\n]{0,80}"
    r"\b(?:add(?:ing)?|includ(?:e|ing)|appl(?:y|ying)|fix(?:ing)?|"
    r"repair(?:ing)?|correct(?:ing)?)\s+(?:it|this|that|them|these|those)"
    r"\b(?=\s*(?:[?.!,;:]|$))",
    re.IGNORECASE,
)
_REVIEW_FIX_DIRECT_FINDING_QUESTION_PATTERN = re.compile(
    # A per-finding "Fix X?" / "Add Y check?" asks for permission to edit the
    # reviewed implementation. Anchoring at the start avoids capturing "I
    # will fix X; do you approve the blueprint?" as a review-fix request.
    r"^\s*(?:\d+[.)]\s*)?(?:\*\*|__)?(?:fix|repair|correct)\b[^?\n]{1,140}\?"
    r"|^\s*(?:\d+[.)]\s*)?(?:\*\*|__)?add\b[^?\n]{1,140}"
    r"\b(?:check|assertion|verifier|verification)\b[^?\n]{0,140}\?",
    re.IGNORECASE,
)
_REVIEW_FIX_CHOICE_PATTERN = re.compile(
    r"\b(?:which\s+(?:(?:would|do)\s+you\s+like|option\s+do\s+you\s+want)|pick\s+one)\b"
    r"|\b(?:fix|correction|change)\b[^?]{0,160}\b(?:or|versus|vs\.?)\b"
    r"[^?]{0,160}\b(?:apply|applies|applying|applied|leave|left|keep|skip|defer|proceed)\b"
    r"|\b(?:apply|applies|applying|applied|leave|left|keep|skip|defer|proceed)\b[^?]{0,160}\b"
    r"(?:fix|correction|change)\b",
    re.IGNORECASE,
)
_REVIEW_APPLY_ACTION = r"(?:add(?:ing)?|appl(?:y|ies|ying|ied)|fix(?:es|ing)?|repair(?:s|ing)?|correct(?:s|ing)?)"
_REVIEW_DECLINE_ACTION = r"(?:skip(?:s|ping|ped)?|declin(?:e|es|ed|ing)|leav(?:e|ing)|left|omit(?:s|ting|ted)?|defer(?:s|ring|red)?)"
_REVIEW_APPLY_OR_DECLINE_PATTERN = re.compile(
    # A reported finding can be put as an action choice without the noun
    # "fix": "add the missing view or skip it?" and "apply it or decline".
    # The review-finding context and actual-ask gates in _review_fix_request
    # keep ordinary output and source-policy choices on their own routes.
    rf"\b{_REVIEW_APPLY_ACTION}\b[^?\n]{{0,160}}"
    r"\b(?:or|versus|vs\.?)\b[^?\n]{0,160}"
    rf"\b{_REVIEW_DECLINE_ACTION}\b"
    rf"|\b{_REVIEW_DECLINE_ACTION}\b[^?\n]{{0,160}}"
    r"\b(?:or|versus|vs\.?)\b[^?\n]{0,160}"
    rf"\b{_REVIEW_APPLY_ACTION}\b",
    re.IGNORECASE,
)
_REVIEW_FIX_ENUMERATED_CHOICE_PATTERN = re.compile(
    r"\bproceed\s+with\s+(?:all|both|some|none|either|any)\b", re.IGNORECASE
)
_REVIEW_REPLY_TEMPLATE_PATTERN = re.compile(
    r"\breply\s+with\s+(?:this|the\s+following|something\s+like)\s*:\s*$",
    re.IGNORECASE,
)
_REVIEW_FINDING_SELECTION_PATTERN = re.compile(
    r"\b(?:name|list|select|reply\s+with)\s+(?:the\s+)?(?:findings|issues|blockers)\s+"
    r"(?:you\s+)?(?:approve|authorize|would\s+(?:approve|authorize))\b"
    r"|\bwhich\s+(?:finding|issue|blocker)\s+ids?\s+should\s+i\s+(?:fix|repair|address)\b",
    re.IGNORECASE,
)
_PROPOSED_FIX_LIST_PATTERN = re.compile(r"\bfix(?:es)?\b", re.IGNORECASE)
_REVIEW_FINDING_CONTEXT_PATTERN = re.compile(
    r"\breview(?:er)?(?:['’]s)?\b.{0,240}\b(?:found|finding|findings|issue|issues|"
    r"correction|corrections|flagged|reported|surfaced|identified|raised)\b"
    r"|\b(?:finding|findings|issue|issues)\b.{0,140}\breview(?:er)?\b"
    r"|\b(?:finding|findings|issue|issues)\b.{0,160}\b(?:surfaced|reported|identified|raised)\b",
    re.IGNORECASE | re.DOTALL,
)
_NEGATED_REVIEW_FINDING_PATTERN = re.compile(
    r"\b(?:no|without)\s+(?:independent\s+)?review\s+(?:has\s+run|findings?|issues?)\b"
    r"|\breview\s+(?:has\s+not|hasn't|did\s+not|didn't)\s+(?:happen|run|finish)\b"
    r"|\bno\s+(?:review\s+)?findings?\b",
    re.IGNORECASE,
)
_REVIEW_FINDING_ID_PATTERN = re.compile(
    r"\b(?:finding|issue)\b[^`\n]{0,140}?`([a-z0-9][a-z0-9_-]{4,})`"
    r"|\b(?:finding|issue)[ _-]?id\s*[:=]\s*[`\"']?([a-z0-9][a-z0-9_-]*)"
    r"|\b(?:finding|issue)\s*#([a-z0-9][a-z0-9_-]*)",
    re.IGNORECASE,
)
_REVIEW_DISPOSITION_ACTION_PATTERN = re.compile(
    r"\b(?:accept(?:ed|ing|ance)?|approv(?:e|es|ed|ing|al)|reject(?:ed|ing)?|"
    r"declin(?:e|ed|ing)|defer(?:red|ring)?|apply|applied|applying|"
    r"fix(?:es|ed|ing)?|repair(?:s|ed|ing)?|restructur(?:e|ed|ing)|"
    r"chang(?:e|ed|ing)|skip(?:s|ped|ping)|omit(?:s|ted|ting)|"
    r"leave|leaving|keep|keeping|want|need|needs|do|adjudicat(?:e|es|ed|ing))\b",
    re.IGNORECASE,
)
_REVIEW_DISPOSITION_TARGET_PATTERN = re.compile(
    r"\b(?:finding|findings|issue|issues|blocker|blockers|"
    r"correction|corrections|fix|fixes|as\s+is|as-is|current\s+behavior|"
    r"current\s+behaviour|restructure|choice|choices|option|options)\b",
    re.IGNORECASE,
)
_LETTERED_REVIEW_CHOICE_PATTERN = re.compile(
    r"(?m)^\s*(?:[-*]\s*)?(?:[A-Z]|[0-9]+)[.):]\s+\S+", re.IGNORECASE
)
_REVIEW_CHOICE_PROMPT_PATTERN = re.compile(
    r"\b(?:what\s+(?:do|would|should)\s+you\s+want|"
    r"what\s+should\s+i\s+do|needs?\s+your\s+choice|"
    r"reply\s+with\s+(?:a\s+)?(?:single|one)\s+(?:letter|number)|"
    r"choose\s+one|reply\s+[\"']?\d+[\"']?\s+(?:or|/)\s+[\"']?\d+[\"']?)\b",
    re.IGNORECASE,
)
_REVIEW_ALTERNATIVES_PATTERN = re.compile(
    r"\boption\s*(?:\(?[a-z]\)?|\d+)(?!\w)"
    r"|^\s*(?:[-*]\s*)?(?:[a-z]|\d+)[.):]\s+\S+"
    r"|\bshould\s+(?:i|we)\b[^?\n]{0,160}\bor\b[^?\n]{0,160}\?",
    re.IGNORECASE | re.MULTILINE,
)
_REVIEW_RECOMMENDATION_PATTERN = re.compile(
    r"\b(?:i\s+lean\s+towards?|i\s+(?:would\s+)?recommend|"
    r"what\s+i\s+recommend|(?:my\s+)?recommendation|recommended)\b"
    r"(?:\s+is)?[\s*(:-]*"
    r"(?:(?:choose|pick|select)\s+)?(?:option|choice)?[\s*(]*"
    r"(?P<label>[a-z]|\d+)(?!\w)",
    re.IGNORECASE,
)
_REVIEW_OFFERED_LABEL_PATTERN = re.compile(
    r"^\s*(?:[-*]\s*)?(?P<listed>[a-z]|\d+)[.):]\s+\S+"
    r"|\boption\s*\(?(?P<named>[a-z]|\d+)\)?(?!\w)",
    re.IGNORECASE | re.MULTILINE,
)
_DIAGNOSTIC_KIND_PATTERN = re.compile(
    r"\b(?:error\s+(?:output|text|class|message)|build\s+output|"
    r"(?:scratch|build|transform|runner)\s+(?:run\s+)?(?:logs?|traces?|diagnostics?)|"
    r"(?:failing|failed)\s+page|stack\s*trace|traceback|run\s+id)\b",
    re.IGNORECASE,
)
_DIAGNOSTIC_REQUEST_PATTERN = re.compile(
    r"\b(?:give|send|share|paste|show|provide)\s+(?:me\s+)?[^.!?\n]{0,130}"
    r"|\b(?:what\s+(?:would|could)\s+unblock|how\s+to\s+unblock|"
    r"i\s+need\s+(?:one\s+of\s+these|the|a)|what\s+i\s+need)\b"
    r".{0,420}",
    re.IGNORECASE | re.DOTALL,
)


def _explicit_review_choice(message: str, request_clause: str) -> bool:
    """Whether a live review ask selects among offered alternatives."""

    return bool(
        _REVIEW_ALTERNATIVES_PATTERN.search(_NON_PROSE.sub(" ", message))
        and (
            _REVIEW_CHOICE_PROMPT_PATTERN.search(request_clause)
            or re.search(r"\bplease\s+choose\s+one\b", request_clause, re.I)
            or re.search(
                r"\b(?:choose|pick|option|alternative|choice)s?\b"
                r"|\bwhich\b.{0,80}\b(?:finding|fix|review|option|choice)s?\b"
                r"|\bapprove\s*\([a-z]\)",
                request_clause,
                re.I,
            )
        )
    )


def _recommended_review_option(message: str, request_clause: str) -> str | None:
    """Read a named recommendation from this ask, never from prior context."""

    prose = _NON_PROSE.sub(" ", message)
    ask_offset = prose.rfind(request_clause)
    current_text = prose[:ask_offset] if ask_offset >= 0 else prose
    # A recommendation cannot make its own label an offered alternative.
    # Find labels in the choice list or addressed ask after masking the
    # recommendation phrase itself.
    offered_text = message
    for recommendation in reversed(list(_REVIEW_RECOMMENDATION_PATTERN.finditer(message))):
        offered_text = (
            offered_text[:recommendation.start()]
            + " " * (recommendation.end() - recommendation.start())
            + offered_text[recommendation.end():]
        )
    offered = {
        (match.group("listed") or match.group("named")).casefold()
        for match in _REVIEW_OFFERED_LABEL_PATTERN.finditer(offered_text)
    }
    for match in reversed(list(_REVIEW_RECOMMENDATION_PATTERN.finditer(current_text))):
        label = match.group("label")
        if label.casefold() not in offered:
            continue
        option = f"option {label.upper() if label.isalpha() else label}"
        if re.match(r"\s*\)?\s+for\s+both\b", current_text[match.end():], re.I):
            option += " for both findings"
        return option
    return None


def _declares_review_choice(answer: str, message: str) -> bool:
    """A declared repair answer can itself name one offered option."""

    selected = re.match(
        r"\s*(?:choose|pick|select)\s+(?:option|choice)\s*\(?([a-z]|\d+)\)?(?!\w)",
        answer,
        re.I,
    )
    return bool(
        selected is not None
        and re.search(
            rf"\b(?:option|choice)\s*\(?{re.escape(selected.group(1))}\)?(?!\w)",
            message,
            re.I,
        )
    )


def _requests_build_diagnostics(message: str) -> bool:
    """Recognize a request for local run evidence, never a source fact."""

    prose = _NON_PROSE.sub(" ", message)
    active = _active_request_clauses(message)
    if active:
        latest = active[-1]
        if _DIAGNOSTIC_KIND_PATTERN.search(latest):
            return True
        # A later, independent factual question owns the current ask even if
        # an earlier sentence requested logs or error text.
        if _FACTUAL_QUESTION_OPENER_PATTERN.match(latest):
            return False
    return any(
        _DIAGNOSTIC_KIND_PATTERN.search(candidate.group())
        for candidate in _DIAGNOSTIC_REQUEST_PATTERN.finditer(prose)
    )
_CORRECTION_INVITATION_PATTERN = re.compile(
    r"\bopen\s+to\s+your\s+correction\b",
    re.IGNORECASE,
)


def _review_disposition_request(message: str, context: str = "") -> str | None:
    """Find a current question that asks how to dispose of a review finding.

    Finding language in a recap is only context. The disposition verbs and
    target must occur in a clause that actually asks the operator, so a source
    or plan-approval question later in the same message cannot inherit a
    disposition from the recap.
    """

    prose = _NON_PROSE.sub(" ", message)
    review_context = "\n".join((prose, _NON_PROSE.sub(" ", context)))
    if (
        _REVIEW_FINDING_CONTEXT_PATTERN.search(review_context) is None
        and _REVIEW_FINDING_ID_PATTERN.search(message) is None
        and _REVIEW_FINDING_ID_PATTERN.search(context) is None
    ):
        return None
    for current_ask in _active_request_clauses(message):
        if _CONDITIONAL_REVISION_PATTERN.search(current_ask) is not None:
            continue
        if not solicits_operator(current_ask):
            continue
        if (
            _LETTERED_REVIEW_CHOICE_PATTERN.search(prose) is not None
            and _REVIEW_CHOICE_PROMPT_PATTERN.search(current_ask) is not None
        ):
            return current_ask
        actions = _REVIEW_DISPOSITION_ACTION_PATTERN.findall(current_ask)
        if not actions:
            continue
        has_alternative = bool(
            re.search(
                r"\b(?:or|versus|vs\.?|either|one\s+of)\b",
                current_ask,
                re.IGNORECASE,
            )
        )
        has_review_target = bool(_REVIEW_DISPOSITION_TARGET_PATTERN.search(current_ask))
        if has_alternative and len(actions) >= 2 and has_review_target:
            return current_ask
        if has_review_target and (
            re.search(r"\badjudicat(?:e|es|ed|ing)\b", current_ask, re.IGNORECASE)
            or re.search(
            r"\b(?:what|how|whether|should|would|could|can|do|does|may|shall)\b",
            current_ask,
            re.IGNORECASE,
            )
        ):
            return current_ask
    return None


def is_review_disposition_ask(message: str, context: str = "") -> bool:
    """Whether the current message explicitly asks how to handle a review finding.

    ``context`` may carry a finding reported on an earlier turn. This is a
    detector only; it does not choose or reveal a disposition answer.
    """

    if not isinstance(message, str):
        raise TypeError("agent message must be a string")
    if not isinstance(context, str):
        raise TypeError("matcher context must be a string")
    return _review_disposition_request(message, context) is not None


def review_finding_ids(message: str) -> tuple[str, ...]:
    """Return explicitly labeled finding identifiers from a review message."""

    if not isinstance(message, str):
        raise TypeError("agent message must be a string")
    return tuple(
        dict.fromkeys(
            value.casefold()
            for match in _REVIEW_FINDING_ID_PATTERN.finditer(message)
            for value in match.groups()
            if value
        )
    )

def asks_for_a_choice(message: str) -> bool:
    """Whether the agent is putting a decision to the operator."""

    if not isinstance(message, str):
        raise TypeError("agent message must be a string")
    return bool(CHOICE_PATTERN.search(_NON_PROSE.sub(" ", message)))


def solicits_operator(message: str) -> bool:
    """Whether the agent asked the operator for anything on this turn.

    Four independent signals, any of which is enough: an explicit question
    mark, an interrogative opening clause, a bare ``which`` opener, or one of
    the request phrases in :data:`SOLICITATION_PATTERN`. A status update that
    merely mentions approval in passing matches none of them, and neither does
    a line-head imperative -- see the note below :data:`SOLICITATION_PATTERN`
    for why that shape is not inferred.
    """

    if not isinstance(message, str):
        raise TypeError("agent message must be a string")
    prose = _NON_PROSE.sub(" ", message)
    return bool(
        "?" in prose
        or INTERROGATIVE_OPENER_PATTERN.match(prose)
        or SOLICITING_OPENER_PATTERN.match(prose)
        or SOLICITATION_PATTERN.search(prose)
    )

_RULES = (
    # For non-approval asks this remains first-match-wins within the addressed
    # request clauses, with source lookup taking precedence over broader
    # question/status rules. Recap vocabulary is never a source-question trigger.
    _Rule(
        "source.question",
        Category.SOURCE_QUESTION,
        re.compile(
            r"\b(source|data|field|column|endpoint|resource|record|row|input|table|where\s+did)\b",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        "approval.request",
        Category.APPROVAL_REQUEST,
        APPROVAL_REQUEST_PATTERN,
    ),
    # Weaker, more ambiguous approval vocabulary, kept under its own rule id so
    # a transcript reader can tell which of the two fired.
    _Rule(
        "approval.proceed",
        Category.APPROVAL_REQUEST,
        re.compile(r"\b(proceed|publish|ship)\b", re.IGNORECASE),
    ),
    _Rule(
        "decision.request",
        Category.DECISION_REQUEST,
        re.compile(r"\b(choose|which|should\s+we|prefer|option|decision|decide|yes\s*/\s*no)\b|\?", re.IGNORECASE),
    ),
    _Rule(
        "status.query",
        Category.STATUS_QUERY,
        re.compile(r"\b(status|done|finished|finish|complete|where\s+are\s+we|what(?:'s|\s+is)\s+next)\b", re.IGNORECASE),
    ),
)


def _contains_term(message: str, terms: tuple[str, ...]) -> bool:
    return contains_any_term(message, terms)


def _contains_declared_term(value: str | bytes, terms: tuple[str, ...]) -> bool:
    """Check reachable text without making the global question vocabulary a leak rule."""

    if isinstance(value, bytes):
        lowered = value.lower()
        return any(term and term.casefold().encode("utf-8").lower() in lowered for term in terms)
    return _contains_term(value, terms)


def _reachable_reply_material(persona: PersonaCard, answer_sheet: AnswerSheet) -> tuple[str, ...]:
    # A turn may be declared as a mapping carrying the substitution switch, so
    # take its text rather than the declaration: the obstacle scan must still
    # see every string that can actually reach the agent.
    values: list[str] = [
        answer_sheet.opening_message,
        *(script_turn_text(turn) for turn in answer_sheet.turns),
        persona.fallback,
    ]
    values.extend(reply for category in sorted(persona.reply_bank) for reply in persona.reply_bank[category])
    values.extend(answer_sheet.source_answers.values())
    values.extend(
        text
        for answer in answer_sheet.decision_answers.values()
        for text in (answer.stages or (answer.answer,))
    )
    values.extend(answer_sheet.status_answers.values())
    values.extend(fact.fact for fact in answer_sheet.ground_truth.values())
    return tuple(values)


def validate_reachable_material(
    persona: PersonaCard,
    answer_sheet: AnswerSheet,
    *,
    extra_material: Iterable[str | bytes] = (),
    obstacle_terms: tuple[str, ...] | list[str] = (),
) -> None:
    """Reject any agent-visible string that names a scenario-declared obstacle."""

    declared = tuple(dict.fromkeys((*answer_sheet.obstacle_terms, *obstacle_terms)))
    for value in (*_reachable_reply_material(persona, answer_sheet), *tuple(extra_material)):
        if _contains_declared_term(value, declared):
            raise MatcherError("a fixed operator reply contains a planted obstacle term")


def validate_decision_reachability(
    answer_sheet: AnswerSheet,
    *,
    exhaustive: bool = False,
    probes_by_decision: Mapping[str, Iterable[str]] | None = None,
) -> None:
    """Check opt-in staged/overlay decisions against their eligible peers.

    Legacy sheets intentionally retain their historical overlap behavior in
    the default mode. New staged or overlay declarations opt into linting so
    a decision cannot be shadowed by an earlier sorted id after its gate is
    active. Package acceptance tests can set ``exhaustive=True`` and provide
    natural ``probes_by_decision`` to check every declared id without making
    the stricter contract a runtime change for older packages.
    """

    probes_by_decision = probes_by_decision or {}
    unknown_probe_ids = sorted(set(probes_by_decision) - set(answer_sheet.decision_answers))
    if unknown_probe_ids:
        raise MatcherError(
            "reachability probes name undeclared decision id(s): " + ", ".join(unknown_probe_ids)
        )
    for decision in answer_sheet.decision_answers.values():
        if not exhaustive and not (
            decision.is_staged
            or decision.available_after_overlay is not None
            or decision.retired_after_overlay is not None
        ):
            continue
        active_events = (
            (decision.available_after_event,)
            if decision.available_after_event is not None
            else ()
        )
        active_overlays = (
            (decision.available_after_overlay,)
            if decision.available_after_overlay is not None
            else ()
        )
        probes = tuple(probes_by_decision.get(decision.decision_id, ())) or (
            "Can you decide " + " and ".join(decision.terms) + "?",
        )
        if not probes or any(not isinstance(probe, str) or not probe.strip() for probe in probes):
            raise MatcherError(
                f"reachability probes for {decision.decision_id!r} must be non-empty strings"
            )
        for probe in probes:
            matched = answer_sheet.answer_for_decision(
                probe,
                available_event_ids=active_events,
                active_overlay_ids=active_overlays,
            )
            if matched is None or matched.decision_id != decision.decision_id:
                raise MatcherError(
                    f"decision {decision.decision_id!r} is unreachable after its declared gate for probe {probe!r}"
                )


class MatcherBank:
    """Classify messages and select only predeclared reply strings."""

    def __init__(
        self,
        persona: PersonaCard,
        answer_sheet: AnswerSheet,
        *,
        obstacle_terms: tuple[str, ...] | list[str] = (),
        extra_material: Iterable[str | bytes] = (),
    ) -> None:
        self.persona = persona
        self.answer_sheet = answer_sheet
        declared = tuple(dict.fromkeys((*answer_sheet.obstacle_terms, *obstacle_terms)))
        self.obstacle_terms = declared
        question_terms = tuple(dict.fromkeys((*DEFAULT_OBSTACLE_TERMS, *declared)))
        # A matching decision returned above is the only per-question exemption.
        self.question_obstacle_terms = question_terms
        self._known_decision_overlays = answer_sheet.decision_overlay_ids
        self._active_decision_overlays: list[str] = []
        validate_decision_reachability(answer_sheet)
        validate_reachable_material(
            persona,
            answer_sheet,
            extra_material=extra_material,
            obstacle_terms=obstacle_terms,
        )

    @property
    def active_decision_overlays(self) -> tuple[str, ...]:
        """Return active decision overlays in activation order."""

        return tuple(self._active_decision_overlays)

    def validate_decision_overlay(self, overlay_id: str) -> None:
        """Reject an unknown overlay without changing matcher state."""

        if not isinstance(overlay_id, str) or not overlay_id:
            raise MatcherError("decision overlay id must be a non-empty string")
        if overlay_id not in self._known_decision_overlays:
            raise MatcherError(f"undeclared decision overlay id: {overlay_id}")

    def activate_decision_overlay(self, overlay_id: str) -> None:
        """Activate one declared answer-sheet overlay idempotently.

        Chain controllers call this at the source-switch boundary. An overlay
        can expose revised answers and retire prefix decisions atomically from
        the matcher's point of view, without relying on a driver-facing event
        card or a hard-coded turn number.
        """

        self.validate_decision_overlay(overlay_id)
        if overlay_id not in self._active_decision_overlays:
            self._active_decision_overlays.append(overlay_id)

    def decision_is_available(
        self,
        decision_id: str,
        *,
        available_event_ids: tuple[str, ...] = (),
    ) -> bool:
        """Whether an already-selected answer remains live under current gates."""

        decision = self.answer_sheet.decision_answers.get(decision_id)
        if decision is None:
            return False
        return (
            (decision.available_after_event is None or decision.available_after_event in available_event_ids)
            and (decision.retired_after_event is None or decision.retired_after_event not in available_event_ids)
            and (
                decision.available_after_overlay is None
                or decision.available_after_overlay in self._active_decision_overlays
            )
            and (
                decision.retired_after_overlay is None
                or decision.retired_after_overlay not in self._active_decision_overlays
            )
        )

    def _decision_result(
        self,
        decision: DecisionAnswer,
        *,
        decision_stage_counts: Mapping[str, int],
        matched_request_clause: str | None = None,
    ) -> MatchResult:
        """Build a result using the next answer stage not already delivered."""

        decision_id = decision.decision_id
        reply, stage, final = decision.response_for_solicitation(
            decision_stage_counts.get(decision_id, 0) + 1
        )
        return MatchResult(
            Category.DECISION_REQUEST,
            f"decision.answer.{decision_id}",
            reply,
            decision_id=decision_id,
            matched_request_clause=matched_request_clause,
            decision_stage=stage,
            decision_final=final,
        )

    def _request_decision(
        self,
        clause: str,
        *,
        excluded_decision_ids: frozenset[str],
        available_event_ids: tuple[str, ...],
        active_overlay_ids: tuple[str, ...],
    ) -> DecisionAnswer | None:
        """Select the best declared decision for one actual request clause.

        The answer sheet's default lookup retains its established lexical
        order. For matcher routing only, a decision supported by more of its
        explicit terms outranks one that needs synonyms to capture incidental
        vocabulary in the same clause. Ties keep the answer sheet's existing
        event and lexical order. This lets "make a new workflow to handle the
        stage" resolve to the directly named workflow choice while leaving a
        later, distinct stage question eligible for its ruling. The caller
        limits this lookup to the current ask and its local option context.
        """

        matches: list[DecisionAnswer] = []
        excluded = set(excluded_decision_ids)
        while True:
            decision = self.answer_sheet.answer_for_decision(
                clause,
                excluded=frozenset(excluded),
                available_event_ids=available_event_ids,
                active_overlay_ids=active_overlay_ids,
            )
            if decision is None:
                break
            matches.append(decision)
            excluded.add(decision.decision_id)
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        lowered = clause.casefold()
        event_order = {
            event_id: index for index, event_id in enumerate(available_event_ids)
        }
        return max(
            matches,
            key=lambda decision: (
                event_order.get(decision.available_after_event, -1),
                sum(_decision_term_present(term, lowered) for term in decision.terms),
            ),
        )

    def _validate_replies(self) -> None:
        """Compatibility hook retained for callers that explicitly revalidate a bank."""

        validate_reachable_material(self.persona, self.answer_sheet, obstacle_terms=self.obstacle_terms)

    @staticmethod
    def has_review_finding_context(message: str) -> bool:
        """Whether a message explicitly reports a review finding."""

        if not isinstance(message, str):
            raise TypeError("agent message must be a string")
        prose = _NON_PROSE.sub(" ", message)
        if _NEGATED_REVIEW_FINDING_PATTERN.search(prose) is not None:
            return False
        return (
            _REVIEW_FINDING_CONTEXT_PATTERN.search(prose) is not None
            or _REVIEW_FINDING_ID_PATTERN.search(message) is not None
        )

    def validate_outgoing_message(self, message: str) -> None:
        """Validate composed text immediately before transport sends it.

        The empty-message check is an author-error guard: operator-driven
        paths already provide non-empty scripted text or matcher replies. It
        is not the screenshot/wrong-file replacement filter, which suppresses
        only an event card's text when its attachment replaces the message.
        """

        if not isinstance(message, str):
            raise TypeError("outgoing operator message must be a string")
        if not message.strip():
            raise MatcherError("the composed operator message must not be empty")
        if _contains_term(message, self.obstacle_terms):
            raise MatcherError("the composed operator message contains a planted obstacle term")

    def validate_generated_surface(self, message: str) -> None:
        """Apply the stricter no-obstacle guard to model-rendered operator text."""

        self.validate_outgoing_message(message)
        if _contains_term(message, self.question_obstacle_terms):
            raise MatcherError("the generated operator surface contains an obstacle term")

    @staticmethod
    def _with_approval_flag(result: MatchResult, message: str) -> MatchResult:
        """Attach both orthogonal message flags to an already-chosen result.

        ``classify`` and ``reply_for`` both funnel through here, so setting
        the flags in one place is what keeps them consistent between a
        classification and the reply chosen from it.
        """

        approval = result.approval_requested or bool(APPROVAL_REQUEST_PATTERN.search(message))
        asked = result.solicits_operator or solicits_operator(message)
        if approval == result.approval_requested and asked == result.solicits_operator:
            return result
        return replace(result, approval_requested=approval, solicits_operator=asked)

    def classify(
        self,
        message: str,
        *,
        context: str = "",
        excluded_decision_ids: frozenset[str] = frozenset(),
        available_event_ids: tuple[str, ...] = (),
        decision_stage_counts: Mapping[str, int] | None = None,
    ) -> MatchResult:
        """Return a stable category and rule id without selecting a reply."""

        if not isinstance(message, str):
            raise TypeError("agent message must be a string")
        if not isinstance(context, str):
            raise TypeError("matcher context must be a string")
        return self._with_approval_flag(
            self._classify(
                message,
                context=context,
                excluded_decision_ids=excluded_decision_ids,
                available_event_ids=available_event_ids,
                decision_stage_counts=decision_stage_counts or {},
            ),
            message,
        )

    def _classify(
        self,
        message: str,
        *,
        context: str = "",
        excluded_decision_ids: frozenset[str] = frozenset(),
        available_event_ids: tuple[str, ...] = (),
        decision_stage_counts: Mapping[str, int] | None = None,
    ) -> MatchResult:
        stage_counts = decision_stage_counts or {}
        active_overlays = tuple(self._active_decision_overlays)
        is_question = "?" in message or bool(INTERROGATIVE_OPENER_PATTERN.match(message))
        request_clauses = _active_request_clauses(message)
        request_text = " ".join(request_clauses)
        approval_clauses = [
            clause
            for clause in request_clauses
            if APPROVAL_REQUEST_PATTERN.search(clause)
            and _ADDRESSED_APPROVAL_ASK_PATTERN.search(clause)
        ]
        other_substantive_asks = any(
            _OTHER_ASK_TOPIC_PATTERN.search(clause)
            and clause not in approval_clauses
            and _CONDITIONAL_REVISION_PATTERN.search(clause) is None
            for clause in request_clauses
        )
        approval_context = bool(_APPROVAL_CONTEXT_PATTERN.search(request_text))
        if (
            not approval_context
            and request_clauses
            and re.search(r"\b(?:reply|confirm|respond)\b", request_clauses[-1], re.I)
        ):
            # "I cannot build without approval. Could you reply plainly?"
            # is one approval ask, even though the final sentence is
            # anaphoric. Keep the borrowed context inside that paragraph so
            # an earlier plan recap cannot supply an unrelated answer.
            prose = _NON_PROSE.sub(" ", message)
            ask_offset = prose.rfind(request_clauses[-1])
            if ask_offset >= 0:
                paragraph_start = prose.rfind("\n\n", 0, ask_offset) + 2
                paragraph_end = prose.find("\n\n", ask_offset)
                if paragraph_end < 0:
                    paragraph_end = len(prose)
                approval_context = bool(
                    _APPROVAL_CONTEXT_PATTERN.search(prose[paragraph_start:paragraph_end])
                )
        explicit_approval_ask = bool(approval_clauses) or (
            approval_context and not other_substantive_asks
        )
        # A distinct factual/decision ask keeps the existing lookup behavior;
        # approval wins when it is the actual request, including a direct
        # "reply with approval" ask after a sentence explaining that consent
        # is the only blocker.
        approval_rule = (
            _approval_request_rule(" ".join(approval_clauses)) or "approval.request"
            if explicit_approval_ask else None
        )
        review_fix = self.answer_sheet.decision_answers.get("review_fix_authorization")
        if (
            review_fix is not None
            and not self.decision_is_available(
                review_fix.decision_id,
                available_event_ids=available_event_ids,
            )
        ):
            review_fix = None
        # The caller retains only reports of actual findings as context. A
        # hypothetical or negated review must not make a plan approval into
        # authorization to repair work that has never been reviewed.
        review_context = context if self.has_review_finding_context(context) else ""
        review_in_play = bool(review_context) or self.has_review_finding_context(message)
        review_choice_clause = next(
            (
                clause for clause in reversed(request_clauses)
                if _explicit_review_choice(message, clause)
            ),
            None,
        ) if review_in_play else None
        if review_choice_clause is not None:
            specific_choice = self._request_decision(
                _decision_lookup_text(message, review_choice_clause),
                excluded_decision_ids=excluded_decision_ids,
                available_event_ids=available_event_ids,
                active_overlay_ids=active_overlays,
            )
            alternatives = _referenced_options_text(message, review_choice_clause)
            if specific_choice is None and alternatives is not None:
                specific_choice = self._request_decision(
                    alternatives,
                    excluded_decision_ids=excluded_decision_ids,
                    available_event_ids=available_event_ids,
                    active_overlay_ids=active_overlays,
                )
                if specific_choice is None:
                    partial = [
                        decision
                        for decision in self.answer_sheet.decision_answers.values()
                        if decision.decision_id not in excluded_decision_ids
                        and decision.decision_id != "review_fix_authorization"
                        and self.decision_is_available(
                            decision.decision_id,
                            available_event_ids=available_event_ids,
                        )
                        and (
                            decision.available_after_overlay is None
                            or decision.available_after_overlay in active_overlays
                        )
                        and (
                            decision.retired_after_overlay is None
                            or decision.retired_after_overlay not in active_overlays
                        )
                        and any(
                            _decision_term_present(term, alternatives.casefold())
                            for term in decision.terms
                        )
                    ]
                    if len(partial) == 1:
                        specific_choice = partial[0]
            if specific_choice is not None and specific_choice.decision_id != "review_fix_authorization":
                return self._decision_result(
                    specific_choice,
                    decision_stage_counts=stage_counts,
                    matched_request_clause=review_choice_clause,
                )
            if (
                review_fix is not None
                and review_fix.decision_id not in excluded_decision_ids
                and _declares_review_choice(review_fix.answer, message)
            ):
                return self._decision_result(
                    review_fix,
                    decision_stage_counts=stage_counts,
                    matched_request_clause=review_choice_clause,
                )
            return MatchResult(
                Category.DECISION_REQUEST,
                "review.choice_undeclared",
                self.persona.review_choice_reply(
                    _recommended_review_option(message, review_choice_clause)
                ),
                matched=False,
                matched_request_clause=review_choice_clause,
            )
        review_fix_request = (
            _review_fix_request(message, review_context) if review_in_play else None
        )
        if (
            review_fix is not None
            and review_fix_request is not None
            and solicits_operator(message)
        ):
            # A decision named in the actual repair question is more specific
            # than this generic authorization. For a pure "which option?"
            # choice, retain scenario-specific decisions described in the
            # finding; an explicit fix action still wins over recap terms.
            direct_finding_question = bool(
                _REVIEW_FIX_DIRECT_FINDING_QUESTION_PATTERN.search(review_fix_request)
                or _REVIEW_OUTPUT_ADDITION_PATTERN.search(review_fix_request)
            )
            specific = self.answer_sheet.answer_for_decision(
                _decision_lookup_text(message, review_fix_request),
                excluded=excluded_decision_ids,
                available_event_ids=available_event_ids,
                active_overlay_ids=active_overlays,
            )
            if (
                specific is not None
                and specific.decision_id != "review_fix_authorization"
                and not direct_finding_question
            ):
                return self._decision_result(
                    specific,
                    decision_stage_counts=stage_counts,
                    matched_request_clause=review_fix_request,
                )
            return self._decision_result(
                review_fix,
                decision_stage_counts=stage_counts,
                matched_request_clause=review_fix_request,
            )

        # A review can ask for a disposition that is not authorization to
        # apply corrections (for example, accept an existing behavior or
        # restructure it). Keep that explicit choice out of the source and
        # plan-approval routes. If no declared decision covers it, the
        # operator returns its ordinary unknown-decision response rather than
        # silently selecting an answer from recap vocabulary.
        review_disposition_request = (
            _review_disposition_request(message, review_context) if review_in_play else None
        )
        if review_disposition_request is not None and review_fix_request is None:
            disposition_decision = self.answer_sheet.answer_for_decision(
                review_disposition_request,
                excluded=excluded_decision_ids,
                available_event_ids=available_event_ids,
                active_overlay_ids=active_overlays,
            )
            if (
                disposition_decision is not None
                and disposition_decision.decision_id != "review_fix_authorization"
            ):
                return self._decision_result(
                    disposition_decision,
                    decision_stage_counts=stage_counts,
                    matched_request_clause=review_disposition_request,
                )
            if review_fix is not None:
                return self._decision_result(
                    review_fix,
                    decision_stage_counts=stage_counts,
                    matched_request_clause=review_disposition_request,
                )
            return MatchResult(
                Category.DECISION_REQUEST,
                "decision.request",
                "",
                matched=True,
                matched_request_clause=review_disposition_request,
            )

        # A declared decision is more specific than the generic approval
        # persona, but its complete term set must occur in one actual ask
        # clause. Combining separate requests could otherwise manufacture a
        # match from unrelated questions (for example, "approve PyYAML?" and
        # "approve the install?").
        request_decision = None
        request_decision_clause = None
        for clause in reversed(request_clauses):
            if _CONDITIONAL_REVISION_PATTERN.search(clause) is not None:
                continue
            request_decision = self._request_decision(
                _decision_lookup_text(message, clause),
                excluded_decision_ids=excluded_decision_ids,
                available_event_ids=available_event_ids,
                active_overlay_ids=active_overlays,
            )
            if request_decision is not None:
                request_decision_clause = clause
                break
        if request_decision is None:
            confirmation_text = _declared_confirmation_text(message)
            if confirmation_text is not None:
                request_decision = self._request_decision(
                    confirmation_text,
                    excluded_decision_ids=excluded_decision_ids,
                    available_event_ids=available_event_ids,
                    active_overlay_ids=active_overlays,
                )
                if request_decision is not None:
                    request_decision_clause = confirmation_text
        if request_decision is None and request_clauses:
            alternatives = _referenced_options_text(message, request_clauses[-1])
            if alternatives is not None:
                request_decision = self._request_decision(
                    alternatives,
                    excluded_decision_ids=excluded_decision_ids,
                    available_event_ids=available_event_ids,
                    active_overlay_ids=active_overlays,
                )
                if request_decision is None:
                    # The recap can abbreviate a previously enumerated choice.
                    # A single explicit term may identify it, but ambiguity
                    # must leave the operator asking for the decision instead.
                    partial = [
                        decision
                        for decision in self.answer_sheet.decision_answers.values()
                        if decision.decision_id not in excluded_decision_ids
                        and self.decision_is_available(
                            decision.decision_id,
                            available_event_ids=available_event_ids,
                        )
                        and (
                            decision.available_after_overlay is None
                            or decision.available_after_overlay in active_overlays
                        )
                        and (
                            decision.retired_after_overlay is None
                            or decision.retired_after_overlay not in active_overlays
                        )
                        and any(
                            _decision_term_present(term, alternatives.casefold())
                            for term in decision.terms
                        )
                    ]
                    if len(partial) == 1:
                        request_decision = partial[0]
                if request_decision is not None:
                    request_decision_clause = request_clauses[-1]
        if (
            request_decision is not None
            and request_decision.decision_id != "review_fix_authorization"
            and solicits_operator(message)
        ):
            return self._decision_result(
                request_decision,
                decision_stage_counts=stage_counts,
                matched_request_clause=request_decision_clause,
            )

        # An explicit approval question is decided by its ask clause. A
        # ground-truth or source term in an earlier recap must not turn it into
        # an unrelated factual answer (especially one already repeat-suppressed).
        if approval_rule is not None:
            correction_invitation_clause = next(
                (
                    clause
                    for clause in reversed(request_clauses)
                    if _CORRECTION_INVITATION_PATTERN.search(clause)
                ),
                None,
            )
            if correction_invitation_clause is not None:
                correction_decision = self.answer_sheet.answer_for_decision(
                    _decision_lookup_text(message, correction_invitation_clause),
                    excluded=excluded_decision_ids,
                    available_event_ids=available_event_ids,
                    active_overlay_ids=active_overlays,
                )
                if correction_decision is not None:
                    return self._decision_result(
                        correction_decision,
                        decision_stage_counts=stage_counts,
                        matched_request_clause=correction_invitation_clause,
                    )
            return MatchResult(
                Category.APPROVAL_REQUEST,
                approval_rule,
                "",
                matched_request_clause=(
                    next(reversed(approval_clauses))
                    if approval_clauses
                    else next(
                        (
                            clause
                            for clause in reversed(request_clauses)
                            if _APPROVAL_CONTEXT_PATTERN.search(clause)
                        ),
                        None,
                    )
                ),
            )

        # A scratch/build error is local run evidence. Source-answer nouns in
        # the same request (page, record, data) do not make it source data.
        if _requests_build_diagnostics(message):
            return MatchResult(
                Category.OTHER,
                "persona.diagnostic_request",
                self.persona.replies_for("diagnostic_request")[0],
                matched=False,
                solicits_operator=True,
                matched_request_clause=request_clauses[-1] if request_clauses else None,
            )

        decision = request_decision
        # A decision answer is an operator response, not a keyword-triggered
        # status line. Require an actual solicitation so a report such as
        # "no review finding was reported" cannot consume a later decision.
        if (
            decision is not None
            and decision.decision_id != "review_fix_authorization"
            and solicits_operator(message)
        ):
            return self._decision_result(
                decision,
                decision_stage_counts=stage_counts,
                matched_request_clause=(
                    request_decision_clause
                    or next(
                        (clause for clause in request_clauses if solicits_operator(clause)),
                        None,
                    )
                ),
            )
        # A direct choice is about the requested action even when the agent's
        # recap mentions a source row or table. Broad closing questions retain
        # the ordinary rule bank, but source facts require source wording in an
        # actual request clause.
        choice_clause = next(
            (
                clause
                for clause in reversed(request_clauses)
                if _CONDITIONAL_REVISION_PATTERN.search(clause) is None
                and _DIRECT_CHOICE_PATTERN.search(clause)
            ),
            None,
        )
        if (
            choice_clause is not None
            and solicits_operator(choice_clause)
            and self.answer_sheet.answer_for_source(choice_clause) is not None
        ):
            return MatchResult(
                Category.SOURCE_QUESTION,
                "source.question",
                "",
                matched=True,
                matched_request_clause=choice_clause,
            )
        if choice_clause is not None and solicits_operator(choice_clause):
            return MatchResult(
                Category.DECISION_REQUEST,
                "decision.request",
                "",
                matched=True,
                matched_request_clause=choice_clause,
            )
        source_clause = request_clauses[-1] if request_clauses else None
        if (
            source_clause is not None
            and solicits_operator(source_clause)
            and (
                self.answer_sheet.answer_for_source(source_clause) is not None
                or self.answer_sheet.answer_for_ground_truth(source_clause) is not None
            )
        ):
            return MatchResult(
                Category.SOURCE_QUESTION,
                "source.question",
                "",
                matched=True,
                matched_request_clause=source_clause,
            )
        if source_clause is not None and solicits_operator(source_clause):
            list_item = _numbered_list_item_text(message, source_clause)
            if list_item is not None:
                list_decision = self.answer_sheet.answer_for_decision(
                    list_item,
                    excluded=excluded_decision_ids,
                    available_event_ids=available_event_ids,
                    active_overlay_ids=active_overlays,
                )
                if list_decision is not None:
                    return self._decision_result(
                        list_decision,
                        decision_stage_counts=stage_counts,
                        matched_request_clause=source_clause,
                    )
        if is_question and _contains_term(message, self.question_obstacle_terms):
            return MatchResult(
                Category.OTHER,
                "fallback.no-leading",
                self.persona.no_leading_fallback,
                matched=False,
                obstacle_question=True,
            )
        for rule in _RULES:
            # Preserve the legacy classification of a standalone source
            # statement. When there is an addressed ask, only its clauses are
            # classified; reply_for separately limits factual lookup to the
            # matched current request, so recap terms cannot provide facts.
            routing_text = request_text or message
            if rule.pattern.search(routing_text):
                matched_clause = next(
                    (
                        clause
                        for clause in reversed(request_clauses)
                        if rule.pattern.search(clause)
                    ),
                    None,
                )
                return MatchResult(
                    rule.category,
                    rule.rule_id,
                    "",
                    matched=True,
                    matched_request_clause=matched_clause,
                )
        return MatchResult(Category.OTHER, "fallback.no-leading", self.persona.no_leading_fallback, matched=False)

    def reply_for(
        self,
        message: str,
        *,
        context: str = "",
        excluded_decision_ids: frozenset[str] = frozenset(),
        available_event_ids: tuple[str, ...] = (),
        decision_stage_counts: Mapping[str, int] | None = None,
    ) -> MatchResult:
        """Classify one message and choose its fixed reply."""

        if not isinstance(context, str):
            raise TypeError("matcher context must be a string")
        return self._with_approval_flag(
            self._reply_for(
                message,
                context=context,
                excluded_decision_ids=excluded_decision_ids,
                available_event_ids=available_event_ids,
                decision_stage_counts=decision_stage_counts,
            ),
            message,
        )

    def _reply_for(
        self,
        message: str,
        *,
        context: str = "",
        excluded_decision_ids: frozenset[str] = frozenset(),
        available_event_ids: tuple[str, ...] = (),
        decision_stage_counts: Mapping[str, int] | None = None,
    ) -> MatchResult:
        classified = self.classify(
            message,
            context=context,
            excluded_decision_ids=excluded_decision_ids,
            available_event_ids=available_event_ids,
            decision_stage_counts=decision_stage_counts,
        )
        if classified.category is Category.OTHER:
            return classified
        if classified.rule_id == "review.choice_undeclared":
            return classified
        if classified.category is Category.DECISION_REQUEST and classified.decision_id is not None:
            return classified
        request_text = " ".join(_active_request_clauses(message))
        lookup_text = classified.matched_request_clause or request_text or message
        if classified.category is Category.SOURCE_QUESTION:
            if (
                classified.matched_request_clause is None
                or not solicits_operator(classified.matched_request_clause)
            ):
                bank = self.persona.replies_for(classified.category.value)
                return MatchResult(
                    classified.category,
                    f"persona.{classified.category.value}",
                    bank[0],
                    matched=False,
                    matched_request_clause=classified.matched_request_clause,
                )
            # The brief is consulted before the source answers, not only after
            # them. A ground-truth fact fires only when its *whole* declared
            # term set is present, so a matching fact is strictly more specific
            # than a source answer, which fires on a single topic key name.
            # Consulting the sheet first let one generic key ("data") shadow
            # every specific fact an author added precisely because the source
            # answer was the wrong answer to that question. Scenarios that
            # declare no brief are unaffected: an empty mapping never matches.
            found = self.answer_sheet.answer_for_ground_truth(lookup_text)
            if found is not None:
                key, fact = found
                return MatchResult(
                    Category.SOURCE_QUESTION,
                    f"ground_truth.{key}",
                    fact,
                    answer_key=key,
                    ground_truth=True,
                    matched_request_clause=classified.matched_request_clause,
                )
            source = self.answer_sheet.answer_for_source(lookup_text)
            if source is not None:
                key, answer = source
                return MatchResult(
                    Category.SOURCE_QUESTION,
                    f"source.answer.{key}",
                    answer,
                    answer_key=key,
                    matched_request_clause=classified.matched_request_clause,
                )
            return self._unmatched(classified, message, lookup_text=lookup_text)
        if classified.category is Category.STATUS_QUERY:
            status = self.answer_sheet.answer_for_status(lookup_text)
            if status is not None:
                key, answer = status
                return MatchResult(
                    Category.STATUS_QUERY,
                    f"status.answer.{key}",
                    answer,
                    answer_key=key,
                    matched_request_clause=classified.matched_request_clause,
                )
            return self._unmatched(classified, message, lookup_text=lookup_text)
        if classified.category is Category.DECISION_REQUEST:
            if (
                classified.matched_request_clause is not None
                and _FACTUAL_CHOICE_QUESTION_PATTERN.search(
                    classified.matched_request_clause
                )
            ):
                fact = self.answer_sheet.answer_for_ground_truth(
                    _decision_lookup_text(
                        message, classified.matched_request_clause
                    )
                )
                if fact is not None:
                    key, answer = fact
                    return MatchResult(
                        Category.SOURCE_QUESTION,
                        f"ground_truth.{key}",
                        answer,
                        answer_key=key,
                        ground_truth=True,
                        matched_request_clause=classified.matched_request_clause,
                    )
            if (
                classified.matched
                and classified.matched_request_clause is not None
                and "?" not in classified.matched_request_clause
                and re.match(r"\s*which\b", classified.matched_request_clause, re.I)
                and re.search(
                    r"\bshould\s+i\s+(?:use|choose|select)\b",
                    classified.matched_request_clause,
                    re.I,
                )
            ):
                bank = self.persona.replies_for(classified.category.value)
                return MatchResult(
                    classified.category,
                    f"persona.{classified.category.value}",
                    bank[0],
                    matched=True,
                    matched_request_clause=classified.matched_request_clause,
                )
            if self.answer_sheet.ground_truth:
                return MatchResult(
                    classified.category,
                    f"unmatched.{classified.category.value}",
                    self.persona.no_leading_fallback,
                    matched=False,
                    matched_request_clause=classified.matched_request_clause,
                )
            bank = self.persona.replies_for(classified.category.value)
            return MatchResult(
                classified.category,
                f"persona.{classified.category.value}",
                bank[0],
                matched=False,
                matched_request_clause=classified.matched_request_clause,
            )
        # APPROVAL_REQUEST has no declared-fact lookup: whether to approve is
        # a persona behavioral choice, not a fact a ground-truth brief holds.
        bank = self.persona.replies_for(classified.category.value)
        return MatchResult(
            classified.category,
            f"persona.{classified.category.value}",
            bank[0],
            matched_request_clause=classified.matched_request_clause,
        )

    def _unmatched(
        self, classified: MatchResult, message: str, *, lookup_text: str | None = None
    ) -> MatchResult:
        """Resolve a factual category with no declared answer-sheet match.

        No ``ground_truth`` brief declared (the common, legacy case) keeps
        the exact prior behavior byte-for-byte: the persona's own stock line
        for that category, reported unmatched. A declared brief is consulted
        first and, when it covers the question, answered from it — a real
        fact, never fabricated. Only when neither the answer sheet nor the
        brief covers the question does the operator fall back to its fixed,
        never-leading "I don't know, you tell me" line: this is the one path
        that must never produce a confidently wrong or confidently empty
        scripted answer.
        """

        if not self.answer_sheet.ground_truth:
            bank = self.persona.replies_for(classified.category.value)
            return MatchResult(
                classified.category,
                f"persona.{classified.category.value}",
                bank[0],
                matched=False,
                matched_request_clause=classified.matched_request_clause,
            )
        candidate = lookup_text or message
        found = self.answer_sheet.answer_for_ground_truth(candidate)
        if (
            found is None
            and candidate != message
            and classified.category is not Category.SOURCE_QUESTION
        ):
            found = self.answer_sheet.answer_for_ground_truth(message)
        if found is not None:
            key, fact = found
            return MatchResult(
                classified.category,
                f"ground_truth.{key}",
                fact,
                answer_key=key,
                ground_truth=True,
                matched_request_clause=classified.matched_request_clause,
            )
        return MatchResult(
            classified.category,
            f"unmatched.{classified.category.value}",
            self.persona.no_leading_fallback,
            matched=False,
            matched_request_clause=classified.matched_request_clause,
        )


def classify_and_reply(
    message: str,
    persona: PersonaCard,
    answer_sheet: AnswerSheet,
    *,
    obstacle_terms: tuple[str, ...] | list[str] = (),
) -> MatchResult:
    """Convenience wrapper for one deterministic match."""

    return MatcherBank(persona, answer_sheet, obstacle_terms=obstacle_terms).reply_for(message)


__all__ = [
    "APPROVAL_REQUEST_PATTERN",
    "Category",
    "DEFAULT_OBSTACLE_TERMS",
    "CHOICE_PATTERN",
    "INTERROGATIVE_OPENER_PATTERN",
    "SOLICITATION_PATTERN",
    "SOLICITING_OPENER_PATTERN",
    "MatchResult",
    "MatcherBank",
    "MatcherError",
    "asks_for_a_choice",
    "classify_and_reply",
    "is_review_disposition_ask",
    "review_finding_ids",
    "solicits_operator",
    "validate_decision_reachability",
]

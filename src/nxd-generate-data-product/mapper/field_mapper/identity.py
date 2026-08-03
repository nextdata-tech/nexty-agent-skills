"""Row identity and the four identifiers. CONTRACT.md §5.

Split out of `spec.py` because row identity is consumed by four modules —
records, resolver, validate, ledger — and leaving the derivation inside the spec
module invites the drift where the resolver derives a key one way and the record
writer another. Row identity is the contract's load-bearing primitive.

All digests are sha256, lowercase hex, truncated to `DIGEST_CHARS` for column
width, with the full digest available for the ledger.

Pure stdlib. Must not import transport, anthropic, or the spec module.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from typing import Any

from .errors import SpecError

__all__ = [
    "DIGEST_CHARS",
    "NULL_SENTINEL",
    "digest",
    "full_digest",
    "canonical_json",
    "normalize_text",
    "new_execution_id",
    "value_hash",
    "target_row_key",
    "input_snapshot_id",
    "observation_id",
    "evidence_digest",
]

#: Column-width truncation for landed identifier columns. The ledger keeps the
#: full 64-char digest; landed models keep this prefix.
DIGEST_CHARS = 32

#: Type-tagged null encoding. CONTRACT.md §5: "null values hash the type-tagged
#: null, not the empty string." Without this, a null string and an empty string
#: hash identically and a review bound to one silently applies to the other.
NULL_SENTINEL = "\x00null\x00"


def full_digest(payload: str | bytes) -> str:
    """sha256 over UTF-8 bytes, full 64-char lowercase hex."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def digest(payload: str | bytes) -> str:
    """`full_digest` truncated to `DIGEST_CHARS` for a landed column."""
    return full_digest(payload)[:DIGEST_CHARS]


def canonical_json(value: Any) -> str:
    """Deterministic JSON: keys sorted at every level, no incidental whitespace.

    `sort_keys=True` is the load-bearing argument. Without it, dict iteration
    order leaks into the digest and an identical spec hashes differently between
    runs — which would auto-invalidate every human review at random.

    `ensure_ascii=False` keeps non-ASCII as real characters so the digest is
    stable regardless of the escaping policy of whatever wrote the source.
    """
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_fallback,
    )


def _json_fallback(value: Any) -> Any:
    """Last-resort encoder for types json doesn't know.

    Deliberately narrow: anything reaching here is a bug in the caller, and a
    silent `str()` of an arbitrary object would produce a digest containing a
    memory address (`<object at 0x7f...>`) — nondeterministic across runs, which
    is precisely the class of defect §5's exclusion list exists to prevent.
    """
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(
        f"non-canonicalizable value of type {type(value).__name__!r} reached a "
        "digest input; convert it to a primitive in the caller"
    )


_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Whitespace/case normalization — the ONLY normalization ever applied.

    CONTRACT.md §2.3 and design §5 are explicit and this function is where that
    promise is kept: collapse runs of whitespace, strip ends, casefold. Never
    fuzzy, never edit-distance, never embedding similarity. Fuzzy matching is
    exactly where the teeth fall out — a substring check that tolerates
    paraphrase stops catching fabrication.

    NFKC first so that visually identical text with different Unicode encodings
    (non-breaking space, full-width punctuation) normalizes consistently rather
    than producing a spurious `verify_failed`.
    """
    normalized = unicodedata.normalize("NFKC", text)
    return _WHITESPACE_RUN.sub(" ", normalized).strip().casefold()


def new_execution_id() -> str:
    """Explicitly nondeterministic, harness-supplied execution identity.

    NEVER a business primary key, never part of a uniqueness assert, never a
    partition key on a landed model. It exists to join to the ledger.
    """
    return str(uuid.uuid4())


def value_hash(value_type: str, value: Any) -> str:
    """sha256 over `(value_type, canonical value encoding)`.

    Stable for null: hashes the type-tagged null. This is the review-binding
    primitive — if it moves, every review bound to the old value correctly goes
    stale, so its encoding must not drift for incidental reasons.
    """
    encoded = NULL_SENTINEL if value is None else canonical_json(value)
    return digest(f"{value_type}\x1f{encoded}")


def target_row_key(
    identity_values: dict[str, Any],
    *,
    source_locators: dict[str, Any] | None = None,
    ordinal: int | None = None,
) -> str:
    """Content/source-derived row identity. Emission ordinal is display-only.

    Design §3: run 1 emits `[Acme, Nextdata]`; run 2 reverses them, and
    `candidate-01` now denotes a different employment record — the uniqueness
    assert still passes while reviews attach to the wrong row. So the key is
    derived from content, never from position.

    `ordinal` participates ONLY under `duplicate_policy = ordinal_suffix`, and
    the spec layer is what decides to pass it. Callers that pass an ordinal are
    accepting that reordering the source changes the key and mass-invalidates
    reviews (CONTRACT.md open question 8).
    """
    if not identity_values:
        raise SpecError(
            "target_row_key requires at least one identity field; a spec that "
            "cannot define stable row identity is rejected"
        )
    # Null identity values are not an acceptable key component: two rows both
    # missing the same identity field would collide into one key and silently
    # merge distinct entities. Reject loudly instead.
    missing = sorted(k for k, v in identity_values.items() if v is None or v == "")
    if missing:
        raise SpecError(
            f"identity fields {missing} are null/empty; row identity is "
            "under-determined and would collide with any other such row"
        )
    # Identity values are normalized on whitespace/case before hashing. Without
    # this, a trailing space or a case change in the source mints a NEW row key
    # for the same entity, silently orphaning every human review bound to the
    # old one — the review-misbinding failure design §3 exists to prevent. The
    # normalization is the same whitespace/case-only rule used for evidence
    # matching: never fuzzy, so two genuinely different employers never collide.
    payload: dict[str, Any] = {"identity": _normalize_components(identity_values)}
    if source_locators:
        payload["locators"] = _normalize_components(source_locators)
    if ordinal is not None:
        payload["ordinal"] = ordinal
    return digest(canonical_json(payload))


def _normalize_components(values: dict[str, Any]) -> dict[str, Any]:
    """Whitespace/case-normalize the string components of a key.

    Non-string components (ints, bools) pass through untouched: they have no
    incidental whitespace or case, and coercing them to text would let the
    integer 1 and the string "1" collide into one row key.
    """
    return {
        k: normalize_text(v) if isinstance(v, str) else v
        for k, v in values.items()
    }


def input_snapshot_id(identity_bearing_inputs: list[Any]) -> str:
    """Deterministic hash of what was read. Binds reviews.

    The caller passes inputs ALREADY in the spec's declared canonical sort
    order; this function does not re-sort, because the sort order is a spec
    decision and silently re-sorting here would mask a spec that failed to
    declare one.
    """
    return digest(canonical_json(identity_bearing_inputs))


def evidence_digest(evidence: list[dict[str, Any]]) -> str:
    """Digest over the evidence atoms of one cell, in citation order.

    Order is significant and deliberately not sorted: citation order is part of
    what the model asserted, so a reordering is a different observation.
    """
    return digest(canonical_json(evidence))


def observation_id(
    *,
    target_row_key_: str,
    field: str,
    value_hash_: str,
    evidence_digest_: str,
    response_hash: str,
) -> str:
    """Content hash of the observation itself.

    Two runs producing the same value from the same input with the same
    citations produce the same `observation_id` — which is what makes "did this
    rebuild actually change anything?" answerable without diffing values.
    """
    return digest(
        canonical_json(
            {
                "target_row_key": target_row_key_,
                "field": field,
                "value_hash": value_hash_,
                "evidence_digest": evidence_digest_,
                "response_hash": response_hash,
            }
        )
    )

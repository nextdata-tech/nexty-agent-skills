"""Append-only attempt ledger for the field mapper (CONTRACT.md §9).

One JSONL line per *attempt* — not per cell. A cell that took three validation
retries writes three lines, each with its own ``attempt_id`` and
``attempt_index``, and the proposal's ``attempt_id`` points at the final one.

What this module stores, and what it refuses to store
-----------------------------------------------------
It stores **hashes and controlled references**: prompt hash, wire-schema hash,
input *content* hash, response hash, the exact model snapshot echoed by
``response.model``, request parameters with secrets stripped, token usage,
latency, ``stop_reason``, outcome, and the resulting ``value_status``.

It refuses to store input content, base64 payloads, or quotes lifted from source
documents. At 10k x 1MB PDFs verbatim logging is ~10GB before responses, and —
worse than the size — it is a second uncontrolled copy of whatever PII was in
those documents. :func:`hash_payload` exists so callers can turn a payload into
a reference at the boundary and never hand the bytes to this module at all.

**Replay is parser/validator replay, and nothing more.**
:func:`replay_validation` re-runs a stored response through a parser/validator
callable. That tests the parser and the validator. It does **not** test a
changed prompt: the stored response was generated under the *old* prompt, so
feeding it to a new prompt's validator measures nothing about how the new prompt
would actually behave. Prompt-quality comparison — the entire Layer-2 loop —
requires live calls and costs real money. Any claim that prompt iteration is
free is false. This module therefore exposes no function named or shaped like
``replay_prompt``, and adding one would be a contract violation rather than a
convenience.

Crash consistency
-----------------
Every line is written and flushed whole. A process killed mid-write can still
leave a torn final line, so :func:`read_attempts` detects a trailing
unparseable line, discards it, and reports it via
:attr:`LedgerScan.torn_final_line`. A torn line anywhere *other* than the end is
corruption rather than a crash, and raises.

The ledger is diagnostic, never authoritative. Nothing in the harness reads it
back to decide a value, a status, or whether work still needs doing — that state
lives in the landed records. Reading the ledger as resumable state is how a
partially-written run gets mistaken for a complete one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence, cast

__all__ = [
    "LEDGER_FILENAME",
    "AttemptRecord",
    "LedgerScan",
    "RunLedger",
    "SecretLeakError",
    "LedgerCorruptionError",
    "ReplayOutcome",
    "hash_payload",
    "hash_text",
    "truncate_digest",
    "read_attempts",
    "iter_attempts",
    "replay_validation",
]

LEDGER_FILENAME = "attempts.jsonl"

# Digest presentation matches CONTRACT.md §5: sha256, lowercase hex. Landed
# columns truncate to 32 chars; the ledger keeps the full digest, which is the
# point of "full digest in the ledger".
_TRUNCATED_DIGEST_LEN = 32

# Keys whose values are secrets by name, stripped from request parameters before
# a line is written. Matched case-insensitively against the whole key.
_SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|auth|authorization|token|secret|password|credential|bearer)",
    re.IGNORECASE,
)

# Anthropic key shapes. Any occurrence in a serialized line is a hard failure —
# not a redaction, because a leak that gets quietly scrubbed teaches nobody that
# the caller is handing secrets to the ledger.
_KEY_PREFIXES = ("sk-ant-", "sk-ant-api", "sk_ant_")

_REDACTED = "<redacted>"


class SecretLeakError(RuntimeError):
    """A record was about to be written containing a credential.

    Raised *before* the write, so the secret never reaches the file. The message
    deliberately does not echo the offending value.
    """


class LedgerCorruptionError(RuntimeError):
    """The ledger file is unparseable somewhere other than a torn final line."""


def hash_text(text: str) -> str:
    """sha256 of UTF-8 text, lowercase hex, full digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_payload(payload: bytes) -> str:
    """sha256 of raw bytes, lowercase hex, full digest.

    Use this at the call boundary to convert a document, an image block, or any
    base64 payload into a reference *before* it would otherwise be handed to the
    ledger. The ledger stores the return value; it never sees ``payload``.
    """
    return hashlib.sha256(payload).hexdigest()


def truncate_digest(digest: str) -> str:
    """Column-width form of a digest (32 chars), for joining to landed rows."""
    return digest[:_TRUNCATED_DIGEST_LEN]


def _redact_params(params: Mapping[str, Any]) -> dict[str, Any]:
    """Strip secret-shaped keys from request parameters, recursively."""
    out: dict[str, Any] = {}
    for key, value in params.items():
        if _SECRET_KEY_PATTERN.search(str(key)):
            out[str(key)] = _REDACTED
        elif isinstance(value, Mapping):
            out[str(key)] = _redact_params(cast(Mapping[str, Any], value))
        elif isinstance(value, (list, tuple)):
            values: Sequence[Any] = cast(Sequence[Any], value)
            out[str(key)] = [
                (
                    _redact_params(cast(Mapping[str, Any], item))
                    if isinstance(item, Mapping)
                    else item
                )
                for item in values
            ]
        else:
            out[str(key)] = value
    return out


@dataclass(frozen=True)
class AttemptRecord:
    """One attempt. Serialized as exactly one JSONL line.

    Every field is a hash, an identifier, a count, or a controlled enum token.
    There is intentionally no field that can carry input content, a document
    quote, or a rendered prompt — the schema itself is the first line of defence
    against the "second PII store" failure.
    """

    execution_id: str
    attempt_id: str
    attempt_index: int
    target_row_key: str
    field_name: str

    mapper_spec_id: str
    input_snapshot_id: str

    prompt_hash: str
    wire_schema_hash: str
    input_content_hash: str

    model: str | None = None
    """Exact snapshot echoed by ``response.model`` — not the requested alias.

    Null only when the call never reached the API (blocked before dispatch).
    """

    api_version: str | None = None
    request_params: Mapping[str, Any] = field(
        default_factory=lambda: dict[str, Any]()
    )

    response_hash: str | None = None
    stop_reason: str | None = None

    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None

    outcome: str = "unknown"
    """``success`` | ``validation_failed`` | ``transport_error`` | ``refusal`` |
    ``schema_reject`` | ``skipped``."""

    value_status: str | None = None
    error_code: str | None = None
    harness_version: str | None = None

    provider: str = "anthropic"
    """Which provider dispatched this call.

    Recorded because a development provider (``claude_cli``) is NOT wire- or
    behaviour-equivalent to the API. Without this field an attempt made through a
    local CLI is indistinguishable from a real API attempt in the audit trail,
    which is precisely the confusion the provider seam exists to make impossible.
    """

    provider_notes: tuple[str, ...] = ()
    """Every way this response is not what the Anthropic API would have returned.

    Populated by the provider (missing schema enforcement, media sent as a file
    read rather than a content block, agent-loop turns, ignored effort). A reader
    deciding whether an attempt certifies anything needs these, so they travel with
    the attempt rather than living in a README.
    """

    def to_json_obj(self) -> dict[str, Any]:
        """Plain dict with secret-shaped request params already redacted."""
        return {
            "execution_id": self.execution_id,
            "attempt_id": self.attempt_id,
            "attempt_index": self.attempt_index,
            "target_row_key": self.target_row_key,
            "field": self.field_name,
            "mapper_spec_id": self.mapper_spec_id,
            "input_snapshot_id": self.input_snapshot_id,
            "prompt_hash": self.prompt_hash,
            "wire_schema_hash": self.wire_schema_hash,
            "input_content_hash": self.input_content_hash,
            "model": self.model,
            "api_version": self.api_version,
            "request_params": _redact_params(self.request_params),
            "response_hash": self.response_hash,
            "stop_reason": self.stop_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "outcome": self.outcome,
            "value_status": self.value_status,
            "error_code": self.error_code,
            "harness_version": self.harness_version,
            "provider": self.provider,
            "provider_notes": list(self.provider_notes),
        }


def _assert_no_secret(line: str, forbidden: Sequence[str]) -> None:
    """Fail before writing if a credential appears anywhere in the line.

    Two checks. The first catches the *known* key — the one this run actually
    holds — which is what a test greps for. The second catches any Anthropic-
    shaped key, including one that arrived from somewhere the harness does not
    know about (a stray env var interpolated into a param, say).
    """
    for secret in forbidden:
        if secret and secret in line:
            raise SecretLeakError(
                "refusing to write a ledger line containing the configured API "
                "key; the caller passed a credential into an attempt record"
            )
    lowered = line.lower()
    for prefix in _KEY_PREFIXES:
        if prefix in lowered:
            raise SecretLeakError(
                f"refusing to write a ledger line containing an {prefix!r}-shaped "
                "credential"
            )


#: Directory names that mark a path as an ephemeral run dir rather than a
#: durable location. One of these must appear in the path for a run dir under
#: the user's home to be accepted — see :meth:`RunLedger.__init__`.
_RUN_DIR_MARKERS = ("runs", "run", "tmp", "temp", "scratch", "var")


def _assert_ephemeral_run_dir(run_dir: Path) -> None:
    """Refuse a ledger path that is a durable location rather than a run dir.

    CONTRACT.md §9: the ledger lives under the **ephemeral run directory**,
    never the closure root, never ``~``. This is not hygiene — a ledger holds
    input hashes, token counts, and per-row identifiers for every attempt, so a
    ledger written into a closure is a durable artifact that a rebuild will not
    clean up and that a ``git add .`` will happily commit.

    The rule is deliberately narrow. A path outside the user's home is the
    caller's business (a CI runner's ``/tmp``, a container's workdir), so it
    passes. A path *at* the home directory itself, or directly under it with no
    run-dir marker anywhere in its parts, is refused: that is the shape a
    closure root or a stray ``~/ledger`` has.
    """
    try:
        resolved = run_dir.expanduser().resolve()
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        # No resolvable home (some sandboxes). Nothing to guard against.
        return

    if resolved == home:
        raise ValueError(
            "refusing to write the attempt ledger into the home directory "
            "itself; CONTRACT.md §9 requires an ephemeral run directory"
        )
    if home not in resolved.parents:
        return
    parts = {part.casefold() for part in resolved.parts}
    if parts.isdisjoint(_RUN_DIR_MARKERS):
        raise ValueError(
            f"refusing to write the attempt ledger to {resolved} — a path under "
            "the home directory with no run-dir component looks like a closure "
            "root, and a ledger there is a durable artifact a rebuild will not "
            f"clean up. Use a run-scoped dir (one of {_RUN_DIR_MARKERS} in the "
            "path), or a location outside the home directory."
        )


class RunLedger:
    """Append-only JSONL ledger scoped to one run directory.

    ``run_dir`` must be the **ephemeral run directory** — never the closure
    root, never ``~``. The constructor enforces this via
    :func:`_assert_ephemeral_run_dir`, because a ledger written into a closure
    is a durable PII-adjacent artifact that a rebuild will not clean up.

    Thread-safe: ``transport.py`` runs cells concurrently, and interleaved
    partial writes from two threads would produce exactly the torn lines this
    class otherwise guarantees against.
    """

    def __init__(
        self,
        run_dir: str | os.PathLike[str],
        *,
        execution_id: str,
        api_key: str | None = None,
        harness_version: str | None = None,
        filename: str = LEDGER_FILENAME,
    ) -> None:
        self.run_dir = Path(run_dir)
        _assert_ephemeral_run_dir(self.run_dir)
        self.execution_id = execution_id
        self.harness_version = harness_version
        self.path = self.run_dir / filename

        # The key is held only to assert it never appears. It is never written,
        # never logged, and deliberately not exposed as an attribute a repr
        # would pick up.
        self._forbidden: tuple[str, ...] = (api_key,) if api_key else ()
        self._lock = threading.Lock()
        self._count = 0

        self.run_dir.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        # Explicit: a default dataclass-style repr would happily print
        # self._forbidden into a traceback.
        return (
            f"RunLedger(path={str(self.path)!r}, "
            f"execution_id={self.execution_id!r}, attempts={self._count})"
        )

    @property
    def attempt_count(self) -> int:
        """Lines written by *this* instance. Not a read-back of the file."""
        return self._count

    def new_attempt_id(self) -> str:
        """Mint an attempt id. Nondeterministic by construction, like
        ``execution_id`` — it identifies an execution event, never a business
        row (CONTRACT.md §5)."""
        return uuid.uuid4().hex

    def record(self, attempt: AttemptRecord) -> str:
        """Append one attempt. Returns its ``attempt_id``.

        The line is serialized, checked for credentials, then written and
        flushed whole under a lock. If the credential check fires, nothing is
        written at all.
        """
        obj = attempt.to_json_obj()
        if obj.get("harness_version") is None and self.harness_version:
            obj["harness_version"] = self.harness_version
        # sort_keys makes lines diffable across runs; a stable field order is
        # what lets two ledgers be compared without a normalization pass.
        line = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
        _assert_no_secret(line, self._forbidden)

        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._count += 1
        return attempt.attempt_id


@dataclass(frozen=True)
class LedgerScan:
    """Result of reading a ledger back — for triage and cost accounting only."""

    attempts: tuple[dict[str, Any], ...]
    torn_final_line: bool
    """True when the last line was unparseable and was discarded.

    A crash mid-write is expected and recoverable; the discarded attempt simply
    did not complete. This flag exists so a caller can say so rather than
    silently under-count.
    """

    @property
    def total_input_tokens(self) -> int:
        return sum(int(a.get("input_tokens") or 0) for a in self.attempts)

    @property
    def total_output_tokens(self) -> int:
        return sum(int(a.get("output_tokens") or 0) for a in self.attempts)


def read_attempts(path: str | os.PathLike[str]) -> LedgerScan:
    """Read a ledger for triage. **Never** as authoritative harness state.

    A torn *final* line is discarded and flagged. A torn line anywhere else
    means the file was corrupted rather than truncated, and raises
    :class:`LedgerCorruptionError`.
    """
    ledger_path = Path(path)
    if not ledger_path.exists():
        return LedgerScan(attempts=(), torn_final_line=False)

    raw_lines = ledger_path.read_text(encoding="utf-8", errors="replace").splitlines()
    # A trailing newline yields no empty element from splitlines(), so any empty
    # string here is interior padding, not the tail.
    attempts: list[dict[str, Any]] = []
    torn = False
    last_index = len(raw_lines) - 1
    for index, raw in enumerate(raw_lines):
        if not raw.strip():
            continue
        try:
            attempts.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            if index == last_index:
                torn = True
                continue
            raise LedgerCorruptionError(
                f"{ledger_path}: unparseable line {index + 1} of {len(raw_lines)}; "
                "a torn line before the end is corruption, not a crash"
            ) from exc
    return LedgerScan(attempts=tuple(attempts), torn_final_line=torn)


def iter_attempts(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """Stream attempts one line at a time, without holding the file in memory.

    For a 10k-row run with retries the ledger is large enough that
    :func:`read_attempts` materializing every line at once is a real cost. This
    reads line by line instead.

    The torn-final-line rule is the same as :func:`read_attempts`: a trailing
    unparseable line is a crash mid-write and is discarded silently here (a
    generator has nowhere to hang a flag — call :func:`read_attempts` when you
    need to *know* the ledger was torn). A torn line anywhere earlier is
    corruption and raises.
    """
    ledger_path = Path(path)
    if not ledger_path.exists():
        return

    pending: dict[str, Any] | None = None
    pending_failed = False
    with ledger_path.open("r", encoding="utf-8", errors="replace") as handle:
        for lineno, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            # Emit the previous line only once we know it was not the last, so
            # a torn tail is dropped rather than raising.
            if pending_failed:
                raise LedgerCorruptionError(
                    f"{ledger_path}: unparseable line {lineno - 1}; a torn line "
                    "before the end is corruption, not a crash"
                )
            if pending is not None:
                yield pending
            try:
                pending, pending_failed = json.loads(raw), False
            except json.JSONDecodeError:
                pending, pending_failed = None, True
    if pending is not None:
        yield pending


@dataclass(frozen=True)
class ReplayOutcome:
    """One replayed attempt's parser/validator result."""

    attempt_id: str
    target_row_key: str
    field_name: str
    ok: bool
    detail: str | None = None


def replay_validation(
    attempts: Iterable[Mapping[str, Any]],
    responses: Mapping[str, str],
    validator: Callable[[str], tuple[bool, str | None]],
) -> tuple[ReplayOutcome, ...]:
    """Re-run stored responses through a parser/validator. Nothing more.

    ``responses`` maps ``attempt_id`` to the stored raw response text (which the
    caller keeps *outside* the ledger — the ledger holds only ``response_hash``).
    ``validator`` is the parse-and-check callable under test.

    **This tests the parser and the validator. It does not test a prompt.**
    Every response here was generated under whatever prompt was live when it was
    recorded. Running it against a validator written for a *new* prompt tells
    you the new validator can parse an old answer — which is worth knowing, and
    is not the same question as whether the new prompt produces better answers.
    Behavioral prompt comparison requires new live calls, at full cost.

    Attempts whose ``attempt_id`` is absent from ``responses`` are skipped
    rather than counted as failures: a missing stored response is a gap in the
    replay corpus, not a validator defect.
    """
    outcomes: list[ReplayOutcome] = []
    for attempt in attempts:
        attempt_id = str(attempt.get("attempt_id", ""))
        if attempt_id not in responses:
            continue
        try:
            ok, detail = validator(responses[attempt_id])
        except Exception as exc:  # a validator crash is a validator result
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        outcomes.append(
            ReplayOutcome(
                attempt_id=attempt_id,
                target_row_key=str(attempt.get("target_row_key", "")),
                field_name=str(attempt.get("field", "")),
                ok=ok,
                detail=detail,
            )
        )
    return tuple(outcomes)

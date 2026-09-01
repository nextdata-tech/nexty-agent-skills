"""Append-only per-run grant events and cumulative budget checking."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .grants import grant_identity, grant_scope, validate_widening

EVENTS_FILENAME = "grant-events.jsonl"
TRANSCRIPT_FILENAME = "provider-transcript.jsonl"
ATTEMPTS_FILENAME = "attempts.jsonl"
SUMMARY_FILENAME = "run-summary.json"
EVENTS_SCHEMA = "nxd-eval-grant-events-v1"
TRANSCRIPT_SCHEMA = "nxd-eval-provider-transcript-v1"
SUMMARY_SCHEMA = "nxd-eval-grant-run-summary-v1"


class GrantLedgerError(RuntimeError):
    """Raised when a provider call cannot be safely ledgered."""


@dataclass(frozen=True, slots=True)
class LedgerFinding:
    code: str
    detail: str
    run_dir: str | None = None
    grant_id: str | None = None


@dataclass(frozen=True, slots=True)
class GrantUsage:
    grant_id: str
    calls: int
    total_tokens: int | None
    total_usd: Decimal | None
    max_calls: int | None
    max_tokens: int | None
    max_usd: Decimal | None
    breached: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CumulativeBudgetReport:
    usage: Mapping[str, GrantUsage]
    findings: tuple[LedgerFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    @property
    def breached_grants(self) -> tuple[str, ...]:
        return tuple(grant_id for grant_id, item in self.usage.items() if item.breached)


def _decimal(value: Any, *, name: str, allow_none: bool = True) -> Decimal | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise GrantLedgerError(f"{name} must be a decimal amount, not a boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise GrantLedgerError(f"{name} is not a decimal amount: {value!r}") from exc
    if not result.is_finite() or result < 0:
        raise GrantLedgerError(f"{name} must be finite and non-negative")
    return result


def _tokens(value: Any, *, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GrantLedgerError(f"{name} must be a non-negative integer or null")
    return value


def _append(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_jsonl(path: Path, *, kind: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise GrantLedgerError(f"missing {kind}: {path}")
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            raise GrantLedgerError(f"blank {kind} line {line_number}: {path}")
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GrantLedgerError(f"invalid {kind} JSON at line {line_number}: {path}") from exc
        if not isinstance(item, Mapping):
            raise GrantLedgerError(f"{kind} line {line_number} is not an object: {path}")
        records.append(dict(item))
    return records


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _usage_from_response(response: Any) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, Mapping):
        usage = response.get("usage")
    if usage is None:
        return None, None
    if isinstance(usage, Mapping):
        return usage.get("input_tokens"), usage.get("output_tokens")
    return getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)


def _safe_response_tokens(value: Any, *, name: str) -> tuple[int | None, str | None]:
    """Normalize response usage without allowing a provider result to be lost."""

    try:
        return _tokens(value, name=name), None
    except GrantLedgerError as exc:
        return None, str(exc)


class GrantLedger:
    """One run's durable grant history and provider dispatch boundary."""

    def __init__(self, run_dir: str | Path, *, run_id: str, run_set_id: str = "default") -> None:
        if not run_id or "/" in run_id or "\\" in run_id:
            raise GrantLedgerError("run_id must be a non-empty path-independent identifier")
        if not run_set_id or "/" in run_set_id or "\\" in run_set_id:
            raise GrantLedgerError("run_set_id must be a non-empty path-independent identifier")
        self.run_dir = Path(run_dir).resolve()
        self.run_id = run_id
        self.run_set_id = run_set_id
        self.events_path = self.run_dir / EVENTS_FILENAME
        self.transcript_path = self.run_dir / TRANSCRIPT_FILENAME
        self.summary_path = self.run_dir / SUMMARY_FILENAME
        self._lock = threading.RLock()
        self._current: Any | None = None
        self._known: dict[str, Any] = {}
        self._calls: list[str] = []
        self._next_call = 1
        _append(
            self.events_path,
            {
                "schema": EVENTS_SCHEMA,
                "event": "run_started",
                "run_id": run_id,
                "run_set_id": run_set_id,
            },
        )

    @property
    def current_grant(self) -> Any:
        if self._current is None:
            raise GrantLedgerError("no grant has been installed for this run")
        return self._current

    def issue(self, grant: Any, *, turn: int = 0) -> str:
        with self._lock:
            if self._current is not None:
                raise GrantLedgerError("a run can issue only one initial grant")
            identity = grant_identity(grant)
            self._known[identity] = grant
            self._current = grant
            _append(
                self.events_path,
                {
                    "schema": EVENTS_SCHEMA,
                    "event": "grant_issued",
                    "run_id": self.run_id,
                    "run_set_id": self.run_set_id,
                    "turn": turn,
                    "grant_id": identity,
                    "grant": grant_scope(grant),
                },
            )
            return identity

    def expand(self, replacement: Any, *, turn: int, justification: str) -> tuple[str, str]:
        with self._lock:
            previous = self.current_grant
            if self._current is not previous:
                raise GrantLedgerError("grant ledger state changed unexpectedly")
            validate_widening(previous, replacement)
            previous_id = grant_identity(previous)
            replacement_id = grant_identity(replacement)
            if replacement_id in self._known:
                raise GrantLedgerError("a grant identity may be expanded only once")
            self._known[replacement_id] = replacement
            _append(
                self.events_path,
                {
                    "schema": EVENTS_SCHEMA,
                    "event": "grant_expanded",
                    "run_id": self.run_id,
                    "run_set_id": self.run_set_id,
                    "turn": turn,
                    "justification": justification,
                    "previous_grant_id": previous_id,
                    "grant_id": replacement_id,
                    "previous_grant": grant_scope(previous),
                    "grant": grant_scope(replacement),
                },
            )
            self._current = replacement
            return previous_id, replacement_id

    def dispatch(
        self,
        grant: Any,
        provider_call: Callable[..., Any],
        *args: Any,
        turn: int = 0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        usd: Decimal | str | int | float | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Dispatch through this ledger and record one call in a ``finally`` path.

        The provider callable may be the upstream recorded-provider callable;
        this wrapper is the seam that keeps replayed responses accounted for.
        Spend is intentionally caller-supplied because pricing belongs to the
        provider/runtime and must not be guessed by the eval harness.
        """

        with self._lock:
            if self._current is None or grant_identity(self._current) != grant_identity(grant):
                raise GrantLedgerError("provider call used a grant that is not active at this turn")
            grant_id = grant_identity(grant)
            if grant_id not in self._known:
                raise GrantLedgerError("provider call used a grant not recorded in this run")
            call_id = f"{self.run_id}:call-{self._next_call}"
            self._next_call += 1
            if isinstance(turn, bool) or not isinstance(turn, int) or turn < 0:
                raise GrantLedgerError("provider call turn must be a non-negative integer")
            explicit_input = _tokens(input_tokens, name="input_tokens")
            explicit_output = _tokens(output_tokens, name="output_tokens")
            explicit_usd = _decimal(usd, name="usd")
            _append(
                self.events_path,
                {
                    "schema": EVENTS_SCHEMA,
                    "event": "provider_call_reserved",
                    "run_id": self.run_id,
                    "run_set_id": self.run_set_id,
                    "call_id": call_id,
                    "grant_id": grant_id,
                    "turn": turn,
                },
            )
            _append(
                self.transcript_path,
                {
                    "schema": TRANSCRIPT_SCHEMA,
                    "event": "provider_call_started",
                    "run_id": self.run_id,
                    "run_set_id": self.run_set_id,
                    "call_id": call_id,
                    "grant_id": grant_id,
                    "turn": turn,
                },
            )

        response: Any = None
        error_type: str | None = None
        try:
            response = provider_call(*args, **kwargs)
            return response
        except BaseException as exc:
            error_type = type(exc).__name__
            raise
        finally:
            usage_errors: list[str] = []
            try:
                response_input, response_output = _usage_from_response(response)
            except Exception as exc:  # provider response adapters are outside this package's control
                response_input = response_output = None
                usage_errors.append(f"could not read provider usage: {exc}")
            final_input = explicit_input if explicit_input is not None else response_input
            final_output = explicit_output if explicit_output is not None else response_output
            final_input, input_error = _safe_response_tokens(final_input, name="input_tokens")
            final_output, output_error = _safe_response_tokens(final_output, name="output_tokens")
            usage_errors.extend(error for error in (input_error, output_error) if error is not None)
            record = {
                "schema": TRANSCRIPT_SCHEMA,
                "event": "provider_call",
                "run_id": self.run_id,
                "run_set_id": self.run_set_id,
                "call_id": call_id,
                "grant_id": grant_id,
                "turn": turn,
                "provider": provider or getattr(grant, "provider", ""),
                "model": model or getattr(grant, "model", ""),
                "status": "error" if error_type else "completed",
                "error_type": error_type,
                "input_tokens": final_input,
                "output_tokens": final_output,
                "usd": format(explicit_usd, "f") if explicit_usd is not None else None,
                "usage_error": usage_errors or None,
            }
            with self._lock:
                _append(self.transcript_path, record)
                self._calls.append(call_id)

    def write_summary(
        self,
        *,
        claimed_provider_calls: int | None = None,
        claimed_call_ids: Sequence[str] | None = None,
    ) -> Path:
        """Write the operator's run claim separately from the transcript."""

        with self._lock:
            claim = len(self._calls) if claimed_provider_calls is None else claimed_provider_calls
            if isinstance(claim, bool) or not isinstance(claim, int) or claim < 0:
                raise GrantLedgerError("claimed_provider_calls must be a non-negative integer")
            ids = list(self._calls) if claimed_call_ids is None else list(claimed_call_ids)
            _atomic_json(
                self.summary_path,
                {
                    "schema": SUMMARY_SCHEMA,
                    "run_id": self.run_id,
                    "run_set_id": self.run_set_id,
                    "claimed_provider_calls": claim,
                    "claimed_call_ids": ids,
                },
            )
            return self.summary_path

    def close(self) -> Path:
        return self.write_summary()

    def __enter__(self) -> "GrantLedger":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()


def _record_grant_definitions(
    events: Iterable[Mapping[str, Any]],
    *,
    run_dir: str,
    findings: list[LedgerFinding],
    invalid_grant_ids: set[str] | None = None,
    malformed_ceiling_keys: set[tuple[str, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}
    for event in events:
        kind = event.get("event")
        if kind == "grant_issued":
            entries = [(event.get("grant_id"), event.get("grant"))]
        elif kind == "grant_expanded":
            entries = [
                (event.get("previous_grant_id"), event.get("previous_grant")),
                (event.get("grant_id"), event.get("grant")),
            ]
        else:
            continue
        for grant_id, grant in entries:
            if not isinstance(grant_id, str) or not grant_id or not isinstance(grant, Mapping):
                findings.append(LedgerFinding("malformed_grant_event", "grant event has invalid identity or payload", run_dir))
                continue
            normalized = dict(grant)
            # Validate ceiling types before identity verification.  Otherwise
            # a tampered ceiling changes the derived identity and the payload
            # is discarded before the checker can report the malformed value.
            for ceiling_name in ("max_calls", "max_tokens", "max_usd"):
                _ceiling(
                    grant_id,
                    normalized,
                    ceiling_name,
                    run_dir=run_dir,
                    findings=findings,
                    malformed_ceiling_keys=malformed_ceiling_keys,
                )
            try:
                derived_id = grant_identity(normalized)
            except Exception as exc:
                findings.append(LedgerFinding("malformed_grant_event", f"grant payload cannot be canonicalized: {exc}", run_dir))
                if isinstance(grant_id, str):
                    (invalid_grant_ids if invalid_grant_ids is not None else set()).add(grant_id)
                continue
            if derived_id != grant_id:
                findings.append(
                    LedgerFinding(
                        "grant_identity_mismatch",
                        f"recorded grant_id {grant_id} does not match the grant payload identity {derived_id}",
                        run_dir,
                        grant_id,
                    )
                )
                if invalid_grant_ids is not None:
                    invalid_grant_ids.add(grant_id)
                continue
            old = definitions.get(grant_id)
            if old is not None and old != normalized:
                findings.append(
                    LedgerFinding("grant_identity_collision", "one grant identity has conflicting grant payloads", run_dir, grant_id)
                )
            else:
                definitions[grant_id] = normalized
    return definitions


@dataclass(frozen=True, slots=True)
class _LoadedRun:
    path: Path
    run_id: str
    summary: Mapping[str, Any]
    events: list[dict[str, Any]]
    transcript: list[dict[str, Any]] | None
    attempts: list[dict[str, Any]] | None
    definitions: Mapping[str, dict[str, Any]]


def _attempt_call_id(record: Mapping[str, Any], *, run_id: str, line_number: int) -> str:
    for key in ("call_id", "attempt_id", "id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    for key in ("attempt_index", "attempt_number", "index"):
        value = record.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
            return f"{run_id}:attempt-{value}"
    return f"{run_id}:attempt-{line_number}"


def _recorded_grant_for_mapper_spec(
    record: Mapping[str, Any],
    definitions: Mapping[str, dict[str, Any]],
    *,
    run_dir: str,
    findings: list[LedgerFinding],
) -> str | None:
    mapper_spec_id = record.get("mapper_spec_id")
    if not isinstance(mapper_spec_id, str) or not mapper_spec_id:
        findings.append(LedgerFinding("malformed_attempt", "attempt has no mapper_spec_id", run_dir))
        return None
    explicit_grant_id = record.get("grant_id")
    if explicit_grant_id is not None:
        if not isinstance(explicit_grant_id, str) or explicit_grant_id not in definitions:
            findings.append(
                LedgerFinding(
                    "unknown_grant",
                    "attempt is not bound to a recorded grant",
                    run_dir,
                    explicit_grant_id if isinstance(explicit_grant_id, str) else None,
                )
            )
            return None
        if definitions[explicit_grant_id].get("mapper_spec_id") != mapper_spec_id:
            findings.append(
                LedgerFinding(
                    "grant_scope_mismatch",
                    "attempt mapper_spec_id does not match its recorded grant",
                    run_dir,
                    explicit_grant_id,
                )
            )
            return None
        return explicit_grant_id
    matches = sorted(
        grant_id
        for grant_id, grant in definitions.items()
        if grant.get("mapper_spec_id") == mapper_spec_id
    )
    if len(matches) == 1:
        return matches[0]
    if not matches:
        findings.append(LedgerFinding("unknown_grant", "attempt mapper_spec_id has no recorded grant", run_dir))
    else:
        findings.append(
            LedgerFinding(
                "ambiguous_grant",
                "attempt mapper_spec_id matches more than one grant identity; grant usage is unverifiable",
                run_dir,
            )
        )
    return None


def _check_call_id_contiguity(
    call_ids: Iterable[str],
    *,
    run_id: str,
    run_dir: str,
    findings: list[LedgerFinding],
) -> None:
    prefix = f"{run_id}:call-"
    numbers: list[int] = []
    for call_id in call_ids:
        if not call_id.startswith(prefix):
            continue
        suffix = call_id[len(prefix) :]
        if suffix.isdigit() and int(suffix) >= 1:
            numbers.append(int(suffix))
    if not numbers:
        return
    actual = sorted(set(numbers))
    expected = list(range(1, actual[-1] + 1))
    if actual != expected or len(numbers) != len(actual):
        findings.append(
            LedgerFinding(
                "noncontiguous_call_ids",
                f"provider call ids are not a contiguous run sequence: {actual}",
                run_dir,
            )
        )


def _check_attempt_index_contiguity(
    records: Iterable[Mapping[str, Any]],
    *,
    run_dir: str,
    findings: list[LedgerFinding],
) -> None:
    """Check the upstream attempt sequence within each mapped cell.

    The field-mapper ledger's ``attempt_index`` is zero-based and restarts for
    each ``(target_row_key, field)`` stream.  ``attempt_id`` is deliberately a
    random execution identifier, so it cannot establish ordering.
    """

    streams: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    for record in records:
        sequence = record.get("attempt_index")
        if sequence is None:
            for key in ("sequence", "sequence_number", "attempt_number", "index"):
                if key in record:
                    sequence = record[key]
                    break
        if sequence is None:
            continue
        row_key = record.get("target_row_key")
        field = record.get("field", record.get("field_name"))
        if row_key is None and field is None:
            # Keep small synthetic upstream-shaped fixtures useful while the
            # real ledger remains grouped by its required cell identity.
            stream = ("<unkeyed>", "<unkeyed>")
        elif isinstance(row_key, str) and row_key and isinstance(field, str) and field:
            stream = (row_key, field)
        else:
            continue
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            findings.append(
                LedgerFinding(
                    "malformed_attempt",
                    "attempt sequence is not a non-negative integer",
                    run_dir,
                )
            )
            continue
        streams[stream].append(sequence)

    for stream, sequence_values in streams.items():
        actual = sorted(sequence_values)
        expected = list(range(0, actual[-1] + 1))
        if actual != expected or len(sequence_values) != len(set(sequence_values)):
            findings.append(
                LedgerFinding(
                    "noncontiguous_attempt_indices",
                    f"upstream attempt indices for {stream!r} are not a contiguous zero-based sequence: {actual}",
                    run_dir,
                )
            )


def _ceiling(
    grant_id: str,
    grant: Mapping[str, Any],
    name: str,
    *,
    run_dir: str,
    findings: list[LedgerFinding],
    malformed_ceiling_keys: set[tuple[str, str]] | None = None,
) -> int | Decimal | None:
    def record_malformed(detail: str) -> None:
        key = (grant_id, name)
        if malformed_ceiling_keys is not None and key in malformed_ceiling_keys:
            return
        findings.append(LedgerFinding("malformed_grant_ceiling", detail, run_dir, grant_id))
        if malformed_ceiling_keys is not None:
            malformed_ceiling_keys.add(key)

    value = grant.get(name)
    if value is None:
        return None
    if name in {"max_calls", "max_tokens"}:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            record_malformed(f"{name} must be a non-negative integer or null, got {value!r}")
            return None
        return value
    try:
        return _decimal(value, name=name)
    except GrantLedgerError as exc:
        record_malformed(str(exc))
        return None


def check_cumulative_budgets(
    run_dirs: Sequence[str | Path],
    *,
    run_set_id: str | None = None,
) -> CumulativeBudgetReport:
    """Check cumulative usage across the explicit set of suite-written runs.

    ``attempts.jsonl`` is the upstream field-mapper ledger and is the primary
    usage source whenever it exists.  The grantkit transcript remains useful
    for lifecycle failures and caller-supplied spend, but is not counted a
    second time when both files are present.

    Usage is keyed by the recorded grant identity.  An expansion therefore
    creates a new tally by design: upstream attempts without an explicit
    ``grant_id`` are ambiguous when more than one grant identity has the same
    mapper spec, and fail closed rather than being assigned arbitrarily.
    """

    findings: list[LedgerFinding] = []
    definitions: dict[str, dict[str, Any]] = {}
    definition_run_dirs: dict[str, str] = {}
    invalid_grant_ids: set[str] = set()
    malformed_ceiling_keys: set[tuple[str, str]] = set()
    usage_calls: defaultdict[str, int] = defaultdict(int)
    usage_tokens: defaultdict[str, int] = defaultdict(int)
    usage_usd: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    unknown_tokens: set[str] = set()
    unknown_usd: set[str] = set()
    seen_runs: set[str] = set()
    seen_call_ids: set[str] = set()
    loaded_runs: list[_LoadedRun] = []
    if not run_dirs:
        findings.append(LedgerFinding("empty_run_set", "no run directories were supplied"))

    resolved_run_dirs = sorted((Path(raw_dir).resolve() for raw_dir in run_dirs), key=str)
    for run_path in resolved_run_dirs:
        run_label = str(run_path)
        try:
            events = _read_jsonl(run_path / EVENTS_FILENAME, kind="grant events")
            summary = json.loads((run_path / SUMMARY_FILENAME).read_text(encoding="utf-8"))
            transcript = (
                _read_jsonl(run_path / TRANSCRIPT_FILENAME, kind="provider transcript")
                if (run_path / TRANSCRIPT_FILENAME).is_file()
                else None
            )
            attempts = (
                _read_jsonl(run_path / ATTEMPTS_FILENAME, kind="upstream attempts")
                if (run_path / ATTEMPTS_FILENAME).is_file()
                else None
            )
            if transcript is None and attempts is None:
                raise GrantLedgerError(
                    f"missing provider usage: expected {ATTEMPTS_FILENAME} or {TRANSCRIPT_FILENAME}: {run_path}"
                )
        except (OSError, UnicodeError, json.JSONDecodeError, GrantLedgerError) as exc:
            findings.append(LedgerFinding("malformed_run", str(exc), run_label))
            continue
        if not isinstance(summary, Mapping) or summary.get("schema") != SUMMARY_SCHEMA:
            findings.append(LedgerFinding("malformed_run_summary", "run summary schema is missing or wrong", run_label))
            continue
        run_id = summary.get("run_id")
        actual_run_set = summary.get("run_set_id")
        if not isinstance(run_id, str) or not run_id:
            findings.append(LedgerFinding("malformed_run_summary", "run summary has no run_id", run_label))
        elif run_id in seen_runs:
            findings.append(LedgerFinding("duplicate_run_id", "run_id occurs more than once in the explicit run set", run_label))
        else:
            seen_runs.add(run_id)
        if run_set_id is not None and actual_run_set != run_set_id:
            findings.append(LedgerFinding("run_set_mismatch", "run is outside the requested run set", run_label))

        run_definitions = _record_grant_definitions(
            events,
            run_dir=run_label,
            findings=findings,
            invalid_grant_ids=invalid_grant_ids,
            malformed_ceiling_keys=malformed_ceiling_keys,
        )
        for grant_id, grant in run_definitions.items():
            old = definitions.get(grant_id)
            if old is not None and old != grant:
                findings.append(LedgerFinding("grant_identity_collision", "grant identity differs between runs", run_label, grant_id))
            else:
                definitions[grant_id] = grant
                definition_run_dirs.setdefault(grant_id, run_label)

        loaded_runs.append(
            _LoadedRun(
                path=run_path,
                run_id=run_id if isinstance(run_id, str) else run_label,
                summary=summary,
                events=events,
                transcript=transcript,
                attempts=attempts,
                definitions=run_definitions,
            )
        )

    for loaded in loaded_runs:
        run_label = str(loaded.path)
        source_is_attempts = loaded.attempts is not None
        source_records = loaded.attempts if source_is_attempts else loaded.transcript
        assert source_records is not None
        started: set[str] = set()
        completed: set[str] = set()
        transcript_completed: set[str] = set()
        claimed_records: list[Mapping[str, Any]] = []
        primary_spend: set[str] = set()

        for line_number, record in enumerate(source_records, start=1):
            if source_is_attempts:
                call_id = _attempt_call_id(record, run_id=loaded.run_id, line_number=line_number)
                completed.add(call_id)
                if call_id in seen_call_ids:
                    findings.append(LedgerFinding("duplicate_call_id", "provider call id occurs more than once", run_label))
                seen_call_ids.add(call_id)
                grant_id = _recorded_grant_for_mapper_spec(
                    record,
                    definitions,
                    run_dir=run_label,
                    findings=findings,
                )
                if grant_id is None or grant_id in invalid_grant_ids:
                    continue
            else:
                event = record.get("event")
                call_id = record.get("call_id")
                if event == "provider_call_started":
                    if isinstance(call_id, str):
                        started.add(call_id)
                    continue
                if event != "provider_call":
                    continue
                if not isinstance(call_id, str) or not call_id:
                    findings.append(LedgerFinding("malformed_provider_call", "provider call has no call_id", run_label))
                    continue
                if call_id in seen_call_ids:
                    findings.append(LedgerFinding("duplicate_call_id", "provider call id occurs more than once", run_label))
                seen_call_ids.add(call_id)
                completed.add(call_id)
                grant_id = record.get("grant_id")
                if not isinstance(grant_id, str) or grant_id not in definitions or grant_id in invalid_grant_ids:
                    findings.append(
                        LedgerFinding(
                            "unknown_grant",
                            "provider call is not bound to a recorded grant",
                            run_label,
                            grant_id if isinstance(grant_id, str) else None,
                        )
                    )
                    continue

            usage_calls[grant_id] += 1
            input_tokens = record.get("input_tokens")
            output_tokens = record.get("output_tokens")
            try:
                parsed_input = _tokens(input_tokens, name="input_tokens")
                parsed_output = _tokens(output_tokens, name="output_tokens")
                parsed_usd = _decimal(
                    record.get("usd", record.get("spend_usd")),
                    name="usd",
                )
            except GrantLedgerError as exc:
                findings.append(LedgerFinding("malformed_provider_call", str(exc), run_label, grant_id))
                continue
            if record.get("usage_error"):
                findings.append(
                    LedgerFinding(
                        "malformed_provider_call",
                        f"provider recorded invalid usage: {record['usage_error']!r}",
                        run_label,
                        grant_id,
                    )
                )
            if parsed_input is None or parsed_output is None:
                unknown_tokens.add(grant_id)
            else:
                usage_tokens[grant_id] += parsed_input + parsed_output
            if parsed_usd is None:
                unknown_usd.add(grant_id)
            else:
                usage_usd[grant_id] += parsed_usd
                primary_spend.add(grant_id)
            claimed_records.append(record)

        if source_is_attempts:
            _check_attempt_index_contiguity(
                source_records,
                run_dir=run_label,
                findings=findings,
            )

        # Lifecycle and spend are the extra facts the harness transcript can
        # provide when upstream attempts are the primary call ledger.
        if loaded.transcript is not None:
            reserved = {
                event["call_id"]
                for event in loaded.events
                if event.get("event") == "provider_call_reserved" and isinstance(event.get("call_id"), str)
            }
            started.update(reserved)
            transcript_spend: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
            transcript_spend_grants: set[str] = set()
            for record in loaded.transcript:
                event = record.get("event")
                call_id = record.get("call_id")
                if event == "provider_call_started":
                    if isinstance(call_id, str):
                        started.add(call_id)
                    continue
                if event != "provider_call":
                    continue
                if not isinstance(call_id, str) or not call_id:
                    continue
                transcript_completed.add(call_id)
                grant_id = record.get("grant_id")
                if not isinstance(grant_id, str) or grant_id not in definitions or grant_id in invalid_grant_ids:
                    continue
                try:
                    parsed_usd = _decimal(record.get("usd"), name="usd")
                except GrantLedgerError as exc:
                    findings.append(LedgerFinding("malformed_provider_call", str(exc), run_label, grant_id))
                    continue
                if parsed_usd is not None:
                    transcript_spend[grant_id] += parsed_usd
                    transcript_spend_grants.add(grant_id)
            if source_is_attempts:
                for grant_id in transcript_spend_grants - primary_spend:
                    usage_usd[grant_id] += transcript_spend[grant_id]
                    unknown_usd.discard(grant_id)

        for call_id in sorted(started - transcript_completed if source_is_attempts else started - completed):
            findings.append(
                LedgerFinding(
                    "incomplete_provider_call",
                    "provider dispatch started without a completed transcript row",
                    run_label,
                )
            )
        _check_call_id_contiguity(
            started | completed,
            run_id=loaded.run_id,
            run_dir=run_label,
            findings=findings,
        )

        claimed = loaded.summary.get("claimed_provider_calls")
        if isinstance(claimed, bool) or not isinstance(claimed, int) or claimed < 0:
            findings.append(LedgerFinding("malformed_run_summary", "claimed_provider_calls is not a non-negative integer", run_label))
        elif claimed != len(claimed_records):
            findings.append(
                LedgerFinding(
                    "claimed_call_count_mismatch",
                    f"run claims {claimed} provider calls but primary usage records contain {len(claimed_records)}",
                    run_label,
                )
            )
        claimed_ids = loaded.summary.get("claimed_call_ids")
        if claimed_ids is not None:
            if not isinstance(claimed_ids, list) or not all(isinstance(item, str) for item in claimed_ids):
                findings.append(LedgerFinding("malformed_run_summary", "claimed_call_ids is not a string list", run_label))
            elif len(claimed_ids) != len(set(claimed_ids)) or set(claimed_ids) != completed:
                findings.append(LedgerFinding("claimed_call_ids_mismatch", "run claim ids do not reconcile one-to-one with primary usage calls", run_label))

    usage: dict[str, GrantUsage] = {}
    for grant_id in sorted(set(definitions) | set(usage_calls) | invalid_grant_ids):
        grant = definitions.get(grant_id, {})
        definition_run_dir = definition_run_dirs.get(grant_id)
        max_calls = _ceiling(
            grant_id,
            grant,
            "max_calls",
            run_dir=definition_run_dir or "",
            findings=findings,
            malformed_ceiling_keys=malformed_ceiling_keys,
        )
        max_tokens = _ceiling(
            grant_id,
            grant,
            "max_tokens",
            run_dir=definition_run_dir or "",
            findings=findings,
            malformed_ceiling_keys=malformed_ceiling_keys,
        )
        max_usd = _ceiling(
            grant_id,
            grant,
            "max_usd",
            run_dir=definition_run_dir or "",
            findings=findings,
            malformed_ceiling_keys=malformed_ceiling_keys,
        )
        breached: list[str] = []
        calls = usage_calls[grant_id]
        total_tokens = None if grant_id in unknown_tokens else usage_tokens[grant_id]
        total_usd = None if grant_id in unknown_usd else usage_usd[grant_id]
        if max_calls is not None and calls > max_calls:
            breached.append("max_calls")
            findings.append(LedgerFinding("cumulative_calls_exceeded", f"{calls} calls exceed max_calls={max_calls}", grant_id=grant_id))
        if max_tokens is not None and total_tokens is not None and total_tokens > max_tokens:
            breached.append("max_tokens")
            findings.append(LedgerFinding("cumulative_tokens_exceeded", f"{total_tokens} tokens exceed max_tokens={max_tokens}", grant_id=grant_id))
        if max_usd is not None and total_usd is not None and total_usd > max_usd:
            breached.append("max_usd")
            findings.append(LedgerFinding("cumulative_spend_exceeded", f"{total_usd} USD exceed max_usd={max_usd}", grant_id=grant_id))
        if grant_id in unknown_tokens:
            findings.append(LedgerFinding("unknown_token_usage", "token usage is missing; ceiling cannot be verified", grant_id=grant_id))
        if grant_id in unknown_usd and max_usd is not None:
            findings.append(LedgerFinding("unknown_spend_usage", "spend is missing; ceiling cannot be verified", grant_id=grant_id))
        usage[grant_id] = GrantUsage(grant_id, calls, total_tokens, total_usd, max_calls, max_tokens, max_usd, tuple(breached))
    return CumulativeBudgetReport(usage=usage, findings=tuple(findings))


__all__ = [
    "CumulativeBudgetReport",
    "ATTEMPTS_FILENAME",
    "EVENTS_FILENAME",
    "GrantLedger",
    "GrantLedgerError",
    "GrantUsage",
    "LedgerFinding",
    "SUMMARY_FILENAME",
    "TRANSCRIPT_FILENAME",
    "check_cumulative_budgets",
]

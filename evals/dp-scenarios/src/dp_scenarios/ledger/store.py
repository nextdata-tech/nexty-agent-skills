"""Detectably append-only JSONL storage for one evidence ledger.

The first line is an anchored manifest.  Every later line is an immutable row
with a store-assigned ``row_id`` and a ``prev_digest`` over the exact bytes of
the preceding line.  Opening and appending verify the whole chain, so editing
or truncating any prior line raises :class:`LedgerTamperError` before a new
row can be written.  Supersession is therefore expressed only by a later row's
``supersedes`` reference; no method edits an earlier observation.

The chain and terminal anchor are deliberately unkeyed hashes.  They detect
edits that do not recompute the chain, but do not authenticate the ledger
against an attacker who can rewrite both the rows and the anchor.  The
terminal ``.anchor`` sidecar is part of the ledger artifact and must be copied
with the JSONL file.

Initialization writes the anchored manifest through a temporary file and
``os.replace`` so a crash cannot leave a half-initialized row-zero file.  An
advisory lock held for the lifetime of a store prevents two store handles from
interleaving appends to the same ledger; the chain is what detects writers
that do not participate in that lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, BinaryIO

import fcntl

from .manifest import Manifest, ManifestError
from .schema import LedgerRow, SchemaError


class LedgerError(ValueError):
    """Base error for invalid ledger state or an unsafe append."""


class LedgerFormatError(LedgerError):
    """Raised when a ledger line cannot be parsed as JSON or a row."""


class LedgerTamperError(LedgerError):
    """Raised when the first divergent line breaks the append-only chain."""


class LedgerLockError(LedgerError):
    """Raised when another store handle already owns the ledger lock."""


def _encode_record(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def _anchor_path(path: Path) -> Path:
    return path.with_name(path.name + ".anchor")


def _atomic_write_anchor(path: Path, digest: str) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
            encoding="ascii", newline="", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(digest + "\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _read_raw_lines(path: Path) -> list[bytes]:
    if not path.exists():
        raise LedgerError(f"ledger file does not exist: {path}")
    try:
        with path.open("rb") as handle:
            lines = handle.readlines()
    except OSError as exc:
        raise LedgerError(f"could not read ledger {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.endswith(b"\n"):
            raise LedgerTamperError(f"ledger {path} tampered at line {line_number}: line has no newline")
        if not line.strip():
            raise LedgerFormatError(f"malformed ledger {path} at line {line_number}: blank line")
    return lines


def _read_json_lines(path: Path, raw_lines: list[bytes] | None = None) -> list[Any]:
    """Parse every JSON line without skipping malformed records."""

    records: list[Any] = []
    lines = _read_raw_lines(path) if raw_lines is None else raw_lines
    for line_number, raw_line in enumerate(lines, start=1):
        try:
            records.append(json.loads(raw_line.decode("utf-8")))
        except UnicodeDecodeError as exc:
            raise LedgerFormatError(f"malformed ledger {path} at line {line_number}: invalid UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise LedgerFormatError(f"malformed ledger {path} at line {line_number}: {exc.msg}") from exc
    return records


def _manifest_from_first(path: Path, records: list[Any]) -> Manifest:
    if not records:
        raise LedgerError(f"ledger {path} has no row 0 manifest")
    try:
        return Manifest.from_record(records[0], replay=None)
    except ManifestError as exc:
        raise LedgerError(f"ledger {path} row 0 is not a valid manifest: {exc}") from exc


def _verify_chain(path: Path, records: list[Any], raw_lines: list[bytes]) -> list[LedgerRow]:
    """Verify row-zero anchoring, row IDs, and every predecessor digest."""

    if not records:
        raise LedgerError(f"ledger {path} has no row 0 manifest")
    if len(records) != len(raw_lines):
        raise LedgerFormatError(f"malformed ledger {path}: line count changed during read")
    _manifest_from_first(path, records)
    first = records[0]
    if not isinstance(first, Mapping) or not isinstance(first.get("chain_anchor"), str):
        raise LedgerTamperError(f"ledger {path} tampered at line 1: missing chain anchor")
    unsigned_first = {key: value for key, value in first.items() if key != "chain_anchor"}
    expected_anchor = _digest(_encode_record(unsigned_first))
    if first["chain_anchor"] != expected_anchor:
        raise LedgerTamperError(f"ledger {path} tampered at line 1: chain anchor mismatch")

    parsed_rows: list[LedgerRow] = []
    for line_number, (record, raw_line) in enumerate(zip(records[1:], raw_lines[1:], strict=True), start=2):
        try:
            row = LedgerRow.from_mapping(record, stored=True)
        except (SchemaError, TypeError, KeyError) as exc:
            raise LedgerFormatError(f"malformed ledger {path} at line {line_number}: {exc}") from exc
        expected_previous = _digest(raw_lines[line_number - 2])
        if row.prev_digest != expected_previous:
            raise LedgerTamperError(
                f"ledger {path} tampered at line {line_number - 1}: predecessor digest mismatch "
                f"(detected at line {line_number})"
            )
        expected_row_id = line_number - 1
        if row.row_id != expected_row_id:
            raise LedgerTamperError(
                f"ledger {path} tampered at line {line_number}: row_id {row.row_id!r}, expected {expected_row_id}"
            )
        parsed_rows.append(row)
    return parsed_rows


def _read_verified(path: Path) -> tuple[list[Any], list[bytes], list[LedgerRow]]:
    raw_lines = _read_raw_lines(path)
    records = _read_json_lines(path, raw_lines)
    parsed_rows = _verify_chain(path, records, raw_lines)
    anchor_path = _anchor_path(path)
    try:
        terminal_anchor = anchor_path.read_text(encoding="ascii").strip()
    except (FileNotFoundError, UnicodeDecodeError, OSError) as exc:
        raise LedgerTamperError(
            f"ledger {path} tampered: history ends at line {len(raw_lines)} but terminal anchor is missing"
        ) from exc
    if terminal_anchor != _digest(raw_lines[-1]):
        raise LedgerTamperError(
            f"ledger {path} tampered: history ends at line {len(raw_lines)} but terminal anchor expects a different final line"
        )
    return records, raw_lines, parsed_rows


def read_ledger(
    path: str | Path, *, resolve_supersession: bool = False
) -> list[dict[str, object]]:
    """Read a complete, chain-verified ledger, optionally materializing supersession."""

    ledger_path = Path(path)
    records, _raw_lines, parsed_rows = _read_verified(ledger_path)
    parsed: list[dict[str, object]] = [dict(records[0])]
    for row in parsed_rows:
        parsed.append(row.to_dict())
    if not resolve_supersession:
        return parsed

    by_target: dict[int, int] = {}
    for row in parsed_rows:
        if row.supersedes is not None and row.supersedes not in by_target:
            by_target[row.supersedes] = row.turn
    for row in parsed[1:]:
        row["superseded_by_turn"] = by_target.get(row["row_id"])
    return parsed


class LedgerStore:
    """A locked handle that can append rows but cannot mutate old evidence."""

    def __init__(self, path: str | Path, manifest: Manifest | Mapping[str, object] | None = None):
        self.path = Path(path)
        self.manifest = _coerce_manifest(manifest) if manifest is not None else None
        self._handle: BinaryIO | None = None
        self._lock_handle: BinaryIO | None = None
        self._next_row_id = 1
        self._last_line: bytes | None = None

    @classmethod
    def open(
        cls, path: str | Path, manifest: Manifest | Mapping[str, object]
    ) -> "LedgerStore":
        """Acquire the advisory lock and open or atomically initialize a ledger."""

        store = cls(path, manifest)
        store.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            store._acquire_lock()
            existed_with_bytes = store.path.exists() and store.path.stat().st_size > 0
            if existed_with_bytes:
                records = _read_json_lines(store.path)
                existing_manifest = _manifest_from_first(store.path, records)
                if store.manifest is None or existing_manifest.to_dict() != store.manifest.to_dict():
                    raise LedgerError(f"ledger {store.path} already has a different row 0 manifest")
            else:
                if store.manifest is None:
                    raise ManifestError("LedgerStore.open requires a Manifest or manifest mapping")
                store._atomic_initialize(store.manifest)
            store._verify_current_file()
            store._handle = store.path.open("ab")
            return store
        except Exception:
            store.close()
            raise

    def _acquire_lock(self) -> None:
        lock_path = self.path.with_name(self.path.name + ".lock")
        self._lock_handle = lock_path.open("a+b")
        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._lock_handle.close()
            self._lock_handle = None
            raise LedgerLockError(f"ledger {self.path} is already locked") from exc

    def _atomic_initialize(self, manifest: Manifest) -> None:
        unsigned = manifest.to_record()
        record = dict(unsigned)
        record["chain_anchor"] = _digest(_encode_record(unsigned))
        temporary_name: str | None = None
        encoded = _encode_record(record)
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent, delete=False
            ) as temporary:
                temporary_name = temporary.name
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
            temporary_name = None
            _atomic_write_anchor(_anchor_path(self.path), _digest(encoded))
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

    def __enter__(self) -> "LedgerStore":
        if self._handle is None:
            raise LedgerError(f"ledger {self.path} is not open")
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        """Flush and release the handle and advisory lock without changing bytes."""

        if self._handle is not None:
            self._handle.flush()
            self._handle.close()
            self._handle = None
        if self._lock_handle is not None:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            self._lock_handle.close()
            self._lock_handle = None

    def append(self, row: LedgerRow | Mapping[str, object]) -> None:
        """Verify all existing bytes, assign identity, and append one row."""

        if self._handle is None:
            if not self.path.exists() or self.path.stat().st_size == 0:
                raise LedgerError(f"ledger {self.path} has no row 0 manifest")
            try:
                _manifest_from_first(self.path, _read_json_lines(self.path))
            except LedgerError as exc:
                raise LedgerError(f"ledger {self.path} row 0 is invalid: {exc}") from exc
            raise LedgerError(f"ledger {self.path} is not open")
        parsed_row = row if isinstance(row, LedgerRow) else LedgerRow.from_mapping(row)
        if parsed_row.row_id is not None or parsed_row.prev_digest is not None:
            raise LedgerError("row_id and prev_digest are assigned by LedgerStore")
        self._verify_current_file()
        assert self._last_line is not None
        row_id = self._next_row_id
        previous_digest = _digest(self._last_line)
        stored_row = replace(parsed_row)
        object.__setattr__(stored_row, "row_id", row_id)
        object.__setattr__(stored_row, "prev_digest", previous_digest)
        encoded = _encode_record(stored_row.to_dict())
        self._handle.seek(0, os.SEEK_END)
        self._handle.write(encoded)
        self._handle.flush()
        os.fsync(self._handle.fileno())
        _atomic_write_anchor(_anchor_path(self.path), _digest(encoded))
        self._next_row_id += 1
        self._last_line = encoded

    def read(self, *, resolve_supersession: bool = False) -> list[dict[str, object]]:
        """Return all chain-verified records, including row zero."""

        return read_ledger(self.path, resolve_supersession=resolve_supersession)

    def _verify_current_file(self) -> None:
        _records, raw_lines, parsed_rows = _read_verified(self.path)
        self._next_row_id = len(parsed_rows) + 1
        self._last_line = raw_lines[-1]


def _coerce_manifest(value: Manifest | Mapping[str, object] | None) -> Manifest:
    if isinstance(value, Manifest):
        return value
    if isinstance(value, Mapping):
        return Manifest.from_mapping(value, replay=None)
    raise ManifestError("LedgerStore.open requires a Manifest or manifest mapping")

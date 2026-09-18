"""Durable, secret-safe checkpoints for resumable scenario runs.

This module deliberately does not know about Claude sessions, supervisor
state, replay recordings, or the operator engine.  It stores the smallest
contract needed by a future runner integration: an immutable execution
identity, an immutable committed-turn state, and an explicit decision about
whether that state may be resumed or only regraded.

The store is append-only from the reader's point of view.  A commit writes an
immutable state record, appends a journal record, and finally advances an
atomic ``latest.json`` pointer.  If the pointer is absent or damaged, reads
walk the journal backwards and recover the newest valid state without
repairing files as a side effect.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Literal


class CheckpointError(RuntimeError):
    """Raised when a checkpoint payload or store violates the contract."""


IdentityGroup = Literal["run", "behavior", "substrate", "grading"]
ResumeMode = Literal["native-resume", "report-only"]
DecisionAction = Literal["resume", "regrade", "reject"]

_IDENTITY_GROUPS: tuple[IdentityGroup, ...] = (
    "run",
    "behavior",
    "substrate",
    "grading",
)
_SCHEMA_VERSION = 1
_SECRET_KEY_PARTS = ("token", "key", "secret", "password", "auth", "credential")
_CHECKPOINT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value: object) -> bytes:
    """Return stable JSON bytes for a validated JSON-compatible value."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CheckpointError("checkpoint payload is not canonical JSON") from exc


def _is_secret_key(key: str) -> bool:
    lowered = key.casefold()
    return any(part in lowered for part in _SECRET_KEY_PARTS)


def _is_obvious_secret_value(value: str) -> bool:
    """Recognize common credential encodings without logging their contents."""

    stripped = value.strip()
    lowered = stripped.casefold()
    if any(
        marker in lowered
        for marker in (
            "bearer ",
            "api_key=",
            "api-key=",
            "access_token=",
            "refresh_token=",
            "password=",
            "secret=",
        )
    ):
        return True
    if stripped.startswith(("sk-", "ghp_", "github_pat_", "xoxb-", "xoxp-")):
        return True
    if stripped.startswith("-----BEGIN ") and stripped.endswith("-----"):
        return True
    # JWTs are structurally obvious even when their contents are opaque.
    if len(stripped.split(".")) == 3 and all(stripped.split(".")):
        return all(re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in stripped.split("."))
    return False


def _validate_json(value: object, path: str = "$", *, reject_secrets: bool = True) -> object:
    """Validate and recursively copy JSON data without exposing secrets."""

    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and reject_secrets and _is_obvious_secret_value(value):
            raise CheckpointError(f"secret-like value at {path} is not allowed")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CheckpointError(f"non-finite number at {path} is not allowed")
        return value
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for raw_key, raw_item in value.items():
            if not isinstance(raw_key, str):
                raise CheckpointError(f"non-string key at {path} is not allowed")
            if reject_secrets and _is_secret_key(raw_key):
                raise CheckpointError(f"secret-like key at {path} is not allowed")
            copied[raw_key] = _validate_json(raw_item, f"{path}.{raw_key}", reject_secrets=reject_secrets)
        return copied
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _validate_json(item, f"{path}[{index}]", reject_secrets=reject_secrets)
            for index, item in enumerate(value)
        ]
    raise CheckpointError(f"value at {path} is not JSON-compatible")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_mapping(value: object, description: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CheckpointError(f"{description} must be a mapping")
    return value


def _require_exact_keys(value: Mapping[str, object], expected: set[str], description: str) -> None:
    actual = set(value)
    if actual != expected:
        raise CheckpointError(
            f"{description} has unexpected fields: expected {sorted(expected)}, got {sorted(actual)}"
        )


def _read_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"cannot read checkpoint JSON: {path.name}") from exc


def _fsync_directory(path: Path) -> None:
    """Make a completed rename durable where the platform supports it."""

    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_json(payload) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _append_journal(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_json(payload) + b"\n"
    with path.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


@dataclass(frozen=True)
class CheckpointIdentity:
    """Canonical identity for the execution represented by a checkpoint.

    The four groups are intentionally separate.  Native continuation requires
    every group to match.  A report-only decision may explicitly permit a
    grading-group change while still requiring the run, behavior, and
    substrate groups to match exactly.
    """

    groups: Mapping[IdentityGroup, Mapping[str, object]]
    digest: str

    def __post_init__(self) -> None:
        if set(self.groups) != set(_IDENTITY_GROUPS):
            raise CheckpointError(f"identity groups must be exactly {list(_IDENTITY_GROUPS)}")
        normalized: dict[str, object] = {}
        for group in _IDENTITY_GROUPS:
            raw_group = self.groups[group]
            if not isinstance(raw_group, Mapping):
                raise CheckpointError(f"identity group {group!r} must be a mapping")
            normalized[group] = _validate_json(raw_group, f"$.{group}")
        if not isinstance(self.digest, str) or not _SHA256_RE.fullmatch(self.digest):
            raise CheckpointError("identity digest is invalid")
        if _digest(normalized) != self.digest:
            raise CheckpointError("identity digest does not match canonical groups")

    @classmethod
    def from_groups(cls, groups: Mapping[str, Mapping[str, object]]) -> "CheckpointIdentity":
        """Create an identity from exactly ``run``, ``behavior``, ``substrate``, and ``grading``."""

        if not isinstance(groups, Mapping):
            raise CheckpointError("identity groups must be a mapping")
        if set(groups) != set(_IDENTITY_GROUPS):
            raise CheckpointError(f"identity groups must be exactly {list(_IDENTITY_GROUPS)}")
        normalized: dict[str, object] = {}
        for group in _IDENTITY_GROUPS:
            raw_group = groups[group]
            if not isinstance(raw_group, Mapping):
                raise CheckpointError(f"identity group {group!r} must be a mapping")
            normalized[group] = _validate_json(raw_group, f"$.{group}")
        digest = _digest(normalized)
        typed_groups = {group: normalized[group] for group in _IDENTITY_GROUPS}
        return cls(typed_groups, digest)  # type: ignore[arg-type]

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "CheckpointIdentity":
        """Decode and verify a persisted identity, rejecting tampering."""

        payload = _require_mapping(value, "identity")
        _require_exact_keys(payload, {"schema", "groups", "digest"}, "identity")
        if payload["schema"] != _SCHEMA_VERSION:
            raise CheckpointError("unsupported checkpoint identity schema")
        groups = _require_mapping(payload["groups"], "identity groups")
        raw_digest = payload["digest"]
        if not isinstance(raw_digest, str) or not _SHA256_RE.fullmatch(raw_digest):
            raise CheckpointError("identity digest is invalid")
        identity = cls.from_groups(groups)  # type: ignore[arg-type]
        if identity.digest != raw_digest:
            raise CheckpointError("identity digest does not match canonical groups")
        return identity

    def to_dict(self) -> dict[str, object]:
        """Return the exact JSON object persisted in ``identity.json``."""

        return {"schema": _SCHEMA_VERSION, "groups": dict(self.groups), "digest": self.digest}

    def differing_groups(self, other: "CheckpointIdentity") -> tuple[IdentityGroup, ...]:
        """Return identity groups whose canonical values differ."""

        return tuple(
            group
            for group in _IDENTITY_GROUPS
            if self.groups[group] != other.groups[group]
        )


@dataclass(frozen=True)
class CheckpointState:
    """One immutable turn-boundary checkpoint."""

    checkpoint_id: str
    parent_id: str | None
    committed_turn: int
    next_turn: int
    phase: str
    status: Literal["complete", "incomplete"]
    continuity_mode: Literal["native-resume", "handoff"]
    turn_prefix_digest: str
    identity_digest: str

    def __post_init__(self) -> None:
        if not _CHECKPOINT_ID_RE.fullmatch(self.checkpoint_id):
            raise CheckpointError("checkpoint_id is invalid")
        if self.parent_id is not None and not _CHECKPOINT_ID_RE.fullmatch(self.parent_id):
            raise CheckpointError("parent_id is invalid")
        if not isinstance(self.committed_turn, int) or isinstance(self.committed_turn, bool) or self.committed_turn < 0:
            raise CheckpointError("committed_turn must be a non-negative integer")
        if self.next_turn != self.committed_turn + 1:
            raise CheckpointError("next_turn must immediately follow committed_turn")
        if not self.phase.strip():
            raise CheckpointError("phase must not be empty")
        if self.status not in {"complete", "incomplete"}:
            raise CheckpointError("status must be complete or incomplete")
        if self.continuity_mode not in {"native-resume", "handoff"}:
            raise CheckpointError("continuity_mode is invalid")
        for field_name, value in (
            ("turn_prefix_digest", self.turn_prefix_digest),
            ("identity_digest", self.identity_digest),
        ):
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                raise CheckpointError(f"{field_name} must be a sha256 hex digest")
        _validate_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "CheckpointState":
        """Decode a state record and validate every field."""

        payload = _require_mapping(value, "checkpoint state")
        expected = {
            "schema",
            "checkpoint_id",
            "parent_id",
            "committed_turn",
            "next_turn",
            "phase",
            "status",
            "continuity_mode",
            "turn_prefix_digest",
            "identity_digest",
        }
        _require_exact_keys(payload, expected, "checkpoint state")
        if payload["schema"] != _SCHEMA_VERSION:
            raise CheckpointError("unsupported checkpoint state schema")
        fields = {key: payload[key] for key in expected - {"schema"}}
        if not isinstance(fields["checkpoint_id"], str) or not isinstance(fields["phase"], str):
            raise CheckpointError("checkpoint state string field is invalid")
        if fields["parent_id"] is not None and not isinstance(fields["parent_id"], str):
            raise CheckpointError("parent_id must be a string or null")
        if not isinstance(fields["committed_turn"], int) or isinstance(fields["committed_turn"], bool):
            raise CheckpointError("committed_turn must be an integer")
        if not isinstance(fields["next_turn"], int) or isinstance(fields["next_turn"], bool):
            raise CheckpointError("next_turn must be an integer")
        if not isinstance(fields["status"], str) or not isinstance(fields["continuity_mode"], str):
            raise CheckpointError("checkpoint state enum field is invalid")
        for key in ("turn_prefix_digest", "identity_digest"):
            if not isinstance(fields[key], str):
                raise CheckpointError(f"{key} must be a string")
        return cls(**fields)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        """Return the JSON object persisted in a state record and journal."""

        return {
            "schema": _SCHEMA_VERSION,
            "checkpoint_id": self.checkpoint_id,
            "parent_id": self.parent_id,
            "committed_turn": self.committed_turn,
            "next_turn": self.next_turn,
            "phase": self.phase,
            "status": self.status,
            "continuity_mode": self.continuity_mode,
            "turn_prefix_digest": self.turn_prefix_digest,
            "identity_digest": self.identity_digest,
        }


@dataclass(frozen=True)
class ResumeDecision:
    """Explicit result of asking whether a checkpoint may be used."""

    action: DecisionAction
    checkpoint: CheckpointState | None
    reason: str

    @property
    def accepted(self) -> bool:
        """Whether the decision permits the requested operation."""

        return self.action in {"resume", "regrade"}


class CheckpointStore:
    """Persist and recover immutable per-turn checkpoints under ``root``."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.identity_path = self.root / "identity.json"
        self.latest_path = self.root / "latest.json"
        self.journal_path = self.root / "journal.jsonl"
        self.records_dir = self.root / "checkpoints"

    def initialize(self, identity: CheckpointIdentity) -> None:
        """Create the store identity, or verify an existing one unchanged."""

        if self.identity_path.exists():
            existing = self.read_identity()
            if existing.digest != identity.digest:
                raise CheckpointError("checkpoint store identity already exists and differs")
            return
        _atomic_write_json(self.identity_path, identity.to_dict())

    def read_identity(self) -> CheckpointIdentity:
        """Read and verify the persisted execution identity."""

        return CheckpointIdentity.from_dict(_read_json(self.identity_path))  # type: ignore[arg-type]

    def commit(self, state: CheckpointState) -> None:
        """Atomically append a state checkpoint and advance ``latest.json``.

        An incomplete state may be recorded for diagnostics, but it is never
        returned as an accepted resume decision.  A later checkpoint must
        continue the current complete prefix; an incomplete turn cannot be
        silently skipped.
        """

        identity = self.read_identity()
        if state.identity_digest != identity.digest:
            raise CheckpointError("checkpoint state identity does not match the store")
        current = self.latest()
        if current is None:
            if state.parent_id is not None:
                raise CheckpointError("first checkpoint cannot have a parent")
        else:
            if current.status != "complete":
                raise CheckpointError("cannot append after an incomplete checkpoint")
            if state.parent_id != current.checkpoint_id:
                raise CheckpointError("checkpoint parent does not match the committed prefix")
            if state.committed_turn != current.committed_turn + 1:
                raise CheckpointError("checkpoint turn does not immediately follow the committed prefix")
        record = state.to_dict()
        record_path = self.records_dir / f"{state.checkpoint_id}.json"
        if record_path.exists():
            existing = CheckpointState.from_dict(_read_json(record_path))  # type: ignore[arg-type]
            if existing != state:
                raise CheckpointError("checkpoint_id already names a different state")
            raise CheckpointError("checkpoint_id is already committed")
        _atomic_write_json(record_path, record)
        state_digest = _digest(record)
        _append_journal(
            self.journal_path,
            {
                "schema": _SCHEMA_VERSION,
                "event": "commit",
                "checkpoint": record,
                "state_digest": state_digest,
            },
        )
        _atomic_write_json(
            self.latest_path,
            {"schema": _SCHEMA_VERSION, "checkpoint_id": state.checkpoint_id, "state_digest": state_digest},
        )

    def latest(self) -> CheckpointState | None:
        """Return the newest valid checkpoint without repairing the store."""

        pointer = self._read_latest_pointer()
        if pointer is not None:
            state = self._state_for_pointer(pointer)
            if state is not None and self._valid_chain(state):
                return state
        return self._recover_from_journal()

    def decide(self, identity: CheckpointIdentity, *, mode: ResumeMode = "native-resume") -> ResumeDecision:
        """Decide whether ``identity`` may resume or explicitly regrade.

        ``native-resume`` requires all four identity groups to match.  The
        separate ``report-only`` mode permits only a grading-group change and
        returns ``regrade``; scenario, skill, harness, model, supervisor, and
        other execution changes remain rejected through their containing
        groups.
        """

        if mode not in {"native-resume", "report-only"}:
            raise ValueError("mode must be native-resume or report-only")
        stored_identity = self.read_identity()
        differences = stored_identity.differing_groups(identity)
        forbidden = tuple(group for group in differences if group != "grading")
        if forbidden:
            return ResumeDecision(
                "reject",
                None,
                f"identity mismatch in execution groups: {', '.join(forbidden)}",
            )
        if "grading" in differences and mode != "report-only":
            return ResumeDecision("reject", None, "grading identity differs; use report-only explicitly")
        checkpoint = self.latest()
        if checkpoint is None:
            return ResumeDecision("reject", None, "no checkpoint is available")
        if checkpoint.identity_digest != stored_identity.digest:
            return ResumeDecision("reject", None, "checkpoint identity digest does not match the store")
        if checkpoint.status != "complete":
            return ResumeDecision("reject", checkpoint, "latest checkpoint is incomplete")
        if mode == "report-only":
            return ResumeDecision("regrade", checkpoint, "complete checkpoint accepted for report-only regrading")
        if checkpoint.continuity_mode != "native-resume":
            return ResumeDecision(
                "reject",
                checkpoint,
                f"checkpoint requires {checkpoint.continuity_mode}; native resume is unavailable",
            )
        return ResumeDecision("resume", checkpoint, "complete checkpoint accepted for native resume")

    def _read_latest_pointer(self) -> Mapping[str, object] | None:
        if not self.latest_path.exists():
            return None
        try:
            payload = _read_json(self.latest_path)
            mapping = _require_mapping(payload, "latest pointer")
            _require_exact_keys(mapping, {"schema", "checkpoint_id", "state_digest"}, "latest pointer")
            if mapping["schema"] != _SCHEMA_VERSION:
                return None
            if not isinstance(mapping["checkpoint_id"], str) or not isinstance(mapping["state_digest"], str):
                return None
            if not _SHA256_RE.fullmatch(mapping["state_digest"]):
                return None
            return mapping
        except CheckpointError:
            return None

    def _state_for_pointer(self, pointer: Mapping[str, object]) -> CheckpointState | None:
        checkpoint_id = pointer["checkpoint_id"]
        if not isinstance(checkpoint_id, str):
            return None
        record_path = self.records_dir / f"{checkpoint_id}.json"
        try:
            state = CheckpointState.from_dict(_read_json(record_path))  # type: ignore[arg-type]
            if _digest(state.to_dict()) != pointer["state_digest"]:
                return None
            return state
        except CheckpointError:
            return None

    def _valid_chain(self, state: CheckpointState) -> bool:
        """Verify that every committed prefix record exists and is contiguous."""

        seen: set[str] = set()
        current = state
        while True:
            if current.checkpoint_id in seen:
                return False
            seen.add(current.checkpoint_id)
            if current.parent_id is None:
                return current.committed_turn == 0 or current.committed_turn == 1
            parent_path = self.records_dir / f"{current.parent_id}.json"
            try:
                parent = CheckpointState.from_dict(_read_json(parent_path))  # type: ignore[arg-type]
            except CheckpointError:
                return False
            if parent.identity_digest != current.identity_digest:
                return False
            if current.committed_turn != parent.committed_turn + 1:
                return False
            current = parent

    def _recover_from_journal(self) -> CheckpointState | None:
        if not self.journal_path.exists():
            return None
        try:
            lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        for line in reversed(lines):
            try:
                payload = json.loads(line)
                mapping = _require_mapping(payload, "journal entry")
                _require_exact_keys(mapping, {"schema", "event", "checkpoint", "state_digest"}, "journal entry")
                if mapping["schema"] != _SCHEMA_VERSION or mapping["event"] != "commit":
                    continue
                raw_state = _require_mapping(mapping["checkpoint"], "journal checkpoint")
                state = CheckpointState.from_dict(raw_state)
                if mapping["state_digest"] != _digest(state.to_dict()):
                    continue
                if self._valid_chain(state):
                    return state
            except (CheckpointError, json.JSONDecodeError, TypeError):
                continue
        return None


__all__ = [
    "CheckpointError",
    "CheckpointIdentity",
    "CheckpointState",
    "CheckpointStore",
    "ResumeDecision",
]

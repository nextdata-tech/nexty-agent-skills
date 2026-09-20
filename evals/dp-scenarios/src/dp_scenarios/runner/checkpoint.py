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
from pathlib import PurePosixPath
import re
import tempfile
from typing import Literal
import uuid


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
_SCHEMA_VERSION = 2
_SOURCE_SNAPSHOT_SCHEMA = 1
_SOURCE_SNAPSHOT_DIR = "source-snapshots"
_SOURCE_SNAPSHOT_MANIFEST = "manifest.json"
_SECRET_KEY_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")
_SECRET_WORDS = frozenset(
    {
        "key",
        "token",
        "secret",
        "password",
        "passwd",
        "auth",
        "authorization",
        "credential",
        "cookie",
        "oauth",
        "apikey",
        "accesstoken",
        "refreshtoken",
        "oauthtoken",
        "oauthkey",
        "setcookie",
        "keychain",
    }
)
# Lowercase run-together spellings are not recoverable by the tokenizer above;
# keep the common credential compounds explicit instead of restoring broad
# substring matching (which classified ordinary keys such as ``monkey``).
_SECRET_COMPOUND_WORDS = frozenset(
    {
        "clientsecret",
        "privatekey",
        "secretkey",
        "sessionkey",
        "accesskey",
        "authtoken",
        "bearertoken",
    }
)
_SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
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
    words = tuple(part.casefold() for part in _SECRET_KEY_RE.findall(key))
    if not words:
        return False
    if len(words) == 1 and words[0] in _SECRET_COMPOUND_WORDS:
        return True
    # Preserve the old predicate's protection for credential-bearing words
    # without treating every generic ``*_key`` field as a credential.  Runtime
    # metadata legitimately contains names such as ``route_keys`` and
    # ``key_id``; only a key paired with a credential qualifier is sensitive.
    normalized_words = tuple(
        word[:-1] if word.endswith("s") and word[:-1] in _SECRET_WORDS else word
        for word in words
    )
    if any(word in _SECRET_WORDS - {"key"} for word in normalized_words):
        return True
    return any(
        normalized_words[index : index + 2]
        in {
            ("access", "token"),
            ("api", "key"),
            ("access", "key"),
            ("client", "key"),
            ("oauth", "key"),
            ("oauth", "token"),
            ("private", "key"),
            ("refresh", "token"),
            ("session", "key"),
            ("secret", "key"),
            ("set", "cookie"),
        }
        for index in range(len(words) - 1)
    )


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
    # Three-component release versions are common identity values, not JWTs.
    if _SEMVER_RE.fullmatch(stripped):
        return False
    if stripped.startswith("-----BEGIN ") and stripped.endswith("-----"):
        return True
    # Compact JWTs have a base64url-encoded JSON header beginning with ``eyJ``.
    # Requiring that marker avoids treating ordinary prose with three periods
    # as a credential while still rejecting the common bearer-token shape.
    parts = stripped.split(".")
    if len(parts) == 3 and parts[0].startswith("eyJ") and all(
        len(part) >= 8 and re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts
    ):
        return True
    return False


def redact_json(value: object) -> object:
    """Return JSON data safe to retain in a checkpoint or report.

    Live transcripts and tool results can contain credential-shaped text even
    when the surrounding observation is useful for local continuation.  The
    general payload writer remains fail-closed; this explicit boundary instead
    replaces secret-looking mapping values and scalar values before a
    report-safe recording is handed to that writer.  Secret keys remain in
    the result with an explicit placeholder so the JSON shape is preserved.
    """

    if isinstance(value, str):
        return "[redacted]" if _is_obvious_secret_value(value) else value
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]" if _is_secret_key(str(key)) else redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_json(item) for item in value]
    return value


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
            if reject_secrets and _is_secret_key(raw_key) and raw_item != "[redacted]":
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


def canonical_digest(value: object) -> str:
    """Return the digest used for a validated, credential-free JSON value."""

    return _digest(_validate_json(value))


def checkpoint_prefix_digest(
    payload: Mapping[str, object],
    *,
    checkpoint_id: str,
    parent_id: str | None,
    parent_prefix_digest: str | None,
    committed_turn: int,
    phase: str,
    operator_script_hash: str,
    identity_digest: str,
) -> str:
    """Digest a prefix together with the metadata that gives it meaning."""

    if parent_prefix_digest is not None and not _SHA256_RE.fullmatch(parent_prefix_digest):
        raise CheckpointError("parent prefix digest is invalid")
    if not _SHA256_RE.fullmatch(identity_digest):
        raise CheckpointError("checkpoint identity digest is invalid")
    if not isinstance(committed_turn, int) or isinstance(committed_turn, bool) or committed_turn < 1:
        raise CheckpointError("committed_turn must be a positive integer")
    if not isinstance(phase, str) or not phase.strip():
        raise CheckpointError("phase must not be empty")
    if not isinstance(operator_script_hash, str) or not operator_script_hash.strip():
        raise CheckpointError("operator script hash must not be empty")
    return _digest(
        _validate_json(
            {
                "schema": 1,
                "checkpoint_id": checkpoint_id,
                "parent": {"id": parent_id, "prefix_digest": parent_prefix_digest},
                "committed_turn": committed_turn,
                "phase": phase,
                "operator_script_hash": operator_script_hash,
                "identity_digest": identity_digest,
                "payload": payload,
            }
        )
    )


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


def _validate_payload_ref(value: str) -> None:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise CheckpointError("payload_ref must be a non-empty relative path")


def _validate_source_snapshot_file_ref(value: str) -> None:
    if not value or "\\" in value:
        raise CheckpointError("checkpoint source snapshot path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise CheckpointError("checkpoint source snapshot path is invalid")
    if path.name == _SOURCE_SNAPSHOT_MANIFEST:
        raise CheckpointError("checkpoint source snapshot path is reserved")


def _validate_source_snapshot_content(path: str, _content: bytes) -> None:
    """Reject obvious credential files before private bytes are retained.

    Do not scan ordinary source text for credential-shaped examples: closure
    code commonly contains literal ``Bearer``/environment-name strings that
    are not credential values.  The trusted supervisor credential is not in
    the agent workspace; path-level exclusion is the safe boundary here.
    """

    names = {part.casefold() for part in PurePosixPath(path).parts}
    if any(
        name == ".env"
        or name.startswith(".env.")
        or name in {"credentials", "credentials.json", "secrets", "secrets.json", "keychain"}
        for name in names
    ):
        raise CheckpointError("checkpoint source snapshot refuses environment files")


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(content)
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
class ClaudeSessionIdentity:
    """Credential-free Claude continuation identity.

    Claude session ids are opaque provider identifiers, so the checkpoint
    contract accepts only their canonical UUID spelling.  The execution
    digest binds the provider session to the exact runner identity that
    created it; a UUID from another run is never enough to resume.
    """

    session_id: str
    execution_identity_digest: str

    def __post_init__(self) -> None:
        try:
            parsed = uuid.UUID(self.session_id)
        except (AttributeError, ValueError, TypeError) as exc:
            raise CheckpointError("Claude session id must be a UUID") from exc
        if str(parsed) != self.session_id:
            raise CheckpointError("Claude session id must use canonical UUID spelling")
        if not _SHA256_RE.fullmatch(self.execution_identity_digest):
            raise CheckpointError("Claude session execution identity must be a sha256 hex digest")

    def to_dict(self) -> dict[str, object]:
        """Return the only session facts allowed in a checkpoint."""

        return {
            "session_id": self.session_id,
            "execution_identity_digest": self.execution_identity_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ClaudeSessionIdentity":
        payload = _require_mapping(value, "Claude session identity")
        _require_exact_keys(
            payload,
            {"session_id", "execution_identity_digest"},
            "Claude session identity",
        )
        if not isinstance(payload["session_id"], str) or not isinstance(
            payload["execution_identity_digest"], str
        ):
            raise CheckpointError("Claude session identity fields are invalid")
        return cls(payload["session_id"], payload["execution_identity_digest"])


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
    payload_ref: str | None = None
    payload_digest: str | None = None
    native_session: ClaudeSessionIdentity | None = None

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
        if self.continuity_mode == "native-resume" and self.native_session is None:
            raise CheckpointError("native-resume checkpoints require a Claude session identity")
        if self.continuity_mode == "handoff" and self.native_session is not None:
            raise CheckpointError("handoff checkpoints must not contain a Claude session identity")
        if self.native_session is not None and self.native_session.execution_identity_digest != self.identity_digest:
            raise CheckpointError("Claude session identity does not match checkpoint execution identity")
        for field_name, value in (
            ("turn_prefix_digest", self.turn_prefix_digest),
            ("identity_digest", self.identity_digest),
        ):
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                raise CheckpointError(f"{field_name} must be a sha256 hex digest")
        if (self.payload_ref is None) != (self.payload_digest is None):
            raise CheckpointError("payload_ref and payload_digest must be provided together")
        if self.payload_ref is not None:
            _validate_payload_ref(self.payload_ref)
            assert self.payload_digest is not None
            if not _SHA256_RE.fullmatch(self.payload_digest):
                raise CheckpointError("payload_digest must be a sha256 hex digest")
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
            "payload_ref",
            "payload_digest",
            "native_session",
        }
        # Checkpoint schema v2 handoff records predate native continuation.
        # They remain readable as handoff evidence, but can never become a
        # native resume because the required session identity is absent.
        legacy = set(payload) == expected - {"native_session"}
        if not legacy:
            _require_exact_keys(payload, expected, "checkpoint state")
        if payload["schema"] != _SCHEMA_VERSION:
            raise CheckpointError("unsupported checkpoint state schema")
        fields = {key: payload.get(key) for key in expected - {"schema"}}
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
        raw_native_session = fields.get("native_session")
        native_session = (
            ClaudeSessionIdentity.from_dict(raw_native_session)
            if isinstance(raw_native_session, Mapping)
            else None
        )
        fields["native_session"] = native_session
        return cls(**fields)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        """Return the JSON object persisted in a state record and journal."""

        result = {
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
            "payload_ref": self.payload_ref,
            "payload_digest": self.payload_digest,
        }
        if self.native_session is not None:
            result["native_session"] = self.native_session.to_dict()
        return result


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

    def write_payload(self, checkpoint_id: str, payload: object) -> tuple[str, str]:
        """Write a credential-free JSON payload before its state is committed.

        Payloads are deliberately separate from state records so a caller can
        persist a redacted replay or handoff manifest first and then make the
        corresponding turn checkpoint visible atomically.  The returned
        relative reference and digest belong in ``CheckpointState``.
        """

        if not _CHECKPOINT_ID_RE.fullmatch(checkpoint_id):
            raise CheckpointError("checkpoint_id is invalid")
        validated = _validate_json(payload)
        if not isinstance(validated, Mapping):
            raise CheckpointError("checkpoint payload must be a JSON object")
        payload_ref = f"checkpoints/{checkpoint_id}.payload.json"
        payload_path = self.root / payload_ref
        payload_digest = _digest(validated)
        if payload_path.exists():
            existing = _validate_json(_read_json(payload_path))
            if not isinstance(existing, Mapping) or _digest(existing) != payload_digest:
                raise CheckpointError("checkpoint payload already exists with different content")
            return payload_ref, payload_digest
        _atomic_write_json(payload_path, validated)
        return payload_ref, payload_digest

    def _source_snapshot_root(self, checkpoint_id: str) -> Path:
        if not _CHECKPOINT_ID_RE.fullmatch(checkpoint_id):
            raise CheckpointError("checkpoint_id is invalid")
        return self.root / _SOURCE_SNAPSHOT_DIR / checkpoint_id

    def write_source_snapshot(
        self,
        checkpoint_id: str,
        files: Sequence[tuple[int, int, str, bytes]],
    ) -> None:
        """Persist the private bytes needed to replay one checkpoint prefix.

        The report payload keeps only touched-file digests.  Those digests are
        insufficient when a later turn edits the retained agent workspace,
        so native continuation also keeps an owner-readable, mode-0700 source
        snapshot outside the report payload.  The snapshot is addressed by
        checkpoint id and is never copied into evidence artifacts.
        """

        snapshot_root = self._source_snapshot_root(checkpoint_id)
        entries: list[dict[str, object]] = []
        seen: set[tuple[int, int]] = set()
        for entry_index, item in enumerate(files):
            if len(item) != 4:
                raise CheckpointError("checkpoint source snapshot entry is invalid")
            turn_index, file_index, path, content = item
            if (
                not isinstance(turn_index, int)
                or isinstance(turn_index, bool)
                or turn_index < 1
                or not isinstance(file_index, int)
                or isinstance(file_index, bool)
                or file_index < 0
                or not isinstance(path, str)
                or not isinstance(content, bytes)
            ):
                raise CheckpointError("checkpoint source snapshot entry is invalid")
            _validate_source_snapshot_file_ref(path)
            _validate_source_snapshot_content(path, content)
            key = (turn_index, file_index)
            if key in seen:
                raise CheckpointError("checkpoint source snapshot has duplicate file entries")
            seen.add(key)
            file_ref = f"files/{entry_index:06d}.bin"
            entries.append(
                {
                    "turn_index": turn_index,
                    "file_index": file_index,
                    "path": path,
                    "file_ref": file_ref,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
            )

        manifest: dict[str, object] = {
            "schema": _SOURCE_SNAPSHOT_SCHEMA,
            "checkpoint_id": checkpoint_id,
            "files": entries,
        }
        validated = _validate_json(manifest)
        if not isinstance(validated, Mapping):
            raise CheckpointError("checkpoint source snapshot manifest is invalid")

        existing_manifest = snapshot_root / _SOURCE_SNAPSHOT_MANIFEST
        if existing_manifest.exists():
            existing = _read_json(existing_manifest)
            if not isinstance(existing, Mapping) or _digest(existing) != _digest(validated):
                raise CheckpointError("checkpoint source snapshot already exists with different content")
            # Re-read below so an existing manifest cannot make a missing or
            # modified private file look complete.
            self.read_source_snapshot(checkpoint_id)
            return

        _private_directory(snapshot_root)
        files_root = snapshot_root / "files"
        _private_directory(files_root)
        for entry, item in zip(entries, files, strict=True):
            file_path = (snapshot_root / str(entry["file_ref"])).resolve()
            if snapshot_root.resolve() not in file_path.parents:
                raise CheckpointError("checkpoint source snapshot path escapes the store")
            _atomic_write_bytes(file_path, item[3])
        _atomic_write_json(existing_manifest, validated)

    def read_source_snapshot(
        self,
        checkpoint_id: str,
    ) -> dict[tuple[int, int], tuple[str, bytes]] | None:
        """Read and verify one private source snapshot, if present.

        ``None`` means the checkpoint predates private source snapshots and
        deliberately preserves the old retained-workspace fallback.
        """

        snapshot_root = self._source_snapshot_root(checkpoint_id)
        manifest_path = snapshot_root / _SOURCE_SNAPSHOT_MANIFEST
        if not manifest_path.exists():
            return None
        raw = _read_json(manifest_path)
        manifest = _require_mapping(raw, "checkpoint source snapshot manifest")
        _require_exact_keys(manifest, {"schema", "checkpoint_id", "files"}, "checkpoint source snapshot manifest")
        if manifest["schema"] != _SOURCE_SNAPSHOT_SCHEMA or manifest["checkpoint_id"] != checkpoint_id:
            raise CheckpointError("checkpoint source snapshot manifest identity is invalid")
        raw_files = manifest["files"]
        if not isinstance(raw_files, Sequence) or isinstance(raw_files, (str, bytes)):
            raise CheckpointError("checkpoint source snapshot files must be a list")
        result: dict[tuple[int, int], tuple[str, bytes]] = {}
        for raw_entry in raw_files:
            entry = _require_mapping(raw_entry, "checkpoint source snapshot entry")
            _require_exact_keys(
                entry,
                {"turn_index", "file_index", "path", "file_ref", "sha256", "size_bytes"},
                "checkpoint source snapshot entry",
            )
            turn_index = entry["turn_index"]
            file_index = entry["file_index"]
            path = entry["path"]
            file_ref = entry["file_ref"]
            digest = entry["sha256"]
            size_bytes = entry["size_bytes"]
            if (
                not isinstance(turn_index, int)
                or isinstance(turn_index, bool)
                or turn_index < 1
                or not isinstance(file_index, int)
                or isinstance(file_index, bool)
                or file_index < 0
                or not isinstance(path, str)
                or not isinstance(file_ref, str)
                or not isinstance(digest, str)
                or not _SHA256_RE.fullmatch(digest)
                or not isinstance(size_bytes, int)
                or isinstance(size_bytes, bool)
                or size_bytes < 0
            ):
                raise CheckpointError("checkpoint source snapshot entry is invalid")
            _validate_source_snapshot_file_ref(path)
            _validate_source_snapshot_file_ref(file_ref)
            key = (turn_index, file_index)
            if key in result:
                raise CheckpointError("checkpoint source snapshot has duplicate file entries")
            file_path = (snapshot_root / file_ref).resolve()
            if snapshot_root.resolve() not in file_path.parents:
                raise CheckpointError("checkpoint source snapshot path escapes the store")
            try:
                content = file_path.read_bytes()
            except OSError as exc:
                raise CheckpointError("checkpoint source snapshot bytes are unavailable") from exc
            if len(content) != size_bytes or hashlib.sha256(content).hexdigest() != digest:
                raise CheckpointError("checkpoint source snapshot bytes changed")
            result[key] = (path, content)
        return result

    def read_payload(self, state: CheckpointState) -> Mapping[str, object] | None:
        """Read and verify a checkpoint payload without repairing the store."""

        if state.payload_ref is None:
            return None
        assert state.payload_digest is not None
        _validate_payload_ref(state.payload_ref)
        payload_path = (self.root / state.payload_ref).resolve()
        root = self.root.resolve()
        if root not in payload_path.parents:
            raise CheckpointError("checkpoint payload escapes the store root")
        payload = _read_json(payload_path)
        validated = _validate_json(payload)
        if not isinstance(validated, Mapping):
            raise CheckpointError("checkpoint payload must be a JSON object")
        if _digest(validated) != state.payload_digest:
            raise CheckpointError("checkpoint payload digest does not match state")
        return validated

    def _prefix_digest_matches(
        self,
        state: CheckpointState,
        *,
        parent_prefix_digest: str | None,
    ) -> bool:
        """Verify a payload-backed prefix against its chain and script pins."""

        # Payload-less states predate the durable handoff payload contract.
        # Keep them readable for the low-level store tests; all harness-emitted
        # checkpoints carry a payload and take the strict path below.
        if state.payload_ref is None:
            return True
        try:
            identity = self.read_identity()
            operator_script_hash = identity.groups["run"].get("operator_script_hash")
            if not isinstance(operator_script_hash, str):
                return False
            payload = self.read_payload(state)
            if payload is None:
                return False
            expected = checkpoint_prefix_digest(
                payload,
                checkpoint_id=state.checkpoint_id,
                parent_id=state.parent_id,
                parent_prefix_digest=parent_prefix_digest,
                committed_turn=state.committed_turn,
                phase=state.phase,
                operator_script_hash=operator_script_hash,
                identity_digest=identity.digest,
            )
        except CheckpointError:
            return False
        return expected == state.turn_prefix_digest

    def verify_prefix_digest(self, state: CheckpointState) -> bool:
        """Verify one persisted prefix against its stored parent chain."""

        parent_prefix_digest: str | None = None
        if state.parent_id is not None:
            try:
                parent = CheckpointState.from_dict(
                    _read_json(self.records_dir / f"{state.parent_id}.json")
                )  # type: ignore[arg-type]
            except CheckpointError:
                return False
            if parent.identity_digest != state.identity_digest:
                return False
            parent_prefix_digest = parent.turn_prefix_digest
        return self._prefix_digest_matches(
            state,
            parent_prefix_digest=parent_prefix_digest,
        )

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
        if state.payload_ref is not None:
            self.read_payload(state)
        current = self.latest()
        if current is None:
            if state.parent_id is not None:
                raise CheckpointError("first checkpoint cannot have a parent")
            if state.committed_turn != 1:
                raise CheckpointError("first checkpoint must commit turn 1")
        else:
            if current.status != "complete":
                raise CheckpointError("cannot append after an incomplete checkpoint")
            if state.parent_id != current.checkpoint_id:
                raise CheckpointError("checkpoint parent does not match the committed prefix")
            if state.committed_turn != current.committed_turn + 1:
                raise CheckpointError("checkpoint turn does not immediately follow the committed prefix")
        if not self._prefix_digest_matches(
            state,
            parent_prefix_digest=current.turn_prefix_digest if current is not None else None,
        ):
            raise CheckpointError("checkpoint prefix digest does not match its chain or script metadata")
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

    def decide(
        self,
        expected_identity: CheckpointIdentity,
        *,
        mode: ResumeMode = "native-resume",
        checkpoint_id: str | None = None,
    ) -> ResumeDecision:
        """Compare a caller-supplied identity before resuming or regrading.

        ``native-resume`` requires all four identity groups to match.  The
        separate ``report-only`` mode permits only a grading-group change and
        returns ``regrade``; scenario, skill, harness, model, supervisor, and
        other execution changes remain rejected through their containing
        groups.
        """

        if mode not in {"native-resume", "report-only"}:
            raise ValueError("mode must be native-resume or report-only")
        stored_identity = self.read_identity()
        differences = stored_identity.differing_groups(expected_identity)
        forbidden = tuple(group for group in differences if group != "grading")
        if forbidden:
            return ResumeDecision(
                "reject",
                None,
                f"identity mismatch in execution groups: {', '.join(forbidden)}",
            )
        if "grading" in differences and mode != "report-only":
            return ResumeDecision("reject", None, "grading identity differs; use report-only explicitly")
        checkpoint = self.latest() if checkpoint_id is None else self._checkpoint_by_id(checkpoint_id)
        if checkpoint is None:
            return ResumeDecision(
                "reject",
                None,
                "requested checkpoint is unavailable"
                if checkpoint_id is not None
                else "no checkpoint is available",
            )
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

    def _checkpoint_by_id(self, checkpoint_id: str) -> CheckpointState | None:
        """Read one requested checkpoint and validate its committed prefix."""

        if not _CHECKPOINT_ID_RE.fullmatch(checkpoint_id):
            return None
        try:
            state = CheckpointState.from_dict(
                _read_json(self.records_dir / f"{checkpoint_id}.json")
            )  # type: ignore[arg-type]
        except CheckpointError:
            return None
        return state if self._valid_chain(state) else None

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
            try:
                if current.identity_digest != self.read_identity().digest:
                    return False
            except CheckpointError:
                return False
            if current.parent_id is None:
                return current.committed_turn == 1 and self._prefix_digest_matches(
                    current,
                    parent_prefix_digest=None,
                )
            parent_path = self.records_dir / f"{current.parent_id}.json"
            try:
                parent = CheckpointState.from_dict(_read_json(parent_path))  # type: ignore[arg-type]
            except CheckpointError:
                return False
            if parent.identity_digest != current.identity_digest:
                return False
            if parent.status != "complete":
                return False
            if current.committed_turn != parent.committed_turn + 1:
                return False
            if not self._prefix_digest_matches(
                current,
                parent_prefix_digest=parent.turn_prefix_digest,
            ):
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
    "canonical_digest",
    "checkpoint_prefix_digest",
    "ClaudeSessionIdentity",
    "CheckpointError",
    "CheckpointIdentity",
    "CheckpointState",
    "CheckpointStore",
    "ResumeDecision",
]

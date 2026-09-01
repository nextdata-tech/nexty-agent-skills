"""Read-only dispatch and recorded-claims support for closure review."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .models import ReviewRun, ReviewerClaim, as_claim_sequence


Reviewer = Callable[[Path, str], object]


class ReviewDispatchError(RuntimeError):
    """Raised internally when a review cannot be examined."""


def _closure_files(root: Path) -> tuple[tuple[str, bytes], ...]:
    """Read a closure deterministically and reject links/special files."""

    if not root.exists():
        raise ReviewDispatchError(f"closure does not exist: {root}")
    if root.is_symlink():
        raise ReviewDispatchError(f"closure cannot be a symlink: {root}")
    if root.is_file():
        try:
            return ((root.name, root.read_bytes()),)
        except (OSError, UnicodeError) as exc:
            raise ReviewDispatchError(f"closure is unreadable: {root}: {exc}") from exc
    if not root.is_dir():
        raise ReviewDispatchError(f"closure is not a regular file or directory: {root}")

    files: list[tuple[str, bytes]] = []
    pending = [root]
    try:
        while pending:
            current = pending.pop()
            children = sorted(current.iterdir(), key=lambda child: child.name, reverse=True)
            for child in children:
                relative = child.relative_to(root).as_posix()
                if child.is_symlink():
                    raise ReviewDispatchError(f"closure contains an unsupported symlink: {relative}")
                if child.is_dir():
                    pending.append(child)
                elif child.is_file():
                    files.append((relative, child.read_bytes()))
                else:
                    raise ReviewDispatchError(f"closure contains a non-regular entry: {relative}")
    except ReviewDispatchError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ReviewDispatchError(f"closure is unreadable: {root}: {exc}") from exc
    return tuple(sorted(files))


def closure_content_digest(closure: str | Path) -> str:
    """Return a stable SHA-256 digest over closure paths and bytes.

    Directory names are included as structure markers, while file contents
    are read directly.  This means a recorded claim set is selected by the
    actual closure artifact rather than by its filesystem location.
    """

    root = Path(closure)
    files = _closure_files(root)
    digest = hashlib.sha256()
    if root.is_dir():
        digest.update(b"directory\0")
        directories = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_dir() and not path.is_symlink()
        )
        for relative in directories:
            digest.update(b"dir\0")
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
    else:
        digest.update(b"file\0")
    for relative, content in files:
        digest.update(b"file\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _make_read_only(path: Path) -> None:
    """Remove write bits from every snapshot entry before dispatch."""

    if path.is_file():
        path.chmod(0o444)
        return
    for child in path.rglob("*"):
        if child.is_symlink():
            raise ReviewDispatchError(f"snapshot contains an unsupported symlink: {child}")
        child.chmod(0o555 if child.is_dir() else 0o444)
    path.chmod(0o555)


def _read_only_snapshot(source: Path, temporary_root: Path) -> Path:
    """Copy a closure into a disposable, chmod-restricted reviewer namespace.

    The mode bits are a courtesy boundary for an honest reviewer, not a
    same-user write-proof sandbox.  The original closure is re-digested after
    review so tampering with the artifact is detected after the fact.
    """

    target = temporary_root / "closure"
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        target.mkdir()
        shutil.copy2(source, target / source.name)
        target = target / source.name
    _make_read_only(target)
    return target


def _claim_records(value: object, digest: str) -> tuple[ReviewerClaim, ...]:
    """Parse claims while deliberately ignoring any returned adjudication."""

    records = as_claim_sequence(value)
    used_ids: dict[str, int] = {}
    claims: list[ReviewerClaim] = []
    for index, raw in enumerate(records, start=1):
        raw_id = raw.get("id", raw.get("claim_id"))
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise ReviewDispatchError(f"review claim {index} has no id")
        claim_id = raw_id.strip()
        occurrence = used_ids.get(claim_id, 0) + 1
        used_ids[claim_id] = occurrence
        if occurrence > 1:
            raise ReviewDispatchError(f"review claims contain duplicate id: {claim_id}")
        statement = raw.get("claim")
        if not isinstance(statement, str) or not statement.strip():
            raise ReviewDispatchError(f"review claim {index} has no claim sentence")
        severity = raw.get("severity", "UNKNOWN")
        if not isinstance(severity, str) or not severity.strip():
            severity = "UNKNOWN"
        evidence = raw.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ReviewDispatchError(f"review claim {index} has no evidence")
        reason = raw.get("reason", raw.get("why_it_matters", ""))
        if not isinstance(reason, str):
            reason = ""
        why = raw.get("why_it_matters")
        if not isinstance(why, str):
            why = None
        identity = hashlib.sha256(
            f"{digest}\0{claim_id}\0{evidence.strip()}".encode("utf-8")
        ).hexdigest()
        claims.append(
            ReviewerClaim(
                claim_id=claim_id,
                identity=identity,
                severity=severity,
                claim=statement,
                evidence=evidence,
                reviewer_reason=reason,
                why_it_matters=why,
                raw=dict(raw),
            )
        )
    return tuple(claims)


@dataclass(frozen=True, slots=True)
class RecordedClaims:
    """A no-model review source keyed by closure content digest."""

    by_digest: Mapping[str, object]

    def lookup(self, digest: str) -> object:
        """Return the recorded output for ``digest`` or raise a clear error."""

        if digest not in self.by_digest:
            raise ReviewDispatchError(f"no recorded claims for closure digest {digest}")
        return self.by_digest[digest]


@dataclass(frozen=True, slots=True)
class CommandReviewer:
    """Small JSON/stdin adapter for a real read-only reviewer process.

    The command receives the read-only snapshot path as its final argument and
    the verbatim request on stdin.  It must print a JSON claims envelope.
    """

    command: tuple[str, ...]
    timeout_seconds: float = 120.0

    def __call__(self, closure: Path, original_request: str) -> object:
        if not self.command:
            raise ReviewDispatchError("review command is empty")
        completed = subprocess.run(
            [*self.command, str(closure)],
            input=original_request,
            text=True,
            capture_output=True,
            check=True,
            timeout=self.timeout_seconds,
            env={**os.environ, "DP_REVIEW_READ_ONLY": "1"},
        )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ReviewDispatchError("review command did not return JSON claims") from exc


@dataclass(frozen=True, slots=True)
class ReviewDispatcher:
    """Dispatch a reviewer against a disposable read-only closure snapshot."""

    reviewer: Reviewer | object | None = None
    recorded_claims: RecordedClaims | Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.reviewer is not None and self.recorded_claims is not None:
            raise ReviewDispatchError("configure either reviewer or recorded_claims, not both")

    def dispatch(self, closure: str | Path, original_request: str) -> ReviewRun:
        """Run or replay a review and fail closed on review-time errors.

        The reviewer receives only a disposable chmod-restricted copy.  Since
        a same-user reviewer can change that copy's mode bits, the original
        closure is re-digested after review; any original-artifact tampering is
        reported as an unexamined review.
        """

        source = Path(closure)
        if not isinstance(original_request, str):
            return ReviewRun(source, None, (), False, "invalid", "original request must be a string")
        digest: str | None = None
        mode = "reviewer"
        try:
            digest = closure_content_digest(source)
            with tempfile.TemporaryDirectory(prefix="dp-review-") as temporary_name:
                snapshot = _read_only_snapshot(source, Path(temporary_name))
                recorded = self.recorded_claims
                if recorded is not None:
                    mode = "recorded"
                    source_value = recorded.lookup(digest) if isinstance(recorded, RecordedClaims) else recorded.get(digest)
                    if source_value is None:
                        raise ReviewDispatchError(f"no recorded claims for closure digest {digest}")
                    output = source_value
                else:
                    if self.reviewer is None:
                        raise ReviewDispatchError("no reviewer or recorded claims source was supplied")
                    callback = self.reviewer
                    if not callable(callback) and hasattr(callback, "review"):
                        callback = getattr(callback, "review")
                    if not callable(callback):
                        raise ReviewDispatchError("reviewer must be callable or expose review()")
                    output = callback(snapshot, original_request)
                claims = _claim_records(output, digest)
            if closure_content_digest(source) != digest:
                raise ReviewDispatchError("closure changed during review")
            return ReviewRun(source, digest, claims, True, mode)
        except Exception as exc:  # fail closed: this is an unexamined review
            return ReviewRun(source, digest, (), False, mode, str(exc) or exc.__class__.__name__)

    __call__ = dispatch
    run = dispatch


# Short names keep the public surface convenient for scenario adapters while
# retaining the descriptive class name in documentation and tracebacks.
Dispatcher = ReviewDispatcher


def dispatch_review(
    closure: str | Path,
    original_request: str,
    *,
    reviewer: Reviewer | object | None = None,
    recorded_claims: RecordedClaims | Mapping[str, object] | None = None,
) -> ReviewRun:
    """Convenience wrapper for :class:`ReviewDispatcher`."""

    return ReviewDispatcher(reviewer=reviewer, recorded_claims=recorded_claims).dispatch(
        closure, original_request
    )


__all__ = [
    "CommandReviewer",
    "Dispatcher",
    "RecordedClaims",
    "ReviewDispatchError",
    "ReviewDispatcher",
    "Reviewer",
    "closure_content_digest",
    "dispatch_review",
]

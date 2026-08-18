"""Extract and compare API claims from installed skill text.

The invariant is that a source-span or source-file change cannot be mistaken
for a clean extraction.  Extraction is therefore read-only and reports a
drift finding; only the separate re-baseliner may approve new bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable, Mapping

from .claims import Baseline, Claim, ClaimsDocument, sha256_bytes


# There is deliberately no default skills root. The pack under test is the one
# installed in the isolated environment the agent runs in, so the caller must
# name it. A home-directory default would silently measure a globally installed
# pack that no agent actually uses, and report drift against text the runtime
# never saw.


@dataclass(frozen=True)
class DriftFinding:
    """A source change that needs explicit claims review."""

    claim_id: str
    skill_file: str
    line: int
    before: str
    after: str
    reason: str
    code: str = "claims/source_changed"
    blocking: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "skill_file": self.skill_file,
            "line": self.line,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
            "code": self.code,
            "blocking": self.blocking,
        }


class ClaimDriftError(ValueError):
    """Raised when extraction sees unapproved documentation changes."""

    def __init__(self, findings: Iterable[DriftFinding]):
        self.findings = tuple(findings)
        rendered = "; ".join(
            f"{finding.claim_id} at {finding.skill_file}:{finding.line}: {finding.reason}"
            for finding in self.findings
        )
        super().__init__(f"skill-text drift requires claims review: {rendered}")


@dataclass(frozen=True)
class ExtractionResult:
    """Claims and the unapproved changes found while extracting them."""

    claims: tuple[Claim, ...]
    baseline: Baseline
    drift: tuple[DriftFinding, ...] = ()
    advisories: tuple[DriftFinding, ...] = ()


_MARKER_RE = re.compile(
    r"CANARY_CLAIM\s+id=(?P<id>\S+)\s+code=(?P<code>\S+)\s+"
    r"direction=(?P<direction>\S+)(?:\s+kind=(?P<kind>\S+))?"
    r"(?:\s+probe=(?P<probe>\S+))?(?:\s+signature=(?P<signature>\S+))?"
)
_CONNECTOR_RE = re.compile(r"^\s*\|\s*(?P<name>CSV|Other file|Database|REST API)\b")
_API_SIGNATURE_RE = re.compile(
    r"^\s*[-*]\s+(?:\*\*)?`(?:source_aligned_input|data_product_input|"
    r"data_product_output|semantic_model|semantic_view)\([^`]*\)`"
)
_UNSUPPORTED_BULLET_RE = re.compile(
    r"^\s*[-*]\s+\*\*[^*]*(?:median does not exist|no\s+`?\.semantic_tools|"
    r"unsupported construct)[^*]*\*\*",
    re.IGNORECASE,
)
_DIRECTORY_RE = re.compile(r"^\s*└── data/|Same per-model layout as CSV:")


def source_skill_files(root: Path | str) -> tuple[Path, ...]:
    """Return installed skill Markdown files, including reference text."""

    skills_root = Path(root).expanduser().resolve()
    if not skills_root.is_dir():
        return ()
    files = {
        path
        for path in skills_root.rglob("*.md")
        if path.name == "SKILL.md" or "reference" in path.parts
    }
    return tuple(sorted(files))


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "claim"


def _expected_code(kind: str, direction: str, text: str) -> str:
    if direction == "documented-unsupported" or kind == "unsupported":
        return "structure/spec_compile_failed"
    if kind == "type":
        return "structure/spec_compile_failed"
    if kind == "companion":
        return "structure/companion_files_invalid"
    if kind == "secret":
        # Secrets are observed only by the real transform.  This is a
        # canary-owned build-phase code, not a fabricated supervisor check code.
        return "build/transform_import"
    if kind == "directory":
        return "structure/csv_source_invalid"
    if kind == "semantic":
        return "semantic/registry_invalid"
    if kind == "type":
        return "structure/closure_pinned"
    return "structure/closure_pinned"


def _build_signature(kind: str, text: str) -> str | None:
    """Return a literal child-trace signature for a build-observed claim."""

    if kind != "secret":
        return None
    for key in ("api_source", "db_source", "file_source", "csv_source"):
        if key in text:
            return f"KeyError: '{key}'"
    if "csv-source-path" in text and "secrets[...]" in text:
        return "KeyError: 'csv_source'"
    if "csv-source" in text:
        return "KeyError: 'csv_source'"
    return None


def _classifications(text: str) -> tuple[tuple[str, str], ...]:
    """Classify only an explicit marker or a deliberately narrow API surface."""

    if _UNSUPPORTED_BULLET_RE.match(text):
        return (("unsupported", "documented-unsupported"),)
    if _CONNECTOR_RE.match(text):
        return (("type", "documented-supported"),)
    if _DIRECTORY_RE.search(text):
        return (("directory", "documented-supported"),)
    if (
        "Transform secrets key:" in text
        or ("csv-source-path" in text and "secrets[...]" in text)
    ):
        return (("secret", "documented-supported"),)
    if text.lstrip().startswith("- Companion file:") or text.lstrip().startswith("├── csv-source-path"):
        return (("companion", "documented-supported"),)
    if _API_SIGNATURE_RE.match(text):
        if "semantic_model" in text or "semantic_view" in text:
            return (("semantic", "documented-supported"),)
        return (("type", "documented-supported"),)
    if text.lstrip().startswith("CANARY_CLAIM"):
        return (("api", "documented-supported"),)
    if "CANARY_CLAIM" in text:
        return (("semantic", "documented-supported"),)
    return ()


def _classify(text: str) -> tuple[str, str] | None:
    """Return the first narrow classification for compatibility with callers."""

    classifications = _classifications(text)
    return classifications[0] if classifications else None


def _claim_from_line(
    path: Path,
    skills_root: Path,
    line_number: int,
    line_bytes: bytes,
) -> tuple[Claim, ...]:
    text = line_bytes.decode("utf-8")
    marker = _MARKER_RE.search(text)
    if marker:
        classifications = ((marker.group("kind") or "api", marker.group("direction")),)
    else:
        classifications = _classifications(text)
    if not classifications:
        return ()
    relative = path.relative_to(skills_root).as_posix()
    token = sha256_bytes(line_bytes).split(":", 1)[1][:16]
    claims: list[Claim] = []
    for kind, direction in classifications:
        identity = marker.group("id") if marker else kind
        claim_id = f"{relative}:{_slug(identity)}:{token}"
        if not marker:
            claim_id = f"{relative}:{_slug(kind)}:{token}"
        requested_probe = marker.group("probe") if marker else None
        if requested_probe:
            probe_id = requested_probe
        elif direction == "documented-unsupported":
            probe_id = f"unsupported-{token}"
        else:
            probe_id = "kitchen-sink"
        claims.append(
            Claim(
                claim_id=claim_id,
                skill_file=relative,
                line=line_number,
                quote=text,
                content_hash=sha256_bytes(line_bytes),
                expected_finding_code=(
                    marker.group("code") if marker else _expected_code(kind, direction, text)
                ),
                direction=direction,
                category=kind,
                probe_id=probe_id,
                build_signature=(
                    marker.group("signature")
                    if marker and marker.group("signature")
                    else _build_signature(kind, text)
                ),
            )
        )
    return tuple(claims)


def _extract_from_files(files: Iterable[Path], skills_root: Path) -> tuple[Claim, ...]:
    claims: list[Claim] = []
    seen: set[tuple[str, str, str, str]] = set()
    for path in files:
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise OSError(f"cannot read installed skill text {path}: {exc}") from exc
        for line_number, raw_line in enumerate(content.splitlines(), start=1):
            line_bytes = raw_line
            for claim in _claim_from_line(path, skills_root, line_number, line_bytes):
                key = (claim.skill_file, claim.category, claim.direction, claim.quote)
                if key in seen:
                    continue
                seen.add(key)
                claims.append(claim)
    return tuple(claims)


def _baseline(files: Iterable[Path], claims: Iterable[Claim], skills_root: Path) -> Baseline:
    by_file: dict[str, list[str]] = {}
    for claim in claims:
        by_file.setdefault(claim.skill_file, []).append(claim.content_hash)
    hashes: dict[str, str] = {}
    for path in files:
        relative = path.relative_to(skills_root).as_posix()
        spans = sorted(by_file.get(relative, ()))
        hashes[relative] = sha256_bytes("\n".join(spans).encode("utf-8"))
    return Baseline(
        skill_files=hashes,
        reviewer="unreviewed",
        review_date="unreviewed",
        approves_claims_hash="unapproved",
    )


def _existing_claims(value: ClaimsDocument | Iterable[Claim] | None) -> tuple[Claim, ...]:
    if value is None:
        return ()
    if isinstance(value, ClaimsDocument):
        return value.claims
    return tuple(value)


def _compare(
    current: ExtractionResult,
    existing: ClaimsDocument,
) -> tuple[tuple[DriftFinding, ...], tuple[DriftFinding, ...]]:
    findings: list[DriftFinding] = []
    old_by_id = {claim.claim_id: claim for claim in existing.claims}
    current_by_id = {claim.claim_id: claim for claim in current.claims}
    seen: set[tuple[str, int, str]] = set()

    def add(finding: DriftFinding) -> None:
        key = (finding.claim_id, finding.line, finding.reason)
        if key not in seen:
            seen.add(key)
            findings.append(finding)

    unmatched_old = set(old_by_id)
    unmatched_new = set(current_by_id)

    def stable_prefix(claim_id: str) -> str:
        return claim_id.rsplit(":", 1)[0]

    def fallback_candidate(old: Claim, candidates: list[Claim]) -> Claim | None:
        """Match an ambiguous content-id change to its nearby source span."""

        nearby = [
            candidate
            for candidate in candidates
            if candidate.skill_file == old.skill_file
            and candidate.category == old.category
            and abs(candidate.line - old.line) <= 5
        ]
        if not nearby:
            return None
        nearest = min(abs(candidate.line - old.line) for candidate in nearby)
        closest = [candidate for candidate in nearby if abs(candidate.line - old.line) == nearest]
        return closest[0] if len(closest) == 1 else None

    for claim_id, old in old_by_id.items():
        new = current_by_id.get(claim_id)
        if new is None:
            candidates = [
                candidate
                for candidate_id, candidate in current_by_id.items()
                if candidate_id in unmatched_new and stable_prefix(candidate_id) == stable_prefix(claim_id)
            ]
            new = candidates[0] if len(candidates) == 1 else fallback_candidate(old, candidates)
        if new is None:
            add(
                DriftFinding(
                    claim_id=claim_id,
                    skill_file=old.skill_file,
                    line=old.line,
                    before=old.quote,
                    after="<claim no longer extracted>",
                    reason="the approved claim disappeared from the installed skill text",
                )
            )
            continue
        unmatched_old.discard(claim_id)
        unmatched_new.discard(new.claim_id)
        if old.quote != new.quote or old.content_hash != new.content_hash:
            add(
                DriftFinding(
                    claim_id=claim_id,
                    skill_file=new.skill_file,
                    line=new.line,
                    before=old.quote,
                    after=new.quote,
                    reason="the quoted source span changed without a claims update",
                )
            )
        if old.expected_finding_code != new.expected_finding_code or old.direction != new.direction:
            add(
                DriftFinding(
                    claim_id=claim_id,
                    skill_file=new.skill_file,
                    line=new.line,
                    before=f"code={old.expected_finding_code}, direction={old.direction}",
                    after=f"code={new.expected_finding_code}, direction={new.direction}",
                    reason="the interpretation of an approved source span changed",
                )
            )

    for claim_id, new in current_by_id.items():
        if claim_id in unmatched_new:
            add(
                DriftFinding(
                    claim_id=claim_id,
                    skill_file=new.skill_file,
                    line=new.line,
                    before="<claim absent from approved list>",
                    after=new.quote,
                    reason="a new claim was extracted and requires explicit review",
                )
            )

    old_files = existing.baseline.skill_files
    current_files = current.baseline.skill_files
    advisories: list[DriftFinding] = []
    for filename in sorted(set(old_files) ^ set(current_files)):
        advisories.append(
            DriftFinding(
                claim_id=f"baseline:{filename}",
                skill_file=filename,
                line=1,
                before="<file present>" if filename in old_files else "<file absent>",
                after="<file present>" if filename in current_files else "<file absent>",
                reason="source skill file inventory changed; claim spans remain the blocking baseline",
                code="claims/source_file_inventory_changed",
                blocking=False,
            )
        )
    return tuple(findings), tuple(advisories)


def extract_claims(
    skills_root: Path | str,
    *,
    existing: ClaimsDocument | None = None,
    fail_on_drift: bool = True,
) -> ExtractionResult:
    """Extract claims from ``skills_root`` and reject unapproved drift.

    ``existing`` is comparison-only.  This function never writes either the
    claims list or an approval record.
    """

    skills_root_path = Path(skills_root).expanduser().resolve()
    files = source_skill_files(skills_root_path)
    if not files:
        raise FileNotFoundError(f"no installed skill text found under {Path(skills_root).expanduser()}")
    claims = _extract_from_files(files, skills_root_path)
    current = ExtractionResult(
        claims=claims,
        baseline=_baseline(files, claims, skills_root_path),
    )
    if existing is None:
        return current
    drift, advisories = _compare(current, existing)
    result = ExtractionResult(current.claims, current.baseline, drift, advisories)
    if drift and fail_on_drift:
        raise ClaimDriftError(drift)
    return result

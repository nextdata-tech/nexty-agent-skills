"""Fail-closed claim-to-finding verdict matrix.

The invariant is that every stage/check state is handled explicitly.  A
``skip`` is blocking, and a state introduced by a future supervisor raises
instead of falling through to a clean verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping, Sequence

from .claims import Claim, ClaimsDocument
from .extract import DriftFinding


KNOWN_STATES = frozenset({"pass", "warn", "fail", "skip"})


class UnknownFindingState(ValueError):
    """Raised when a supervisor report contains a state this gate cannot classify."""


@dataclass(frozen=True)
class VerdictIssue:
    """One blocking or drift result in the aggregate verdict."""

    kind: str
    message: str
    claim_id: str | None = None
    code: str | None = None
    skill_file: str | None = None
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "claim_id": self.claim_id,
            "code": self.code,
            "skill_file": self.skill_file,
            "line": self.line,
        }


@dataclass(frozen=True)
class Verdict:
    """Machine-readable canary gate result."""

    outcome: str
    issues: tuple[VerdictIssue, ...]
    observed_codes: tuple[str, ...]
    advisories: tuple[VerdictIssue, ...] = ()

    @property
    def blocking(self) -> bool:
        return self.outcome != "clean"

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "blocking": self.blocking,
            "observed_codes": list(self.observed_codes),
            "issues": [issue.to_dict() for issue in self.issues],
            "advisories": [issue.to_dict() for issue in self.advisories],
        }


def _claim_sequence(value: ClaimsDocument | Iterable[Claim]) -> tuple[Claim, ...]:
    if isinstance(value, ClaimsDocument):
        return value.claims
    return tuple(value)


def _checks(report: Mapping[str, Any]) -> tuple[tuple[str, str, str], ...]:
    stages = report.get("stages")
    if not isinstance(stages, Sequence) or isinstance(stages, (str, bytes)):
        raise UnknownFindingState("report has no stages array")
    rows: list[tuple[str, str, str]] = []
    for stage in stages:
        if not isinstance(stage, Mapping):
            raise UnknownFindingState(f"report contains non-object stage {stage!r}")
        stage_name = str(stage.get("stage", ""))
        stage_status = stage.get("status")
        if stage_status not in KNOWN_STATES:
            raise UnknownFindingState(f"unrecognized stage state {stage_status!r} in {stage_name!r}")
        checks = stage.get("checks")
        if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes)):
            raise UnknownFindingState(f"stage {stage_name!r} has no checks array")
        for check in checks:
            if not isinstance(check, Mapping):
                raise UnknownFindingState(f"stage {stage_name!r} contains non-object check {check!r}")
            status = check.get("status")
            if status not in KNOWN_STATES:
                raise UnknownFindingState(
                    f"unrecognized check state {status!r} for code {check.get('code')!r}"
                )
            code = check.get("code")
            if not isinstance(code, str) or not code:
                raise UnknownFindingState(f"stage {stage_name!r} contains a check without a code")
            rows.append((stage_name, str(status), code))
        if stage_status == "skip":
            rows.append((stage_name, "skip", f"{stage_name}/stage_skipped"))
        elif stage_status == "fail" and not checks:
            rows.append((stage_name, "fail", f"{stage_name}/stage_failed"))
    return tuple(rows)


def _line_ref(claim: Claim) -> str:
    return f"{claim.skill_file}:{claim.line}"


def _drift_issue(
    claim: Claim,
    code: str,
    *,
    kind: str = "drift",
    prefix: str = "",
) -> VerdictIssue:
    message = f"{claim.claim_id} → {code} → {_line_ref(claim)}"
    if prefix:
        message = f"{prefix}: {message}"
    return VerdictIssue(
        kind=kind,
        message=message,
        claim_id=claim.claim_id,
        code=code,
        skill_file=claim.skill_file,
        line=claim.line,
    )


def _diagnostic_text(diagnostic: Mapping[str, Any] | None) -> str:
    """Flatten the supervisor diagnostic fields used for safe signature matching."""

    if not isinstance(diagnostic, Mapping):
        return ""
    parts: list[str] = []
    for key in ("error", "last_phase", "timeout_phase", "transform_stage"):
        value = diagnostic.get(key)
        if value is not None:
            parts.append(str(value))
    for stream_name in ("stderr", "stdout"):
        stream = diagnostic.get(stream_name)
        if isinstance(stream, Mapping):
            lines = stream.get("lines")
            if isinstance(lines, Sequence) and not isinstance(lines, (str, bytes)):
                parts.extend(str(line) for line in lines)
    return "\n".join(parts)


def _claim_build_signature(claim: Claim) -> str | None:
    if claim.build_signature:
        return claim.build_signature
    if claim.category != "secret":
        return None
    for key in ("api_source", "db_source", "file_source", "csv_source"):
        if key in claim.quote:
            return f"KeyError: '{key}'"
    return None


def build_failure_issues(build: Any, claims: Iterable[Claim]) -> tuple[VerdictIssue, ...]:
    """Map a failed create diagnostic to a claim, or retain a blocking failure."""

    if getattr(build, "returncode", 0) == 0:
        return ()
    diagnostic = getattr(build, "diagnostic", None)
    text = _diagnostic_text(diagnostic)
    tail = ""
    if isinstance(diagnostic, Mapping):
        stderr = diagnostic.get("stderr")
        if isinstance(stderr, Mapping):
            lines = stderr.get("lines")
            if isinstance(lines, Sequence) and not isinstance(lines, (str, bytes)):
                tail = " | ".join(str(line) for line in lines[-8:])
    matches = [
        claim
        for claim in claims
        if (signature := _claim_build_signature(claim))
        and re.search(re.escape(signature), text)
    ]
    if matches:
        prefix = "build diagnostic matched the documented transform failure"
        if tail:
            prefix += f"; stderr tail={tail}"
        return tuple(
            _drift_issue(claim, claim.expected_finding_code, prefix=prefix)
            for claim in matches
        )
    detail = f"build → create failed for closure {getattr(build, 'closure', '<unknown>')}"
    if isinstance(diagnostic, Mapping):
        summary = diagnostic.get("error") or diagnostic.get("last_phase")
        if summary:
            detail += f"; diagnostic={summary}"
    if tail:
        detail += f"; stderr tail={tail}"
    return (
        VerdictIssue(
            kind="blocked",
            message=detail,
            code="build/create_failed",
        ),
    )


def aggregate_verdict(
    report: Mapping[str, Any],
    claims: ClaimsDocument | Iterable[Claim],
    *,
    probe_id: str | None = None,
    extraction_drift: Iterable[DriftFinding] = (),
    extraction_advisories: Iterable[DriftFinding] = (),
) -> Verdict:
    """Aggregate a supervisor report against the approved claim matrix."""

    rows = _checks(report)
    all_claims = _claim_sequence(claims)
    report_probe_id = report.get("probe_id")
    effective_probe_id = probe_id or (str(report_probe_id) if report_probe_id else None)
    if effective_probe_id is None:
        probe_ids = {claim.probe_id for claim in all_claims}
        if len(probe_ids) == 1:
            effective_probe_id = next(iter(probe_ids))
        else:
            raise UnknownFindingState("verdict requires an explicit probe_id for a multi-probe claims list")
    claim_values = tuple(claim for claim in all_claims if claim.probe_id == effective_probe_id)
    if not claim_values:
        raise UnknownFindingState(f"no approved claims are bound to probe_id {effective_probe_id!r}")
    for claim in claim_values:
        if claim.direction not in {"documented-supported", "documented-unsupported"}:
            raise UnknownFindingState(f"unrecognized claim direction {claim.direction!r} for {claim.claim_id}")

    issues: list[VerdictIssue] = []
    for drift in extraction_drift:
        issues.append(
            VerdictIssue(
                kind="drift",
                message=(
                    f"{drift.claim_id} → {drift.code} → {drift.skill_file}:{drift.line}; "
                    f"before={drift.before!r}; after={drift.after!r}"
                ),
                claim_id=drift.claim_id,
                code=drift.code,
                skill_file=drift.skill_file,
                line=drift.line,
            )
        )
    advisories = [
        VerdictIssue(
            kind="advisory",
            message=(
                f"{finding.claim_id} → {finding.code} → {finding.skill_file}:{finding.line}; "
                f"{finding.reason}"
            ),
            claim_id=finding.claim_id,
            code=finding.code,
            skill_file=finding.skill_file,
            line=finding.line,
        )
        for finding in extraction_advisories
    ]

    active = [(stage, status, code) for stage, status, code in rows if status != "pass"]
    observed_codes = tuple(sorted({code for _, _, code in rows}))
    expected_codes = {claim.expected_finding_code for claim in claim_values}
    supported_expected_codes = {
        claim.expected_finding_code
        for claim in claim_values
        if claim.direction == "documented-supported"
    }
    claims_by_code: dict[str, list[Claim]] = {}
    for claim in claim_values:
        claims_by_code.setdefault(claim.expected_finding_code, []).append(claim)
    is_single_construct_negative_probe = effective_probe_id.startswith("unsupported-") and all(
        claim.direction == "documented-unsupported" for claim in claim_values
    )
    negative_expected_observed = is_single_construct_negative_probe and any(
        status == "fail"
        and code in expected_codes
        and any(claim.direction == "documented-unsupported" for claim in claims_by_code.get(code, ()))
        for _, status, code in rows
    )

    stage_statuses = [status for _, status, _ in rows]
    expected_outcome = (
        "fail"
        if any(status == "fail" for status in stage_statuses)
        else "warn"
        if any(status == "warn" for status in stage_statuses)
        else "pass"
    )
    report_outcome = report.get("outcome")
    if report_outcome in KNOWN_STATES and report_outcome != expected_outcome:
        issues.append(
            VerdictIssue(
                kind="blocked",
                message=(
                    f"report outcome {report_outcome!r} disagrees with stage outcome "
                    f"{expected_outcome!r}"
                ),
            )
        )

    # A skipped check is always blocking, including one whose prose sounds benign.
    for stage, status, code in active:
        if status == "skip":
            issues.append(
                VerdictIssue(
                    kind="blocked",
                    message=f"{stage} → {code} → skipped stage/check is unexamined and blocks the canary",
                    code=code,
                )
            )
            continue
        if status == "warn" and code not in expected_codes:
            advisories.append(
                VerdictIssue(
                    kind="advisory",
                    message=f"{stage} → {code} → unclaimed warning is advisory only",
                    code=code,
                )
            )

    # A documented unsupported construct must continue to produce its known
    # finding.  It is the one deliberate expected negative in the matrix.
    for claim in claim_values:
        if claim.direction != "documented-unsupported":
            continue
        matching = [
            code
            for _, status, code in active
            if code == claim.expected_finding_code and status != "skip" and status != "warn"
        ]
        if not matching:
            issues.append(
                _drift_issue(
                    claim,
                    claim.expected_finding_code,
                    kind="reverse-drift",
                    prefix="documented-unsupported construct drew no finding",
                )
            )

    # Any non-pass failure with an exact supported mapping is a precise
    # runtime/documentation disagreement.  Unknown failures are blocking; a
    # warning without an exact claim mapping is only an advisory.  There is no
    # stage-wide fallback because it cannot identify which construct was tested.
    for stage, status, code in active:
        if status in {"skip", "warn"}:
            continue
        matching = claims_by_code.get(code, ())
        if matching:
            supported_matching = [
                claim for claim in matching if claim.direction == "documented-supported"
            ]
            for claim in supported_matching:
                issues.append(_drift_issue(claim, code))
            if supported_matching:
                continue
            if is_single_construct_negative_probe:
                continue
        issues.append(
            VerdictIssue(
                kind="blocked",
                message=f"{stage} → {code} → no approved interpretation exists for this probe",
                code=code,
            )
        )

    # A failed stage with no explicit check is not safe to interpret as clean.
    for stage, status, code in rows:
        if status == "fail" and code not in supported_expected_codes:
            if negative_expected_observed and code in expected_codes:
                continue
            issues.append(
                VerdictIssue(
                    kind="blocked",
                    message=f"{stage} → {code} → failing stage has no approved interpretation",
                    code=code,
                )
            )

    # De-duplicate issues created by a check matching both the code and stage
    # paths while preserving deterministic order.
    unique: list[VerdictIssue] = []
    seen: set[tuple[str, str, str | None]] = set()
    for issue in issues:
        key = (issue.kind, issue.message, issue.code)
        if key not in seen:
            seen.add(key)
            unique.append(issue)

    if any(issue.kind == "blocked" for issue in unique):
        outcome = "blocked"
    elif unique:
        outcome = "drift"
    else:
        outcome = "clean"
    return Verdict(
        outcome=outcome,
        issues=tuple(unique),
        observed_codes=observed_codes,
        advisories=tuple(advisories),
    )

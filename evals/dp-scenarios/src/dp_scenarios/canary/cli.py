"""Tier-facing read-only canary command.

The invariant is structural: this module can load, extract, probe, build, and
report, but it has no claims-list write or regeneration branch.  Human
approval belongs exclusively to ``python -m dp_scenarios.canary.rebaseline``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping

from .claims import ClaimsIntegrityError, load_claims
from .extract import ClaimDriftError, extract_claims
from .probe import ProbeError, run_probe_and_build
from .verdict import VerdictIssue, aggregate_verdict, build_failure_issues


def _default_closure() -> Path:
    return Path(__file__).resolve().parents[3] / "scenarios" / "drift-canary"


def _default_claims() -> Path:
    return _default_closure() / "claims.json"


def _probe_specs(closure: Path, requested_probe: str | None) -> tuple[dict[str, Any], ...]:
    manifest = closure / "probes.json"
    if not manifest.is_file():
        return ({"probe_id": requested_probe or "kitchen-sink", "closure": ".", "build": True},)
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeError(f"probe manifest {manifest} is not valid JSON: {exc}") from exc
    raw_probes = value.get("probes") if isinstance(value, Mapping) else None
    if not isinstance(raw_probes, list) or not raw_probes:
        raise ProbeError(f"probe manifest {manifest} must contain a non-empty probes array")
    probes: list[dict[str, Any]] = []
    for raw in raw_probes:
        if not isinstance(raw, Mapping) or not raw.get("probe_id") or not raw.get("closure"):
            raise ProbeError(f"probe manifest {manifest} contains an invalid probe entry")
        if requested_probe is None or raw["probe_id"] == requested_probe:
            probes.append(dict(raw))
    if requested_probe is not None and not probes:
        raise ProbeError(f"probe manifest {manifest} has no probe_id {requested_probe!r}")
    return tuple(probes)


def _report_passes(report: Mapping[str, Any]) -> bool:
    """Require the negative-control closure to be entirely examined and clean."""

    if report.get("outcome") != "pass":
        return False
    for stage in report.get("stages", ()):
        if not isinstance(stage, Mapping) or stage.get("status") != "pass":
            return False
        checks = stage.get("checks", ())
        if any(not isinstance(check, Mapping) or check.get("status") != "pass" for check in checks):
            return False
    return True


def _run_negative_control(
    closure: Path,
    spec: Mapping[str, Any],
    *,
    supervisor: Path | str | None,
    workflow: str,
) -> Any:
    """Run one check after removing exactly the planted unsupported construct."""

    control = spec.get("negative_control")
    if not isinstance(control, Mapping):
        return None
    marker = control.get("remove")
    if not isinstance(marker, str) or not marker:
        raise ProbeError(f"negative control for {spec.get('probe_id')!r} has no removal marker")
    with tempfile.TemporaryDirectory(prefix=f".{closure.name}-negative-control-", dir=closure.parent) as name:
        control_closure = Path(name) / closure.name
        shutil.copytree(closure, control_closure)
        spec_file = control_closure / "spec.py"
        try:
            lines = spec_file.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError as exc:
            raise ProbeError(f"negative control cannot read {spec_file}: {exc}") from exc
        matches = [line for line in lines if marker in line]
        if len(matches) != 1:
            raise ProbeError(
                f"negative control for {spec.get('probe_id')!r} expected one planted line "
                f"containing {marker!r}, found {len(matches)}"
            )
        spec_file.write_text("".join(line for line in lines if marker not in line), encoding="utf-8")
        result, _ = run_probe_and_build(
            control_closure,
            supervisor=supervisor,
            workflow=workflow,
            build=False,
        )
        return result


def _stronger_outcome(current: str, candidate: str) -> str:
    rank = {"clean": 0, "drift": 1, "blocked": 2}
    return candidate if rank.get(candidate, 2) > rank.get(current, 2) else current


def check_claims(
    closure: Path | str,
    claims_path: Path | str,
    *,
    skills_root: Path | str,
    supervisor: Path | str | None = None,
    data_dir: Path | str | None = None,
    workflow: str = "drift-canary",
    build: bool = True,
    probe_id: str | None = None,
) -> dict[str, Any]:
    """Run the read-only claims check, probe, verdict, and optional build."""

    # Loading with verification is deliberately before extraction and before
    # any process invocation.  A stale approval must fail without repairing
    # itself or touching the claims file.
    document = load_claims(claims_path, verify=True)
    extracted = extract_claims(skills_root, existing=document, fail_on_drift=False)
    if extracted.drift:
        raise ClaimDriftError(extracted.drift)
    closure_path = Path(closure).expanduser().resolve()
    probe_results: list[dict[str, Any]] = []
    build_results: list[dict[str, Any]] = []
    all_issues: list[VerdictIssue] = []
    all_advisories: list[VerdictIssue] = []
    observed_codes: set[str] = set()
    probe_outcomes: list[str] = []
    if not build:
        all_issues.append(
            VerdictIssue(
                kind="blocked",
                message="tier canary build was disabled; use this only as a non-passing diagnostic",
                code="build/skipped",
            )
        )
    for spec in _probe_specs(closure_path, probe_id):
        current_probe_id = str(spec["probe_id"])
        current_closure = (closure_path / str(spec["closure"])).resolve()
        should_build = build and bool(spec.get("build", True))
        preflight, built = run_probe_and_build(
            current_closure,
            supervisor=supervisor,
            data_dir=data_dir,
            workflow=workflow,
            build=should_build,
        )
        report = getattr(preflight, "report", None)
        if not isinstance(report, Mapping):
            report = preflight.to_dict().get("report", {})
        report = dict(report)
        report.setdefault("probe_id", current_probe_id)
        probe_entry = preflight.to_dict()
        if built is not None:
            build_results.append(built.to_dict())
        probe_verdict = aggregate_verdict(
            report,
            document,
            probe_id=current_probe_id,
            extraction_drift=extracted.drift,
            extraction_advisories=extracted.advisories,
        )
        all_issues.extend(probe_verdict.issues)
        all_advisories.extend(probe_verdict.advisories)
        observed_codes.update(probe_verdict.observed_codes)
        probe_outcome = probe_verdict.outcome
        stage_statuses = [
            stage.get("status")
            for stage in report.get("stages", [])
            if isinstance(stage, Mapping)
        ]
        stage_statuses.extend(
            check.get("status")
            for stage in report.get("stages", [])
            if isinstance(stage, Mapping)
            for check in stage.get("checks", [])
            if isinstance(check, Mapping)
        )
        report_requires_failure = any(status in {"fail", "skip"} for status in stage_statuses)
        if (getattr(preflight, "returncode", 0) != 0) != report_requires_failure:
            issue = VerdictIssue(
                kind="blocked",
                message=(
                    f"{current_probe_id} → supervisor exit/report disagreement: "
                    f"returncode={getattr(preflight, 'returncode', 0)}, "
                    f"report_requires_failure={report_requires_failure}"
                ),
                code="probe/exit_report_disagreement",
            )
            all_issues.append(issue)
            probe_outcome = _stronger_outcome(probe_outcome, "blocked")
        if built is not None and built.returncode != 0:
            build_issues = build_failure_issues(
                built,
                (claim for claim in document.claims if claim.probe_id == current_probe_id),
            )
            all_issues.extend(build_issues)
            for issue in build_issues:
                if issue.code:
                    observed_codes.add(issue.code)
                probe_outcome = _stronger_outcome(
                    probe_outcome,
                    "drift" if issue.kind in {"drift", "reverse-drift"} else "blocked",
                )
        if spec.get("negative_control") is not None:
            control_result = _run_negative_control(
                current_closure,
                spec,
                supervisor=supervisor,
                workflow=workflow,
            )
            if control_result is not None:
                control_report = dict(control_result.report)
                control_report.setdefault("probe_id", current_probe_id)
                probe_entry["negative_control"] = control_result.to_dict()
                if not _report_passes(control_report):
                    issue = VerdictIssue(
                        kind="blocked",
                        message=(
                            f"{current_probe_id} → negative control failed: the closure without "
                            "the planted construct was not an all-pass check"
                        ),
                        code="probe/negative_control_failed",
                    )
                    all_issues.append(issue)
                    probe_outcome = _stronger_outcome(probe_outcome, "blocked")
        probe_results.append(probe_entry)
        probe_outcomes.append(probe_outcome)
    unique_issues: list[VerdictIssue] = []
    seen_issues: set[tuple[str, str, str | None]] = set()
    for issue in all_issues:
        key = (issue.kind, issue.message, issue.code)
        if key not in seen_issues:
            seen_issues.add(key)
            unique_issues.append(issue)
    outcome = "clean"
    for probe_outcome in probe_outcomes:
        outcome = _stronger_outcome(outcome, probe_outcome)
    if not build:
        outcome = _stronger_outcome(outcome, "blocked")
    verdict = {
        "outcome": outcome,
        "blocking": outcome != "clean",
        "observed_codes": sorted(observed_codes),
        "issues": [issue.to_dict() for issue in unique_issues],
        "advisories": [issue.to_dict() for issue in all_advisories],
    }
    return {
        "claims_hash": document.verify_approval_hash(),
        "probe": probe_results[0] if len(probe_results) == 1 else probe_results,
        "build": (
            build_results[0]
            if len(build_results) == 1
            else build_results
            if build_results
            else None
        ),
        "verdict": verdict,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the skill-vs-runtime drift canary")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="check claims and run the supervisor canary")
    check.add_argument("--closure", type=Path, default=_default_closure())
    check.add_argument("--claims", type=Path, default=_default_claims())
    check.add_argument(
        "--skills-root",
        type=Path,
        required=True,
        help="skill pack installed in the isolated environment under test",
    )
    check.add_argument("--supervisor", type=Path)
    check.add_argument("--data-dir", type=Path)
    check.add_argument("--workflow", default="drift-canary")
    check.add_argument("--probe-id")
    check.add_argument(
        "--no-build",
        action="store_true",
        help="run only the preflight; this is for local diagnostics, not the tier gate",
    )

    extract = subparsers.add_parser("extract", help="extract claims without writing them")
    extract.add_argument(
        "--skills-root",
        type=Path,
        required=True,
        help="skill pack installed in the isolated environment under test",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the read-only canary CLI."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "extract":
            result = extract_claims(args.skills_root)
            print(
                json.dumps(
                    {
                        "claims": [claim.to_dict() for claim in result.claims],
                        "skill_files": result.baseline.skill_files,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        result = check_claims(
            args.closure,
            args.claims,
            skills_root=args.skills_root,
            supervisor=args.supervisor,
            data_dir=args.data_dir,
            workflow=args.workflow,
            build=not args.no_build,
            probe_id=args.probe_id,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["verdict"]["outcome"] == "clean" else 1
    except ClaimDriftError as exc:
        print(
            json.dumps(
                {
                    "outcome": "drift",
                    "drift": [finding.to_dict() for finding in exc.findings],
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    except (ClaimsIntegrityError, ProbeError, OSError, ValueError) as exc:
        error = {"outcome": "blocked", "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line entry point for the canary-gated tier runner.

The invariant enforced here is explicit replay/live construction: replay input
supplies a recorded canary result and structured session records, and a missing
probe never silently becomes a clean tier.  This keeps command-line runs
comparable to programmatic runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Any, Mapping, Sequence

from dp_scenarios.canary import load_claims
from dp_scenarios.canary.verdict import Verdict, VerdictIssue
from dp_scenarios.scenario import load_scenarios

from .environment import PinnedVersions
from .report import write_report
from .session import LiveSession, ReplayRecording
from .tier import CanaryResult, RunBudgets, TierError, TierRunner, run_drift_canary


def _canary_from_mapping(
    value: Mapping[str, object],
    *,
    expected_claims_hash: str,
) -> CanaryResult:
    claims_hash = value.get("claims_hash")
    if not isinstance(claims_hash, str) or not claims_hash.strip():
        raise TierError("replayed canary must carry a non-empty claims_hash")
    if claims_hash != expected_claims_hash:
        raise TierError("replayed canary claims_hash does not match the loaded claims file")
    raw = value.get("verdict", value)
    if not isinstance(raw, Mapping):
        raise TierError("replayed canary has no verdict object")
    issues: list[VerdictIssue] = []
    for item in raw.get("issues", ()):
        if not isinstance(item, Mapping):
            raise TierError("replayed canary issue is not an object")
        issues.append(
            VerdictIssue(
                kind=str(item.get("kind", "blocked")),
                message=str(item.get("message", "")),
                claim_id=item.get("claim_id") if isinstance(item.get("claim_id"), str) else None,
                code=item.get("code") if isinstance(item.get("code"), str) else None,
                skill_file=item.get("skill_file") if isinstance(item.get("skill_file"), str) else None,
                line=item.get("line") if isinstance(item.get("line"), int) else None,
            )
        )
    verdict = Verdict(
        outcome=str(raw.get("outcome", "blocked")),
        issues=tuple(issues),
        observed_codes=tuple(str(code) for code in raw.get("observed_codes", ()) if isinstance(code, str)),
        advisories=(),
    )
    return CanaryResult(
        verdict,
        claims_hash,
        value.get("probe") if isinstance(value.get("probe"), Mapping) else None,
        value.get("build") if isinstance(value.get("build"), Mapping) else None,
        float(value.get("wall_clock_seconds", 0.0)),
    )


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TierError(f"could not read JSON input {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise TierError(f"JSON input {path} must be an object")
    return value


def _load_replays(path: Path, scenario_ids: Sequence[str]) -> dict[str, object]:
    if path.is_dir():
        result: dict[str, ReplayRecording] = {}
        for scenario_id in scenario_ids:
            candidate = path / f"{scenario_id}.json"
            if not candidate.is_file():
                raise TierError(f"replay directory has no recording for {scenario_id}: {candidate}")
            result[scenario_id] = ReplayRecording.read(candidate)
        return result
    raw = _read_json(path)
    nested = raw.get("scenarios", raw)
    if not isinstance(nested, Mapping):
        raise TierError("replay input must map scenario ids to recordings")
    result: dict[str, object] = {}
    for scenario_id in scenario_ids:
        value = nested.get(scenario_id)
        if isinstance(value, Mapping):
            result[scenario_id] = ReplayRecording.from_dict(value)
        elif isinstance(value, str):
            result[scenario_id] = ReplayRecording.read(path.parent / value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            recordings: list[ReplayRecording] = []
            for item in value:
                if isinstance(item, Mapping):
                    recordings.append(ReplayRecording.from_dict(item))
                elif isinstance(item, str):
                    recordings.append(ReplayRecording.read(path.parent / item))
                else:
                    raise TierError(f"replay input has an invalid recording for {scenario_id}")
            if not recordings:
                raise TierError(f"replay input has an empty recording list for {scenario_id}")
            result[scenario_id] = recordings
        else:
            raise TierError(f"replay input has no recording for {scenario_id}")
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the runner CLI parser."""

    parser = argparse.ArgumentParser(description="Run the canary-gated dp-scenarios tier")
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--canary-dir", type=Path, required=True)
    parser.add_argument("--canary-replay", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--session-command", help="JSONL headless session command for live mode")
    parser.add_argument("--supervisor", type=Path)
    parser.add_argument("--skill-pack-version", required=True)
    parser.add_argument("--supervisor-version", required=True)
    parser.add_argument("--runtime-wheel-version", required=True)
    parser.add_argument("--mock-api-version", required=True)
    parser.add_argument("--canary-claims-hash", required=True)
    parser.add_argument("--agent-model-id", default="replay")
    parser.add_argument("--model-call-budget", type=float)
    parser.add_argument("--wall-clock-budget", type=float)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--report-summary", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected tier and write both report surfaces."""

    args = build_parser().parse_args(argv)
    scenarios = load_scenarios(args.scenario_root)
    pins = PinnedVersions(
        skill_pack_version=args.skill_pack_version,
        supervisor_version=args.supervisor_version,
        runtime_wheel_version=args.runtime_wheel_version,
        mock_api_version=args.mock_api_version,
        canary_claims_hash=args.canary_claims_hash,
        agent_model_id=args.agent_model_id,
    )
    if args.canary_replay is not None:
        expected_claims_hash = load_claims(args.canary_dir / "claims.json").baseline.approves_claims_hash
        canary = _canary_from_mapping(
            _read_json(args.canary_replay),
            expected_claims_hash=expected_claims_hash,
        )
    else:
        canary = lambda: run_drift_canary(args.canary_dir, supervisor=args.supervisor)

    replays: dict[str, ReplayRecording] = {}
    session_factory = None
    if args.mode == "replay":
        if args.replay is None:
            raise TierError("replay mode requires --replay")
        replays = _load_replays(args.replay, [scenario.id for scenario in scenarios])
    else:
        if not args.session_command:
            raise TierError("live mode requires --session-command")
        command = tuple(shlex.split(args.session_command))

        def factory(scenario: object, environment: object, epoch: int) -> LiveSession:
            return LiveSession(command, environment=environment.agent_environment, cwd=environment.base_dir)

        session_factory = factory
    result = TierRunner(
        scenarios,
        pins=pins,
        canary=canary,
        session_factory=session_factory,
        replay_recordings=replays,
        budgets=RunBudgets(args.model_call_budget, args.wall_clock_budget),
    ).run()
    write_report(result, json_path=args.report_json, summary_path=args.report_summary)
    return 0 if result.verdict == "clean" else 1


if __name__ == "__main__":  # pragma: no cover - exercised through the console entry point
    raise SystemExit(main())


__all__ = ["build_parser", "main"]

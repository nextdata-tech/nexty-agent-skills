"""Command-line entry point for the canary-gated tier runner.

The invariant enforced here is explicit replay/live construction: replay input
supplies a recorded canary result and structured session records, and a missing
probe never silently becomes a clean tier.  This keeps command-line runs
comparable to programmatic runs.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import replace
import json
from pathlib import Path
import shlex
from typing import Mapping, Sequence

from dp_scenarios.canary import load_claims
from dp_scenarios.knobs import KnobError, SupervisorKnobs, load_knob_plan
from dp_scenarios.scenario import (
    SCENARIO_TIERS,
    load_scenarios,
    requires_live_session,
    select_tier,
)

from dp_scenarios.operator.driver import DriverOperator
from dp_scenarios.operator.openai_driver import OpenAIDriverProvider, driver_prompt_hash

from .environment import PinnedVersions
from .report import write_report
from .session import LiveSession, ReplayRecording
from .tier import CanaryResult, RunBudgets, TierError, TierRunner, run_drift_canary


def _canary_from_mapping(
    value: Mapping[str, object],
    *,
    canary_dir: Path,
    skills_root: Path,
    expected_claims_hash: str,
) -> CanaryResult:
    claims_hash = value.get("claims_hash")
    if not isinstance(claims_hash, str) or not claims_hash.strip():
        raise TierError("replayed canary must carry a non-empty claims_hash")
    if claims_hash != expected_claims_hash:
        raise TierError("replayed canary claims_hash does not match the loaded claims file")
    probe = value.get("probe")
    if not isinstance(probe, Mapping) or not isinstance(probe.get("report"), Mapping):
        raise TierError("replayed canary requires a probe object containing a report")
    build = value.get("build")
    if not isinstance(build, Mapping) and build is not None:
        raise TierError("replayed canary build must be an object")
    if isinstance(build, Mapping) and "returncode" not in build:
        raise TierError("replayed canary build has no mandatory returncode")
    return run_drift_canary(
        canary_dir,
        skills_root=skills_root,
        probe=probe,
        build=build,
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


def _load_cli_knob_plan(path: Path) -> Mapping[tuple[str, int], SupervisorKnobs]:
    """Load CLI controls while refusing an unverifiable workflow switch."""

    try:
        knob_plan = load_knob_plan(path)
    except KnobError as exc:
        raise TierError(str(exc)) from exc
    if any(value.workflow_switch is not None for value in knob_plan.values()):
        raise TierError(
            "CLI knob plans cannot execute workflow switches; use TierRunner with "
            "workflow_restart_factory and workflow_observer callbacks"
        )
    return knob_plan


def _driver_configuration(
    args: argparse.Namespace,
    pins: PinnedVersions,
) -> tuple[PinnedVersions, Callable[..., DriverOperator] | None]:
    """Return the pins and operator factory implied by the driver flags.

    Kept identical in shape to the local entrypoint's ``driver_configuration``
    so the same flags mean the same thing on both surfaces; the key is read
    only from ``OPENAI_API_KEY`` and the provider is built before the canary.
    """

    model = getattr(args, "driver_model", None)
    if model is None:
        return pins, None
    if args.mode != "live":
        # Replaying a recording re-authors nothing; a driver here would spend
        # provider tokens producing words the recording then overrides.
        raise TierError("--driver-model requires --mode live")
    temperature = float(getattr(args, "driver_temperature", 1.0))
    timeout = float(getattr(args, "driver_timeout", 60.0))
    max_tokens = getattr(args, "driver_max_tokens", 400)
    if not 0 <= temperature <= 2:
        raise TierError("--driver-temperature must be between 0 and 2")
    if timeout <= 0:
        raise TierError("--driver-timeout must be positive")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
        raise TierError("--driver-max-tokens must be a positive integer")
    provider = OpenAIDriverProvider.from_environment(
        model=model,
        temperature=temperature,
        timeout_seconds=timeout,
        max_tokens=max_tokens,
    )
    driver_pins = replace(
        pins,
        driver_model_id=model,
        driver_sampling_params={
            "temperature": temperature,
            # The cap decides whether a turn produces text at all --
            # on GPT-5-class models it spans reasoning tokens -- so two
            # runs that differ by it are two different operators and
            # must not pair, exactly like the prompt hash.
            "max_tokens": max_tokens,
            "prompt_hash": driver_prompt_hash(),
        },
    )

    def factory(scenario: object, environment: object, epoch: int) -> DriverOperator:
        return DriverOperator(
            provider,
            model_id=model,
            temperature=temperature,
            provider_timeout_seconds=timeout,
        )

    return driver_pins, factory


def build_parser() -> argparse.ArgumentParser:
    """Build the runner CLI parser."""

    parser = argparse.ArgumentParser(description="Run the canary-gated dp-scenarios tier")
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument(
        "--tier",
        required=True,
        choices=sorted(SCENARIO_TIERS),
        help="Tier to run; only scenarios declaring it are selected from --scenario-root",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="maximum number of scenario packages to execute concurrently (epochs stay serial)",
    )
    parser.add_argument("--canary-dir", type=Path, required=True)
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--canary-replay", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--session-command", help="JSONL headless session command for live mode")
    parser.add_argument("--supervisor", type=Path)
    parser.add_argument("--skill-pack-version", required=True)
    parser.add_argument("--supervisor-version", required=True)
    parser.add_argument("--runtime-wheel-version", required=True)
    parser.add_argument("--mock-api-version", required=True)
    parser.add_argument("--canary-claims-hash", required=True)
    parser.add_argument(
        "--knob-plan",
        type=Path,
        help="JSON runtime-knob plan keyed by scenario id and one-based epoch",
    )
    parser.add_argument("--agent-model-id", default="replay")
    parser.add_argument(
        "--driver-model",
        default=None,
        help=(
            "OpenAI model id that authors each substitutable operator turn "
            "(default: none, the operator stays scripted). Requires OPENAI_API_KEY "
            "in the environment and driver_forbidden_terms in the answer sheet"
        ),
    )
    parser.add_argument("--driver-temperature", type=float, default=1.0, help="sampling temperature for --driver-model")
    parser.add_argument("--driver-timeout", type=float, default=60.0, help="seconds allowed for one driver provider call")
    parser.add_argument(
        "--driver-max-tokens",
        type=int,
        default=400,
        help="maximum completion tokens per provider call, including reasoning tokens",
    )
    parser.add_argument("--model-call-budget", type=float)
    parser.add_argument("--wall-clock-budget", type=float)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--report-summary", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected tier and write both report surfaces."""

    args = build_parser().parse_args(argv)
    if args.jobs < 1:
        raise TierError("--jobs must be a positive integer")
    if requires_live_session(args.tier) and args.mode != "live":
        # A live-tier scenario grades what an agent did across turns. Replaying
        # a stored session would grade the recording instead and report it as a
        # clean run, which is worse than refusing: the report would look
        # indistinguishable from a real one.
        raise TierError(
            f"tier {args.tier!r} requires --mode live; replaying it would grade the "
            "recording rather than an agent"
        )
    scenarios = select_tier(load_scenarios(args.scenario_root), args.tier)
    pins = PinnedVersions(
        skill_pack_version=args.skill_pack_version,
        supervisor_version=args.supervisor_version,
        runtime_wheel_version=args.runtime_wheel_version,
        mock_api_version=args.mock_api_version,
        canary_claims_hash=args.canary_claims_hash,
        agent_model_id=args.agent_model_id,
    )
    pins, operator_factory = _driver_configuration(args, pins)
    if args.canary_replay is not None:
        expected_claims_hash = load_claims(args.canary_dir / "claims.json").baseline.approves_claims_hash
        canary = _canary_from_mapping(
            _read_json(args.canary_replay),
            canary_dir=args.canary_dir,
            skills_root=args.skills_root,
            expected_claims_hash=expected_claims_hash,
        )
    else:

        def canary() -> CanaryResult:
            return run_drift_canary(
                args.canary_dir,
                skills_root=args.skills_root,
                supervisor=args.supervisor,
            )

    replays: dict[str, ReplayRecording] = {}
    session_factory = None
    if args.mode == "replay":
        if args.replay is None:
            raise TierError("replay mode requires --replay")
        replays = _load_replays(args.replay, [scenario.id for scenario in scenarios])
    else:
        if not args.session_command:
            raise TierError("live mode requires --session-command")
        if args.supervisor is None:
            raise TierError("live mode requires --supervisor")
        command = tuple(shlex.split(args.session_command))

        def factory(scenario: object, environment: object, epoch: int) -> LiveSession:
            return environment.live_session()  # type: ignore[attr-defined, no-any-return]

        session_factory = factory
    knob_plan = None
    if args.knob_plan is not None:
        knob_plan = _load_cli_knob_plan(args.knob_plan)
    result = TierRunner(
        scenarios,
        pins=pins,
        canary=canary,
        session_factory=session_factory,
        replay_recordings=replays,
        live_command=command if args.mode == "live" else None,
        supervisor_command=args.supervisor if args.mode == "live" else None,
        knob_plan=knob_plan,
        budgets=RunBudgets(args.model_call_budget, args.wall_clock_budget),
        operator_factory=operator_factory,
        max_workers=args.jobs,
    ).run()
    write_report(result, json_path=args.report_json, summary_path=args.report_summary)
    return 0 if result.verdict == "clean" else 1


if __name__ == "__main__":  # pragma: no cover - exercised through the console entry point
    raise SystemExit(main())


__all__ = ["build_parser", "main"]

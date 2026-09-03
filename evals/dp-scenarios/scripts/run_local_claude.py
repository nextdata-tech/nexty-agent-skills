#!/usr/bin/env python3
"""Run the dp-scenarios qualification tier with local Claude Code.

This is intentionally a developer entrypoint, not a hosted CI workflow. It
uses a fresh scenario home and private Desktop MCP server for each epoch, then
hands the structured observations to the existing canary-gated grader.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from dp_scenarios.canary import load_claims
from dp_scenarios.canary.probe import resolve_supervisor
from dp_scenarios.grading.statistics import RepeatabilityTier
from dp_scenarios.runner.environment import PinnedVersions
from dp_scenarios.runner.local import FileSupervisorRecordReader, temporary_plugin
from dp_scenarios.runner.report import write_report
from dp_scenarios.runner.session import LiveSession
from dp_scenarios.runner.tier import RunBudgets, TierError, TierRunner, run_drift_canary
from dp_scenarios.scenario import Scenario, load_scenarios, select_tier


REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_ROOT = REPO_ROOT / "evals" / "dp-scenarios" / "scenarios"
CANARY_ROOT = SCENARIO_ROOT / "drift-canary"
ADAPTER_MODULE = "dp_scenarios.runner.claude_adapter"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_pin(desktop_python: Path) -> str:
    """Identify the exact local interpreter used by the desktop supervisor."""

    try:
        completed = subprocess.run(
            [str(desktop_python), "-c", "import sys; print(sys.version.split()[0])"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise TierError(f"could not inspect desktop Python {desktop_python}: {exc}") from exc
    version = completed.stdout.strip() if completed.returncode == 0 else "unknown"
    return f"python-{version}:sha256:{_sha256(desktop_python)}"


def _resolve_executable(explicit: Path | None, name: str) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser()
    else:
        discovered = shutil.which(name)
        if discovered is None:
            raise TierError(f"{name} was not found on PATH; pass an explicit executable path")
        candidate = Path(discovered)
    candidate = candidate.resolve()
    if not candidate.is_file() or not candidate.stat().st_mode & 0o111:
        raise TierError(f"{name} is not an executable file: {candidate}")
    return candidate


def _adapter_timeout(turn_timeout: float) -> float:
    """Leave room for the adapter to retain a structured timeout result."""

    if turn_timeout <= 0:
        raise TierError("turn timeout must be positive")
    return turn_timeout * 0.9


def _agent_environment(
    base: Mapping[str, str],
    *,
    allow_host_home: bool,
) -> dict[str, str]:
    """Build the disposable agent environment, with host-home opt-in explicit."""

    environment = dict(base)
    if allow_host_home:
        host_home = str(Path.home())
        environment.update({"HOME": host_home, "USERPROFILE": host_home})
    return environment


def _default_desktop_python() -> Path:
    return Path.home() / ".nxd" / "desktop-venv" / "bin" / "python"


def _select_scenarios(all_scenarios: Sequence[Scenario], selected: Sequence[str]) -> tuple[Scenario, ...]:
    if not selected:
        return tuple(all_scenarios)
    by_id = {scenario.id: scenario for scenario in all_scenarios}
    unknown = [scenario_id for scenario_id in selected if scenario_id not in by_id]
    if unknown:
        raise TierError("unknown scenario id(s): " + ", ".join(unknown))
    selected_set = set(selected)
    return tuple(scenario for scenario in all_scenarios if scenario.id in selected_set)



def _scenarios_in_scope(
    all_scenarios: Sequence[Scenario],
    selected: Sequence[str],
    tier: str,
) -> tuple[Scenario, ...]:
    """Apply the tier boundary to the default (no ``--scenario``) case.

    The boundary has to hold in both loader call sites. ``runner/cli.py``
    requires ``--tier``; this entrypoint drives a live authenticated Claude
    Code session, so an unbounded default is worse here -- it would spend
    model tokens driving core packages whose evidence a live run cannot
    produce. Naming a scenario id still crosses the tier deliberately.
    """

    if selected:
        return tuple(all_scenarios)
    return select_tier(all_scenarios, tier)


def _configure_scenarios(
    all_scenarios: Sequence[Scenario],
    selected: Sequence[str],
    epochs: int,
) -> tuple[Scenario, ...]:
    """Apply CLI selection and make one-epoch runs explicitly demonstrated-once."""

    if epochs < 1:
        raise TierError("--epochs must be positive")
    return tuple(
        replace(
            scenario,
            repeatability=replace(
                scenario.repeatability,
                epochs=epochs,
                tier=(
                    RepeatabilityTier.DEMONSTRATED_ONCE
                    if epochs == 1
                    else scenario.repeatability.tier
                ),
            ),
        )
        for scenario in _select_scenarios(all_scenarios, selected)
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the local runner CLI parser."""

    parser = argparse.ArgumentParser(description="Run local Claude Code DP-scenarios")
    parser.add_argument("--scenario", action="append", default=[], help="scenario id; repeat to select several (default: every scenario in --tier)")
    parser.add_argument(
        "--tier",
        default="smoke",
        help=(
            "tier to run when --scenario is not given (default: smoke). This "
            "entrypoint drives a live, authenticated Claude Code session, so "
            "it defaults to the cheap tier rather than to every package on disk"
        ),
    )
    parser.add_argument("--epochs", type=int, default=1, help="epochs per selected scenario (use 5 for the declared deterministic tier)")
    parser.add_argument("--output-dir", type=Path, help="directory for report.json and summary.txt (default: a retained temp directory)")
    parser.add_argument("--claude", type=Path, help="Claude Code executable (default: claude on PATH)")
    parser.add_argument("--claude-config-dir", type=Path, help="host Claude Code config directory used for local authentication")
    parser.add_argument(
        "--allow-host-home",
        action="store_true",
        help=(
            "give the entire Claude agent process the real host HOME, including "
            "access to host config and credential files"
        ),
    )
    parser.add_argument(
        "--allow-host-home-bash",
        action="store_true",
        help="also grant Bash when --allow-host-home is set; shell access can reach the host HOME",
    )
    parser.add_argument("--model", default="sonnet", help="Claude Code model alias")
    parser.add_argument("--effort", default="medium", choices=("low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--max-budget-usd", type=float, help="per-scenario Claude Code spend ceiling")
    parser.add_argument("--turn-timeout", type=float, default=600.0, help="maximum seconds for each Claude turn")
    parser.add_argument("--supervisor", type=Path, help="nxd-desktop-supervisor executable")
    parser.add_argument("--desktop-python", type=Path, default=None, help="desktop supervisor Python interpreter")
    parser.add_argument("--runtime-wheel-version", help="override the runtime pin stored in the manifest")
    parser.add_argument("--model-call-budget", type=float)
    parser.add_argument("--wall-clock-budget", type=float)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local-only live tier and retain its reports."""

    args = build_parser().parse_args(argv)
    if args.turn_timeout <= 0:
        raise TierError("--turn-timeout must be positive")
    if args.allow_host_home_bash and not args.allow_host_home:
        raise TierError("--allow-host-home-bash requires --allow-host-home")
    repo_root = REPO_ROOT
    scenarios = _configure_scenarios(
        _scenarios_in_scope(load_scenarios(SCENARIO_ROOT), args.scenario, args.tier),
        args.scenario,
        args.epochs,
    )
    supervisor = resolve_supervisor(args.supervisor)
    desktop_python = (args.desktop_python or _default_desktop_python()).expanduser().resolve()
    if not desktop_python.is_file() or not desktop_python.stat().st_mode & 0o111:
        raise TierError(f"desktop Python is not executable: {desktop_python}")
    claude = _resolve_executable(args.claude, "claude")
    # Let Claude Code use its normal host-authenticated configuration unless
    # the caller explicitly selects another config directory.  Setting
    # CLAUDE_CONFIG_DIR to the default-looking ~/.claude path makes the CLI
    # use a separate credential lookup path on macOS.
    claude_config_dir = args.claude_config_dir.expanduser().resolve() if args.claude_config_dir is not None else None
    if claude_config_dir is not None and not claude_config_dir.is_dir():
        raise TierError(f"Claude config directory is not a directory: {claude_config_dir}")

    plugin_manifest = json.loads((repo_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    skill_pack_version = plugin_manifest.get("version")
    if not isinstance(skill_pack_version, str) or not skill_pack_version:
        raise TierError(".claude-plugin/plugin.json has no non-empty version")
    claims_hash = load_claims(CANARY_ROOT / "claims.json").baseline.approves_claims_hash
    runtime_pin = args.runtime_wheel_version or _runtime_pin(desktop_python)
    pins = PinnedVersions(
        skill_pack_version=skill_pack_version,
        supervisor_version="sha256:" + _sha256(supervisor),
        runtime_wheel_version=runtime_pin,
        # Keep the manifest comparable even when a scenario does not declare
        # a route-backed source.  The harness implementation is still part of
        # the tier identity and smoke manifests do not permit a waiver here.
        mock_api_version="mock-1",
        canary_claims_hash=claims_hash,
        agent_model_id=args.model,
        agent_sampling_params={"temperature": "provider-default", "effort": args.effort},
    )

    if args.output_dir is None:
        report_dir = Path(tempfile.mkdtemp(prefix="dp-scenarios-local-report-"))
    else:
        report_dir = args.output_dir.expanduser().resolve()
        report_dir.mkdir(parents=True, exist_ok=True)

    plugin_owner, plugin_dir = temporary_plugin(repo_root)
    adapter_kwargs = {
        "claude": str(claude),
        "model": args.model,
        "effort": args.effort,
        "plugin-dir": str(plugin_dir),
        "repo-root": str(repo_root),
        "desktop-supervisor": str(supervisor),
        "desktop-python": str(desktop_python),
        "timeout": str(_adapter_timeout(args.turn_timeout)),
    }
    if claude_config_dir is not None:
        adapter_kwargs["claude-config-dir"] = str(claude_config_dir)
    if args.max_budget_usd is not None:
        adapter_kwargs["max-budget-usd"] = str(args.max_budget_usd)

    def session_factory(scenario: Scenario, environment: Any, epoch: int) -> LiveSession:
        agent_dir = environment.base_dir / "agent"
        agent_dir.mkdir()
        command = [sys.executable, "-m", ADAPTER_MODULE]
        for key, value in adapter_kwargs.items():
            command.extend((f"--{key}", value))
        if args.allow_host_home and not args.allow_host_home_bash:
            command.append("--no-bash")
        command.extend(("--fixture-dir", str(environment.fixture_dir), "--artifact-dir", str(environment.base_dir / "artifacts")))
        agent_environment = _agent_environment(
            environment.agent_environment,
            allow_host_home=args.allow_host_home,
        )
        return LiveSession(
            command,
            environment=agent_environment,
            cwd=agent_dir,
            timeout=args.turn_timeout,
        )

    def supervisor_reader(scenario: Scenario, environment: Any, epoch: int) -> FileSupervisorRecordReader:
        return FileSupervisorRecordReader(environment.base_dir / "artifacts" / "supervisor-facts.json")

    try:
        result = TierRunner(
            scenarios,
            pins=pins,
            canary=lambda: run_drift_canary(CANARY_ROOT, skills_root=repo_root / "src", supervisor=supervisor),
            session_factory=session_factory,
            environment_root=report_dir,
            budgets=RunBudgets(args.model_call_budget, args.wall_clock_budget),
            supervisor_reader=supervisor_reader,
        ).run()
        write_report(result, json_path=report_dir / "report.json", summary_path=report_dir / "summary.txt")
    finally:
        plugin_owner.cleanup()

    print(f"report: {report_dir / 'report.json'}")
    print(f"summary: {report_dir / 'summary.txt'}")
    return 0 if result.verdict == "clean" else 1


if __name__ == "__main__":  # pragma: no cover - exercised as a local entrypoint
    try:
        raise SystemExit(main())
    except TierError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

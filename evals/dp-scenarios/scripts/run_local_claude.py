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
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from dotenv import dotenv_values

from dp_scenarios.canary import load_claims
from dp_scenarios.canary.probe import resolve_supervisor
from dp_scenarios.grading.statistics import RepeatabilityTier
from dp_scenarios.operator.driver import DriverOperator
from dp_scenarios.operator.openai_driver import (
    DriverConfigError,
    OpenAIDriverProvider,
    driver_prompt_hash,
)
from dp_scenarios.runner.environment import PinnedVersions
from dp_scenarios.runner.environment import DEFAULT_WORKFLOW_ACTIVATION_BUNDLE
from dp_scenarios.runner.local import (
    FileSupervisorRecordReader,
    LocalRunnerError,
    staged_job_helper_dir,
    temporary_plugin,
)
from dp_scenarios.runner.report import write_abort_report, write_report
from dp_scenarios.runner.review_guard import (
    DEFAULT_REVIEW_TIMEOUT_SECONDS,
    validate_review_timeout_seconds,
)
from dp_scenarios.runner.session import LiveSession
from dp_scenarios.runner.tier import RunBudgets, TierError, TierRunner, run_drift_canary
from dp_scenarios.scenario import SCENARIO_TIERS, Scenario, load_scenarios, select_tier


REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_ROOT = REPO_ROOT / "evals" / "dp-scenarios" / "scenarios"
CANARY_ROOT = SCENARIO_ROOT / "drift-canary"
CLAUDE_ADAPTER_MODULE = "dp_scenarios.runner.claude_adapter"
CODEX_ADAPTER_MODULE = "dp_scenarios.runner.codex_adapter"
CLAUDE_OAUTH_TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"
OPENAI_API_KEY = "OPENAI_API_KEY"
CODEX_HOME = "CODEX_HOME"


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


KERNEL_HOST_BINARY = "nxd-desktop-kernel-host"


def require_kernel_host_sibling(supervisor: Path) -> Path:
    """Fail before any agent turn when the supervisor cannot spawn its kernel.

    The supervisor resolves ``nxd-desktop-kernel-host`` next to its own
    executable only when validation starts. Without this check a partial
    install (for example a ``target/<profile>`` holding just the supervisor)
    passes every earlier workflow step and then leaves validation stuck, which
    reads as an agent or skill failure instead of an environment defect.
    """

    candidate = supervisor.parent / KERNEL_HOST_BINARY
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise TierError(
            f"{KERNEL_HOST_BINARY} is missing next to the supervisor at {candidate}; "
            "build the desktop supervisor crate's bins into the same directory"
        )
    return candidate


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


def _run_claude_provider_preflight(
    claude: Path,
    *,
    oauth_token: str | None = None,
    config_dir: Path | None = None,
) -> None:
    """Verify Claude authentication before starting an expensive tier run.

    ``claude auth status`` is the only supported local authentication probe;
    the CLI exposes no usage/quota endpoint.  Keep its JSON output in memory,
    inspect only the boolean login result, and never copy provider diagnostics
    into a report or exception.  This catches expired/missing authentication
    without pretending that a provider session limit can be predicted locally.
    """

    child_environment = os.environ.copy()
    if oauth_token is not None:
        child_environment[CLAUDE_OAUTH_TOKEN] = oauth_token
    if config_dir is not None:
        child_environment["CLAUDE_CONFIG_DIR"] = str(config_dir)
    try:
        completed = subprocess.run(
            [str(claude), "auth", "status", "--json"],
            check=False,
            capture_output=True,
            text=True,
            env=child_environment,
            timeout=15.0,
        )
    except subprocess.TimeoutExpired as exc:
        raise TierError("Claude provider authentication preflight timed out") from exc
    except OSError as exc:
        raise TierError("Claude provider authentication preflight could not start") from exc
    if completed.returncode != 0:
        raise TierError("Claude provider authentication preflight failed")
    try:
        status = json.loads(completed.stdout)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TierError("Claude provider authentication preflight returned invalid status") from exc
    if not isinstance(status, Mapping) or status.get("loggedIn") is not True:
        raise TierError("Claude provider authentication preflight found no active login")


def _needs_provider_preflight(scenarios: Sequence[Scenario]) -> bool:
    """Return whether selected scenarios can spend provider-backed turns."""

    return any(getattr(scenario, "tier", None) in {"core", "full", "live"} for scenario in scenarios)


def _resolve_codex_executable(explicit: Path | None) -> Path:
    """Resolve Codex away from an asdf shim that depends on the host HOME."""

    if explicit is not None:
        candidate = explicit.expanduser().absolute()
    else:
        discovered = shutil.which("codex")
        if discovered is None:
            raise TierError("codex was not found on PATH; pass an explicit executable path")
        candidate = Path(discovered).absolute()
    if explicit is None and candidate.parent.name == "shims":
        asdf = shutil.which("asdf")
        if asdf is not None:
            try:
                completed = subprocess.run(
                    [asdf, "which", "codex"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except OSError:
                completed = None
            resolved = Path(completed.stdout.strip()).expanduser().absolute() if completed is not None and completed.returncode == 0 else None
            if resolved is not None and resolved.is_file() and resolved.stat().st_mode & 0o111:
                candidate = resolved
    if not candidate.is_file() or not candidate.stat().st_mode & 0o111:
        raise TierError(f"codex is not an executable file: {candidate}")
    return candidate


def _resolve_codex_home(selected: Path | None) -> Path:
    """Resolve the host Codex auth/config directory without reading it.

    The live agent gets this path through ``CODEX_HOME`` so the Codex CLI can
    use its host-authenticated session while the disposable run HOME remains
    isolated.  The runner never reads, logs, or copies the credentials in the
    directory.
    """

    configured = os.environ.get(CODEX_HOME)
    candidate = (selected or (Path(configured) if configured else Path.home() / ".codex"))
    candidate = candidate.expanduser().absolute()
    if not candidate.is_dir():
        raise TierError(f"Codex home is not a directory: {candidate}")
    return candidate


def _adapter_timeout(turn_timeout: float) -> float:
    """Leave room for the adapter to retain a structured timeout result."""

    if turn_timeout <= 0:
        raise TierError("turn timeout must be positive")
    return turn_timeout * 0.9


def _adapter_command(
    adapter_module: str, adapter_kwargs: Mapping[str, str | None]
) -> list[str]:
    command = [sys.executable, "-m", adapter_module]
    for key, value in adapter_kwargs.items():
        if value is None:
            continue
        if value:
            command.extend((f"--{key}", value))
        else:
            command.append(f"--{key}")
    return command


def _load_local_credentials(env_file: Path | None) -> dict[str, str]:
    """Load only runner credentials from an explicitly selected dotenv file.

    Values are kept in the trusted harness process.  The caller decides which
    credential, if any, crosses a subprocess boundary.  Environment values
    take precedence so a CI secret or one-shot shell override remains useful.
    """

    file_values: dict[str, str] = {}
    if env_file is not None:
        path = env_file.expanduser().resolve()
        if not path.is_file():
            raise TierError(f"credentials file does not exist: {path}")
        if path.stat().st_mode & 0o077:
            raise TierError(f"credentials file must be owner-readable only: {path}")
        parsed = dotenv_values(path)
        for name in (CLAUDE_OAUTH_TOKEN, OPENAI_API_KEY):
            value = parsed.get(name)
            if isinstance(value, str) and value.strip():
                file_values[name] = value.strip()

    credentials: dict[str, str] = {}
    for name in (CLAUDE_OAUTH_TOKEN, OPENAI_API_KEY):
        value = os.environ.get(name) or file_values.get(name)
        if isinstance(value, str) and value.strip():
            credentials[name] = value.strip()
    return credentials


def _default_desktop_python() -> Path:
    return Path.home() / ".nxd" / "desktop-venv" / "bin" / "python"


def resolve_desktop_python(selected: Path | None) -> Path:
    """Return the interpreter the desktop supervisor should spawn.

    Deliberately absolute-but-unresolved.  A virtualenv's ``bin/python`` is a
    symlink to the base interpreter, so resolving it hands the supervisor the
    base interpreter instead -- the same executable, but without the venv's
    site-packages.  A live run on 2026-09-03 lost every build to exactly that:
    the venv carried PyYAML 6.0.3, the resolved base did not, so
    workflow-v2 admission failed for any closure and the build, query,
    narrowing and capability gates all recorded not-examined.  The path must
    stay the venv's own so ``sys.prefix`` lands inside it.
    """

    candidate = (selected or _default_desktop_python()).expanduser().absolute()
    if not candidate.is_file() or not candidate.stat().st_mode & 0o111:
        raise TierError(f"desktop Python is not executable: {candidate}")
    return candidate


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


def _validated_skill_pack_root(selected: Path | None) -> Path:
    """Resolve the skill source without moving the harness or scenario root."""

    root = (selected or REPO_ROOT).expanduser().resolve()
    if not root.is_dir():
        raise TierError(f"skill-pack root is not a directory: {root}")
    src = root / "src"
    manifest_path = root / ".claude-plugin" / "plugin.json"
    if not src.is_dir() or not manifest_path.is_file():
        raise TierError(f"skill-pack root is incomplete: {root}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TierError(f"skill-pack manifest is unreadable: {root}") from exc
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("version"), str)
        or not manifest["version"].strip()
        or not any(path.is_file() for path in src.glob("*/SKILL.md"))
    ):
        raise TierError(f"skill-pack root is incomplete: {root}")
    return root


DriverFactory = Callable[[Any, Any, int], DriverOperator]


def driver_configuration(
    args: argparse.Namespace,
    pins: PinnedVersions,
    *,
    openai_api_key: str | None = None,
) -> tuple[PinnedVersions, DriverFactory | None]:
    """Return the pins and operator factory implied by the driver flags.

    Without ``--driver-model`` this is the identity: the operator stays
    scripted and the pins keep ``driver_model_id`` not-applicable, which is
    what makes a scripted ledger byte-stable.

    With it, the provider is constructed **first**, before the drift canary
    runs and before any scenario fixture is generated. A missing
    ``OPENAI_API_KEY`` is then a refusal that costs nothing, rather than one
    discovered after a canary build and a live agent session have already been
    paid for.
    """

    model = getattr(args, "driver_model", None)
    if model is None:
        return pins, None
    if not isinstance(model, str) or not model.strip():
        raise TierError("--driver-model must be a non-empty model id")
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
        api_key=openai_api_key,
        timeout_seconds=timeout,
        max_tokens=max_tokens,
    )
    driver_pins = replace(
        pins,
        driver_model_id=model,
        # The prompt is part of the operator's identity: two runs with the
        # same model and temperature but different system prompts are two
        # different operators and must not pair.
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

    def factory(scenario: Any, environment: Any, epoch: int) -> DriverOperator:
        return DriverOperator(
            provider,
            model_id=model,
            temperature=temperature,
            provider_timeout_seconds=timeout,
        )

    return driver_pins, factory


def _tool_grant_arguments(args: argparse.Namespace, *, oauth_token_present: bool = False) -> list[str]:
    """Return the adapter flags that decide the agent's tool grants.

    A token and ``--allow-host-home-bash`` are a genuine conflict: the token
    must not reach a shell, and the flag exists to open one.  Resolving it
    silently in either direction is the wrong answer -- withholding Bash makes
    every shell-dependent scenario fail for a reason that appears nowhere in
    the report, and ``CLAUDE_CODE_OAUTH_TOKEN`` is commonly exported, so the
    operator need not have opted into anything to hit it.
    """

    if getattr(args, "agent_backend", "claude") == "codex":
        # Codex owns its own sandbox/tool policy.  Claude-specific tool-grant
        # flags must not be smuggled into the Codex adapter.
        return []
    if oauth_token_present and args.allow_host_home_bash:
        raise TierError(
            "--allow-host-home-bash cannot be combined with a Claude OAuth token: "
            "the token is withheld from the agent shell, so Bash would be denied "
            "and every shell-dependent scenario would fail invisibly. Unset "
            "CLAUDE_CODE_OAUTH_TOKEN (and omit --env-file) to grant Bash, or drop "
            "--allow-host-home-bash to run token-authenticated without a shell."
        )
    if oauth_token_present or (args.allow_host_home and not args.allow_host_home_bash):
        return ["--no-bash"]
    return []


def build_parser() -> argparse.ArgumentParser:
    """Build the local runner CLI parser."""

    parser = argparse.ArgumentParser(description="Run local agent DP-scenarios")
    parser.add_argument(
        "--agent-backend",
        choices=("claude", "codex"),
        default="claude",
        help="agent CLI used for the live session (default: claude)",
    )
    parser.add_argument("--scenario", action="append", default=[], help="scenario id; repeat to select several (default: every scenario in --tier)")
    parser.add_argument(
        "--tier",
        default="smoke",
        choices=sorted(SCENARIO_TIERS),
        help=(
            "tier to run when --scenario is not given (default: smoke). This "
            "entrypoint drives a live, authenticated Claude Code session, so "
            "it defaults to the cheap tier rather than to every package on disk"
        ),
    )
    parser.add_argument("--epochs", type=int, default=1, help="epochs per selected scenario (use 5 for the declared deterministic tier)")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="maximum number of scenario packages to execute concurrently (epochs stay serial)",
    )
    parser.add_argument("--output-dir", type=Path, help="directory for report.json and summary.txt (default: a retained temp directory)")
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=None,
        help=(
            "stable directory for per-turn live handoff checkpoints; omitted means "
            "checkpoint emission is disabled"
        ),
    )
    parser.add_argument(
        "--native-continuation",
        action="store_true",
        help=(
            "explicitly opt into persisted provider sessions and native-resume "
            "checkpoints; requires --native-run-root and --checkpoint-dir "
            "for a fresh run"
        ),
    )
    parser.add_argument(
        "--native-run-root",
        type=Path,
        help="persistent per-scenario run root required by native continuation",
    )
    parser.add_argument(
        "--native-resume-checkpoint",
        type=Path,
        help=(
            "resume one committed native checkpoint; requires the same "
            "--native-run-root and exactly one scenario/epoch"
        ),
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help=(
            "optional owner-readable-only dotenv file; only OPENAI_API_KEY and "
            "CLAUDE_CODE_OAUTH_TOKEN are read"
        ),
    )
    parser.add_argument("--claude", type=Path, help="Claude Code executable (default: claude on PATH)")
    parser.add_argument("--codex", type=Path, help="Codex executable (default: codex on PATH)")
    parser.add_argument(
        "--codex-multi-agent-v2",
        action="store_true",
        help="enable Codex's experimental multi-agent-v2 backend",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        help=(
            "host Codex auth/config directory (default: CODEX_HOME or ~/.codex); "
            "the runner passes only this path to the Codex child"
        ),
    )
    parser.add_argument(
        "--skill-pack-root",
        type=Path,
        default=None,
        help="validated skill-pack checkout used for the staged plugin and drift canary (default: this repo)",
    )
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
    parser.add_argument(
        "--model",
        default=None,
        help="agent model id or provider alias (default: sonnet for Claude, gpt-5.6-luna for Codex)",
    )
    parser.add_argument("--effort", default="medium", choices=("low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--max-budget-usd", type=float, help="per-scenario Claude Code spend ceiling")
    parser.add_argument("--turn-timeout", type=float, default=600.0, help="maximum seconds for each agent turn")
    parser.add_argument(
        "--review-timeout",
        type=float,
        default=DEFAULT_REVIEW_TIMEOUT_SECONDS,
        help="maximum seconds for the retained-capture reviewer (default: 300)",
    )
    parser.add_argument("--supervisor", type=Path, help="nxd-desktop-supervisor executable")
    parser.add_argument(
        "--workflow-activation-bundle",
        type=Path,
        default=DEFAULT_WORKFLOW_ACTIVATION_BUNDLE,
        help="trusted workflow-v2 activation bundle required by every scenario run",
    )
    parser.add_argument("--desktop-python", type=Path, default=None, help="desktop supervisor Python interpreter")
    parser.add_argument("--runtime-wheel-version", help="override the runtime pin stored in the manifest")
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local-only live tier and retain its reports."""

    args = build_parser().parse_args(argv)
    if args.turn_timeout <= 0:
        raise TierError("--turn-timeout must be positive")
    try:
        review_timeout_seconds = validate_review_timeout_seconds(args.review_timeout)
    except ValueError as exc:
        raise TierError("--review-timeout must be a positive finite number") from exc
    if args.jobs < 1:
        raise TierError("--jobs must be a positive integer")
    if args.allow_host_home_bash and not args.allow_host_home:
        raise TierError("--allow-host-home-bash requires --allow-host-home")
    if args.native_continuation and args.native_run_root is None:
        raise TierError("--native-continuation requires --native-run-root")
    if args.native_resume_checkpoint is not None and not args.native_continuation:
        raise TierError("--native-resume-checkpoint requires --native-continuation")
    if args.native_resume_checkpoint is not None and args.native_run_root is None:
        raise TierError("--native-resume-checkpoint requires --native-run-root")
    if args.native_continuation and args.jobs != 1:
        raise TierError("--native-continuation requires --jobs 1")
    if args.agent_backend == "codex" and args.max_budget_usd is not None:
        raise TierError("--max-budget-usd is only supported by the Claude backend")
    if args.agent_backend == "codex" and args.allow_host_home:
        raise TierError(
            "--allow-host-home is not supported by the Codex backend: "
            "the live Codex session must retain the disposable run HOME"
        )
    if args.codex_multi_agent_v2 and args.agent_backend != "codex":
        raise TierError("--codex-multi-agent-v2 requires --agent-backend codex")
    agent_model = args.model or ("sonnet" if args.agent_backend == "claude" else "gpt-5.6-luna")
    repo_root = REPO_ROOT
    skill_pack_root = _validated_skill_pack_root(args.skill_pack_root)
    scenarios = _configure_scenarios(
        _scenarios_in_scope(load_scenarios(SCENARIO_ROOT), args.scenario, args.tier),
        args.scenario,
        args.epochs,
    )
    supervisor = resolve_supervisor(args.supervisor)
    require_kernel_host_sibling(supervisor)
    desktop_python = resolve_desktop_python(args.desktop_python)
    claude: Path | None = None
    codex: Path | None = None
    codex_home: Path | None = None
    if args.agent_backend == "claude":
        claude = _resolve_executable(args.claude, "claude")
    else:
        codex = _resolve_codex_executable(args.codex)
        codex_home = _resolve_codex_home(args.codex_home)
    credentials = _load_local_credentials(args.env_file)
    claude_oauth_token = credentials.get(CLAUDE_OAUTH_TOKEN)
    # Let Claude Code use its normal host-authenticated configuration unless
    # the caller explicitly selects another config directory.  Setting
    # CLAUDE_CONFIG_DIR to the default-looking ~/.claude path makes the CLI
    # use a separate credential lookup path on macOS.
    claude_config_dir = args.claude_config_dir.expanduser().resolve() if args.claude_config_dir is not None else None
    if claude_config_dir is not None and not claude_config_dir.is_dir():
        raise TierError(f"Claude config directory is not a directory: {claude_config_dir}")

    plugin_manifest = json.loads((skill_pack_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
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
        agent_model_id=f"{args.agent_backend}:{agent_model}",
        agent_sampling_params={
            "backend": args.agent_backend,
            "temperature": "provider-default",
            "effort": args.effort,
        },
    )
    pins, operator_factory = driver_configuration(
        args,
        pins,
        openai_api_key=credentials.get(OPENAI_API_KEY),
    )

    if args.output_dir is None:
        report_dir = Path(tempfile.mkdtemp(prefix="dp-scenarios-local-report-"))
    else:
        report_dir = args.output_dir.expanduser().resolve()
        if report_dir.exists() and any(report_dir.iterdir()):
            raise TierError(
                f"output directory is not empty; choose a new directory: {report_dir}"
            )
        report_dir.mkdir(parents=True, exist_ok=True)

    plugin_owner, plugin_dir = temporary_plugin(skill_pack_root)
    try:
        exact_job_helper_dir = staged_job_helper_dir(plugin_dir, skill_pack_version)
    except Exception:
        plugin_owner.cleanup()
        raise
    if args.agent_backend == "claude":
        assert claude is not None
        adapter_module = CLAUDE_ADAPTER_MODULE
        adapter_kwargs = {
            "claude": str(claude),
            "model": agent_model,
            "effort": args.effort,
            "plugin-dir": str(plugin_dir),
            "repo-root": str(repo_root),
            "desktop-supervisor": str(supervisor),
            "desktop-python": str(desktop_python),
            "timeout": str(_adapter_timeout(args.turn_timeout)),
            "review-timeout": f"{review_timeout_seconds:.15g}",
        }
        if claude_config_dir is not None:
            adapter_kwargs["claude-config-dir"] = str(claude_config_dir)
        if args.max_budget_usd is not None:
            adapter_kwargs["max-budget-usd"] = str(args.max_budget_usd)
    else:
        assert codex is not None
        adapter_module = CODEX_ADAPTER_MODULE
        adapter_kwargs = {
            "codex": str(codex),
            "model": agent_model,
            "effort": args.effort,
            # The agent may write within its sandbox. Give it the staged,
            # disposable plugin rather than the caller's source checkout.
            "skill-pack-root": str(plugin_dir),
            "repo-root": str(repo_root),
            "desktop-supervisor": str(supervisor),
            "desktop-python": str(desktop_python),
            "timeout": str(_adapter_timeout(args.turn_timeout)),
            "multi-agent-v2": "" if args.codex_multi_agent_v2 else None,
            "review-timeout": f"{review_timeout_seconds:.15g}",
        }
    if args.native_continuation:
        adapter_kwargs["native-continuation"] = ""

    adapter_command = _adapter_command(adapter_module, adapter_kwargs)
    adapter_command.extend(
        _tool_grant_arguments(
            args,
            oauth_token_present=(claude_oauth_token is not None and args.agent_backend == "claude"),
        )
    )
    adapter_command.extend(("--fixture-dir", "../fixture", "--artifact-dir", "../artifacts"))

    def session_factory(scenario: Scenario, environment: Any, epoch: int) -> LiveSession:
        return environment.live_session(
            timeout=args.turn_timeout,
            native_resume=args.native_continuation,
        )

    def supervisor_reader(scenario: Scenario, environment: Any, epoch: int) -> FileSupervisorRecordReader:
        return FileSupervisorRecordReader(environment.base_dir / "artifacts" / "supervisor-facts.json")

    result = None
    conversations: tuple[Path, ...] = ()
    try:
        if args.agent_backend == "claude" and _needs_provider_preflight(scenarios):
            assert claude is not None
            _run_claude_provider_preflight(
                claude,
                oauth_token=claude_oauth_token,
                config_dir=claude_config_dir,
            )
        result = TierRunner(
            scenarios,
            pins=pins,
            canary=lambda: run_drift_canary(
                CANARY_ROOT,
                skills_root=skill_pack_root / "src",
                supervisor=supervisor,
                defer_legacy_build=True,
            ),
            session_factory=session_factory,
            environment_root=report_dir,
            evidence_root=report_dir / "evidence",
            checkpoint_root=args.checkpoint_dir,
            native_continuation=args.native_continuation,
            native_resume_checkpoint=args.native_resume_checkpoint,
            native_run_root=args.native_run_root,
            budgets=RunBudgets(args.model_call_budget, args.wall_clock_budget),
            supervisor_reader=supervisor_reader,
            live_command=adapter_command,
            live_environment=(
                ({CLAUDE_OAUTH_TOKEN: claude_oauth_token} if claude_oauth_token is not None else None)
                if args.agent_backend == "claude"
                else (
                    {
                        CODEX_HOME: str(codex_home),
                        # A concrete Node-installed Codex binary has a
                        # ``#!/usr/bin/env node`` shebang.  The disposable
                        # HOME deliberately cannot resolve an asdf shim, so
                        # expose only the binary's own directory plus the
                        # inherited safe PATH.
                        "PATH": f"{codex.parent}{os.pathsep}{os.environ.get('PATH', '')}",
                    }
                    if codex_home is not None and codex is not None
                    else None
                )
            ),
            supervisor_command=supervisor,
            supervisor_environment={"NXD_DESKTOP_PYTHON": str(desktop_python)},
            workflow_activation_bundle=args.workflow_activation_bundle,
            workflow_action_guard=(args.agent_backend == "codex"),
            allow_host_home=args.allow_host_home,
            staged_job_helper_dir=exact_job_helper_dir,
            operator_factory=operator_factory,
            review_timeout_seconds=review_timeout_seconds,
            max_workers=args.jobs,
        ).run()
        _, _, conversations = write_report(
            result, json_path=report_dir / "report.json", summary_path=report_dir / "summary.txt"
        )
    except (TierError, DriverConfigError, LocalRunnerError) as exc:
        # Keep an operator-visible, secret-safe artifact even when TierRunner
        # aborts before it can construct a TierResult. The normal outer error
        # path still returns a non-success exit status.
        write_abort_report(
            exc,
            json_path=report_dir / "report.json",
            summary_path=report_dir / "summary.txt",
        )
        print(f"report: {report_dir / 'report.json'}")
        print(f"summary: {report_dir / 'summary.txt'}")
        raise
    finally:
        plugin_owner.cleanup()

    print(f"report: {report_dir / 'report.json'}")
    print(f"summary: {report_dir / 'summary.txt'}")
    for conversation in conversations:
        # stdout is the first place an operator looks after a live run.
        print(f"conversation: {conversation}")
    return 0 if result.verdict == "clean" else 1


if __name__ == "__main__":  # pragma: no cover - exercised as a local entrypoint
    try:
        raise SystemExit(main())
    except (TierError, DriverConfigError, LocalRunnerError) as exc:
        # DriverConfigError carries only the name of the missing variable, never
        # its value; there is nothing to redact on this path.
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

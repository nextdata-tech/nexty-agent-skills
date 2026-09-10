"""Emit honest machine and human tier reports.

The invariant enforced here is that scored gate state, efficiency, manifests,
and repeatability evidence remain separate report surfaces.  A demonstrated-
once observation is rendered as such, never as a percentage, and a clean tier
is described as the checks it performed rather than as cryptographic proof.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from typing import Any

from dp_scenarios.grading import NOT_STAGED_CODES

from .tier import ScenarioRun, TierResult
from .transcript import render_epoch_conversation


class ReportError(ValueError):
    """Raised when a report destination cannot be written safely."""


def machine_report(result: TierResult) -> dict[str, object]:
    """Return the stable JSON-ready tier document."""

    document = _stable_document(result.as_dict(report_safe=True))
    document["report_format_version"] = 1
    document["efficiency_is_reported_only"] = True
    return document


_NON_REPRODUCIBLE_KEYS = frozenset(
    {
        "wall_clock",
        "wall_clock_seconds",
        "total_wall_clock_seconds",
        "observed_wall_clock_seconds",
        "ledger_path",
        "fixture_dir",
        "evidence_bundle_dir",
        "supervisor",
        "closure",
        "command",
    }
)


def _stable_document(value: object) -> object:
    """Remove disposable paths and timing deltas from the machine surface."""

    if isinstance(value, dict):
        return {
            key: _stable_document(item)
            for key, item in value.items()
            if key not in _NON_REPRODUCIBLE_KEYS
        }
    if isinstance(value, list):
        return [_stable_document(item) for item in value]
    return value


def _gate_text(run: ScenarioRun) -> str:
    parts: list[str] = []
    for name in ("intake", "capability", "narrowing", "construction", "build", "query", "follow-up"):
        gate = run.score.gates[name]
        not_staged = next((code for code in gate.codes if code in NOT_STAGED_CODES), None)
        if not_staged is not None:
            parts.append(f"{name}=NOT-STAGED")
            continue
        status = (
            "PASS"
            if gate.passed
            else "UN-GRADED"
            if gate.ungraded
            else "UNEXAMINED"
            if not gate.examined
            else "FAIL"
        )
        codes = ",".join(gate.codes) if gate.codes else "-"
        parts.append(f"{name}={status}[{codes}]")
    return " ".join(parts)


def _coverage_text(run: ScenarioRun) -> str:
    scoreable = [name for name, gate in run.score.gates.items() if gate.required]
    waived = [
        f"{name}({code})"
        for name, gate in run.score.gates.items()
        for code in gate.codes
        if code in NOT_STAGED_CODES
    ]
    scoreable_text = ",".join(scoreable) if scoreable else "none"
    waived_text = ",".join(waived) if waived else "none"
    return f"  scoreable gates: {scoreable_text}; waived: {waived_text}"


def human_summary(result: TierResult) -> str:
    """Render a concise summary with canary, gate, rate, and manifest facts."""

    lines = [
        f"Tier verdict: {result.verdict}",
        f"Total wall-clock: {result.wall_clock_seconds:.3f}s",
        "",
        "Clean tier means the canary found no drift in its claims, scenario gates passed against their oracles, and ledger lint was clean.",
        "The ledger chain is unkeyed: this checks the recorded chain and detects edits that did not recompute it, not cryptographic authenticity.",
        "Efficiency is reported only and never contributes points.",
        "",
        f"Canary: {result.canary.verdict.outcome} (blocking={result.canary.blocking})",
        f"Canary legacy build: {result.canary.legacy_build_status}",
    ]
    if result.canary.legacy_build_status == "deferred_to_workflow_v2":
        lines.append(
            "Canary legacy build was deferred to workflow-v2 scenario execution; "
            "it was not passed. Each scenario must provide its construction and publication gates."
        )
    if result.canary.verdict.issues:
        lines.append("Canary findings:")
        for issue in result.canary.verdict.issues:
            location = f" {issue.skill_file}:{issue.line}" if issue.skill_file and issue.line else ""
            code = f" code={issue.code}" if issue.code else ""
            claim = f" claim={issue.claim_id}" if issue.claim_id else ""
            lines.append(f"- {issue.kind}:{claim}{code}{location} — {issue.message}")
    if result.blocked_by_canary:
        lines.append("Scenarios: none ran; the canary gate returned before scenario transport construction.")
        return "\n".join(lines) + "\n"

    for summary in result.scenarios:
        lines.append("")
        lines.append(f"Scenario {summary.scenario_id} ({summary.repeatability.tier.value}):")
        for run in summary.runs:
            lines.append(
                f"- epoch {run.epoch}: state={run.score.state.value}, stop={run.stop_condition}, "
                f"total={run.score.total}, {_gate_text(run)}"
            )
            lines.append(_coverage_text(run))
            lines.append(
                "  hard gates: "
                + ", ".join(f"{name}={value}" for name, value in run.score.hard_gate_flags.items())
            )
            lines.append(
                f"  route fidelity: {run.route_fidelity_status} ({run.route_fidelity_reason})"
            )
            if run.failure_reason is not None or run.failure_detail is not None:
                # stdout is where an operator decides whether to rerun the
                # scenario or wait for the account.  A run that stopped on a
                # provider ceiling must say so here, not only in report.json.
                # Print only what the record holds.  Inventing a reason here
                # when report.json says null would make the two surfaces
                # disagree about the same run; normalization belongs to the
                # producer, which the engine now does.
                if run.failure_reason is not None:
                    lines.append(f"  interrupted: {run.failure_reason}")
                if run.last_mcp_call is not None:
                    lines.append(f"  last MCP call: {run.last_mcp_call}")
                if run.failure_detail is not None:
                    lines.append(f"  detail: {run.failure_detail}")
            if run.qualification.operator_mode == "driver":
                # Without this a driven run whose every authored turn fell back
                # to the scripted line is indistinguishable from a scripted run
                # in stdout and summary.txt -- the run completes, spends the
                # full agent budget, and the only trace is
                # operator-observations.json. A provider error is a fail-safe
                # fallback, not an abort, so the summary has to say it happened.
                if "operator_fallback" in run.failure_modes:
                    lines.append(
                        "  driver: fell back to scripted lines on at least one authored turn; "
                        "see driver_fallback_reason in operator-observations.json"
                    )
                else:
                    lines.append("  driver: authored every substitutable turn")
            lines.append(
                f"  efficiency: turns={run.efficiency.turns!s}, "
                f"model-calls={run.efficiency.model_calls!s}, wall-clock={run.efficiency.wall_clock!s}"
            )
            lines.append(f"  manifest: run_id={run.manifest.run_id}, fixture={run.manifest.fixture_dir_hash}")
        if summary.repeatability.demonstrated_once is not None:
            lines.append("- repeatability: demonstrated-once; no rate is rendered")
        elif summary.repeatability.rates is not None:
            if not summary.repeatability.rates.rates:
                # Without this the summary prints a bare "- per-gate rates:"
                # header with nothing beneath it and never says, in words, the
                # one fact the reader needs: too few epochs finished to rate.
                lines.append("- per-gate rates: none; too few epochs completed to rate this batch")
            else:
                lines.append("- per-gate rates:")
            for gate, rate in summary.repeatability.rates.rates.items():
                lines.append(
                    f"  {gate}: {rate.passed}/{rate.examined} = {rate.rate:.3f}; "
                    f"Wilson lower bound={rate.lower_bound:.3f}"
                )
            if summary.repeatability.rates.excluded_invalid:
                # "invalid" alone is wrong for half of what this counts: a
                # truncated run scores PASSED with terminal_state=turn_timeout.
                excluded = summary.repeatability.rates.excluded_invalid
                truncated = summary.repeatability.rates.excluded_truncated
                detail = f" ({truncated} truncated)" if truncated else ""
                lines.append(
                    f"  runs excluded from rates (invalid or truncated): {excluded}{detail}"
                )
    return "\n".join(lines) + "\n"


def write_report(
    result: TierResult,
    *,
    json_path: str | Path,
    summary_path: str | Path | None = None,
) -> tuple[Path, Path | None, tuple[Path, ...]]:
    """Write machine JSON, optionally a human summary, and the transcripts.

    Returns the conversation paths so a caller can name them on stdout, which
    is the first place an operator looks after a live run. Without that, the
    only way to learn a transcript exists is to open summary.txt and read to
    the end.
    """

    report = machine_report(result)
    machine_target = Path(json_path)
    machine_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        machine_target.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ReportError(f"could not write machine report {machine_target}: {exc}") from exc
    summary_target: Path | None = None
    if summary_path is not None:
        summary_target = Path(summary_path)
        summary_target.parent.mkdir(parents=True, exist_ok=True)
        try:
            summary_target.write_text(human_summary(result), encoding="utf-8")
        except OSError as exc:
            raise ReportError(f"could not write human report {summary_target}: {exc}") from exc
    conversation_targets = write_conversations(result, machine_target.parent, report=report)
    if summary_target is not None and conversation_targets:
        # Name them in the summary. A transcript nobody knows to look for is a
        # transcript nobody reads: rendering it required knowing a separate
        # script existed and handing it a bundle path.
        lines = ["", "Conversations:"]
        lines += [f"  {path}" for path in conversation_targets]
        try:
            with summary_target.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        except OSError as exc:
            raise ReportError(f"could not append to {summary_target}: {exc}") from exc
    return machine_target, summary_target, conversation_targets


def write_conversations(
    result: TierResult, directory: str | Path, *, report: Any = None
) -> tuple[Path, ...]:
    """Render every epoch's conversation next to the report.

    Written beside the report rather than inside the evidence bundle on
    purpose: the bundle's digest is computed when it is retained, so adding a
    file afterwards would leave the recorded digest describing something the
    bundle no longer is.

    A rendering failure must not lose the run -- the transcript is a
    convenience over evidence already on disk -- but it must not be silent
    either. ``transcript.py`` states the rule for its own output: "a renderer
    that silently drops a malformed turn is worse than one that crashes: the
    reader concludes the turn never happened." The same applies one level up:
    absence alone is indistinguishable from a run that retained no bundle, so
    a failure is reported on stderr and the run continues.
    """

    target_dir = Path(directory)
    written: list[Path] = []
    for run in result.scenario_runs:
        bundle = getattr(run, "evidence_bundle_dir", None)
        if not bundle:
            continue
        destination = target_dir / f"conversation-{run.scenario_id}-epoch-{run.epoch}.md"
        try:
            destination.write_text(
                render_epoch_conversation(bundle, report=report), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001 - never lose a finished run to a renderer
            print(
                f"warning: could not render conversation for {bundle}: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            continue
        written.append(destination)
    return tuple(written)


emit_report = write_report
render_machine_report = machine_report
render_human_summary = human_summary


__all__ = [
    "ReportError",
    "emit_report",
    "human_summary",
    "machine_report",
    "render_human_summary",
    "render_machine_report",
    "write_report",
    "write_conversations",
]

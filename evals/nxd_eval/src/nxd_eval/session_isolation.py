"""Per-case session isolation for :func:`nxd_eval.run_suite`.

Some MCP servers retain conversational state for the lifetime of a connection.
Set ``isolate_sessions=True`` on :func:`nxd_eval.run_suite` when each case must
start from a fresh connection. The individual Inspect logs are collated into one
normal ``.eval`` log, so :class:`nxd_eval.Report` and ``certify`` continue to
work on the result.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

if TYPE_CHECKING:
    from .case import Suite

logger = logging.getLogger(__name__)


class SessionIsolationError(RuntimeError):
    """An isolated run completed partially; ``log_path`` holds its error log.

    ``log_path`` is ``None`` when no case produced a log to collate.
    """

    def __init__(self, log_path: Path | None, errors: list[tuple[str, str]]) -> None:
        self.log_path = log_path
        self.errors = errors
        details = "; ".join(f"{case_id}: {detail}" for case_id, detail in errors)
        artifact = f"partial log written to {log_path}" if log_path else "no partial log was written"
        super().__init__(
            f"{len(errors)} isolated case(s) failed; {artifact}: {details}"
        )


def _parse_timestamp(value: str) -> datetime:
    """Parse an Inspect timestamp into a timezone-aware UTC datetime."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fold_eval_log(base: Any | None, addition: Any) -> Any:
    """Append one case log to an accumulating Inspect ``EvalLog`` in place."""
    if base is None:
        base = addition
        base.samples = list(addition.samples or [])
        base.eval.dataset.samples = len(base.samples)
        base.eval.dataset.sample_ids = [sample.id for sample in base.samples]
        return base

    base.samples = list(base.samples or []) + list(addition.samples or [])
    base.eval.dataset.samples = len(base.samples)
    base.eval.dataset.sample_ids = [sample.id for sample in base.samples]

    if base.stats and addition.stats:
        if addition.stats.started_at and (
            not base.stats.started_at
            or _parse_timestamp(addition.stats.started_at)
            < _parse_timestamp(base.stats.started_at)
        ):
            base.stats.started_at = addition.stats.started_at
        if addition.stats.completed_at and (
            not base.stats.completed_at
            or _parse_timestamp(addition.stats.completed_at)
            > _parse_timestamp(base.stats.completed_at)
        ):
            base.stats.completed_at = addition.stats.completed_at
        if base.stats.model_usage is None:
            base.stats.model_usage = {}
        for model, usage in (addition.stats.model_usage or {}).items():
            if model not in base.stats.model_usage:
                base.stats.model_usage[model] = usage
                continue
            existing = base.stats.model_usage[model]
            for key, value in usage.model_dump().items():
                if isinstance(value, (int, float)):
                    setattr(existing, key, (getattr(existing, key, None) or 0) + value)

    if addition.status != "success" and base.status == "success":
        base.status = addition.status
        if not base.error:
            base.error = addition.error

    reductions = {reduction.scorer: reduction for reduction in (base.reductions or [])}
    for reduction in addition.reductions or []:
        if reduction.scorer in reductions:
            current = reductions[reduction.scorer]
            current.samples = list(current.samples) + list(reduction.samples)
        else:
            reductions[reduction.scorer] = reduction
    base.reductions = list(reductions.values()) or None

    # Report/certify derive their metrics from log.samples. Recomputing Inspect
    # reductions here would require every custom metric to be registered.
    if base.results:
        base.results.total_samples = len(base.samples)
        base.results.completed_samples = sum(
            1 for sample in base.samples if not getattr(sample, "error", None)
        )
        base.results.scores = []
    return base


def run_suite_isolated(
    suite: "Suite",
    *,
    run_one: Callable[..., Path],
    variant: str,
    mcp_url: str | None,
    server_factory: Callable[[], Any] | None,
    agent_prompt: str | None,
    agent_model: str | None,
    authorization: str | None,
    grader_model: str | None,
    epochs: int,
    epochs_reducer: str,
    log_dir: str | Path,
    display: str,
) -> Path:
    """Run each case separately and atomically collate their Inspect logs."""
    if not suite.cases:
        raise ValueError("Suite has no cases to run")

    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    out_path = log_dir_path / (
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S+00-00')}_"
        f"{suite.name}_{uuid4().hex[:12]}.eval"
    )
    logger.info(
        "Using isolated sessions: running %s cases with fresh connections per case",
        len(suite.cases),
    )

    from inspect_ai.log import read_eval_log, write_eval_log

    case_logs: list[Any] = []
    errors: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="nxd_eval_case_") as scratch_dir:
        for index, case in enumerate(suite.cases, start=1):
            logger.info("[%s/%s] %s (isolated session)", index, len(suite.cases), case.id)
            single_case_suite = replace(suite, cases=[case])
            try:
                case_log_path = run_one(
                    single_case_suite,
                    variant=variant,
                    mcp_url=mcp_url,
                    server_factory=server_factory,
                    agent_prompt=agent_prompt,
                    agent_model=agent_model,
                    authorization=authorization,
                    grader_model=grader_model,
                    epochs=epochs,
                    epochs_reducer=epochs_reducer,
                    log_dir=scratch_dir,
                    display=display,
                )
                case_log = read_eval_log(str(case_log_path))
                case_logs.append(case_log)
                Path(case_log_path).unlink(missing_ok=True)
                if case_log.status != "success":
                    errors.append((case.id, f"Inspect completed with status {case_log.status!r}"))
            except Exception as exc:  # preserve completed cases and keep running
                errors.append((case.id, f"{type(exc).__name__}: {exc}"))
                logger.exception("Case %s errored; continuing with remaining isolated cases", case.id)

    if not case_logs:
        raise SessionIsolationError(None, errors)

    accumulated_log: Any | None = None
    for case_log in case_logs:
        accumulated_log = _fold_eval_log(accumulated_log, case_log)

    tmp_out = out_path.with_name(f"{out_path.stem}.tmp.eval")
    try:
        write_eval_log(accumulated_log, str(tmp_out), format="eval")
        os.replace(tmp_out, out_path)
    finally:
        if tmp_out.exists():
            tmp_out.unlink(missing_ok=True)
    if errors:
        logger.error(
            "%s/%s isolated cases failed; partial log written to %s",
            len(errors),
            len(suite.cases),
            out_path,
        )
        raise SessionIsolationError(out_path, errors)
    return out_path

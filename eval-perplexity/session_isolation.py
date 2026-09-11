"""Session isolation fix for eval runner.

This module patches nxd_eval's run_suite to create isolated sessions per test case,
preventing message history pollution (root cause of a02 API 400 error).

Usage:
    Import this module BEFORE calling run_suite:

    from session_isolation import patch_run_suite_for_isolation
    patch_run_suite_for_isolation()

    # Then use run_suite normally:
    log_path = run_suite(...)
"""

from __future__ import annotations

import logging
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from eval_common import PROVIDER_DEFAULT_MODELS

logger = logging.getLogger(__name__)


def _fold_eval_log(base: Any | None, addition: Any) -> Any:
    """Fold one case's EvalLog into an accumulating collated EvalLog.

    On the first call (base=None) the accumulator IS `addition` (no data to
    merge yet); every later call appends `addition`'s samples/stats/etc into
    the running `base` in place. Returns the accumulator either way, so
    callers do `acc = _fold_eval_log(acc, new_log)`.
    """
    if base is None:
        base = addition
        base.samples = list(addition.samples or [])
        base.eval.dataset.samples = len(base.samples)
        base.eval.dataset.sample_ids = [s.id for s in base.samples]
        return base

    base.samples = list(base.samples or []) + list(addition.samples or [])
    base.eval.dataset.samples = len(base.samples)
    base.eval.dataset.sample_ids = [s.id for s in base.samples]

    if base.stats and addition.stats:
        if addition.stats.started_at and (
            not base.stats.started_at or addition.stats.started_at < base.stats.started_at
        ):
            base.stats.started_at = addition.stats.started_at
        if addition.stats.completed_at and (
            not base.stats.completed_at or addition.stats.completed_at > base.stats.completed_at
        ):
            base.stats.completed_at = addition.stats.completed_at
        for model, usage in (addition.stats.model_usage or {}).items():
            if model not in base.stats.model_usage:
                base.stats.model_usage[model] = usage
            else:
                existing = base.stats.model_usage[model]
                for k, v in usage.model_dump().items():
                    if isinstance(v, (int, float)):
                        setattr(existing, k, getattr(existing, k, 0) + v)

    if addition.status == "error":
        base.status = "error"
        if not base.error:
            base.error = addition.error

    merged_reductions = {r.scorer: r for r in (base.reductions or [])}
    for red in addition.reductions or []:
        if red.scorer not in merged_reductions:
            merged_reductions[red.scorer] = red
        else:
            merged_reductions[red.scorer].samples = list(merged_reductions[red.scorer].samples) + list(red.samples)
    base.reductions = list(merged_reductions.values()) or None

    # We don't recompute per-scorer metric values here: nxd_eval's custom
    # metrics (nxd_eval/applicable_accuracy etc.) need its metric registry
    # loaded, which report()/certify() don't consult anyway -- they call
    # read_eval_log() and compute their own stats directly from log.samples.
    if base.results:
        base.results.total_samples = len(base.samples)
        base.results.completed_samples = sum(1 for s in base.samples if not getattr(s, "error", None))

    return base


def patch_run_suite_for_isolation() -> None:
    """Monkey-patch nxd_eval.run_suite to use isolated sessions per case.

    This wraps the original run_suite to run each test case individually
    with a fresh MCP server session, preventing message history pollution
    between test cases.
    """
    try:
        from nxd_eval import run_suite as original_run_suite
    except ImportError:
        logger.warning("nxd_eval not found; session isolation patch skipped")
        return

    @wraps(original_run_suite)
    def patched_run_suite(
        suite: Any,
        mcp_url: str | None = None,
        server_factory: Callable[[], Any] | None = None,
        agent_prompt: str = "",
        agent_model: str = PROVIDER_DEFAULT_MODELS["anthropic"]["agent"],
        grader_model: str = PROVIDER_DEFAULT_MODELS["anthropic"]["grader"],
        epochs: int = 1,
        log_dir: str = "./logs",
        **kwargs: Any,
    ) -> str:
        """Wrapper that isolates sessions per test case.

        The key insight: instead of running suite.cases all at once (which
        shares message history), we run each case individually with its own
        server_factory() call, creating fresh connections.
        """
        from dataclasses import replace
        from pathlib import Path

        if not server_factory:
            logger.warning(
                "server_factory not provided; falling back to default run_suite "
                "(no session isolation)"
            )
            return original_run_suite(
                suite,
                mcp_url=mcp_url,
                server_factory=server_factory,
                agent_prompt=agent_prompt,
                agent_model=agent_model,
                grader_model=grader_model,
                epochs=epochs,
                log_dir=log_dir,
                **kwargs,
            )

        if not suite.cases:
            raise ValueError("Suite has no cases to run")

        import os
        import tempfile
        from copy import deepcopy
        from datetime import datetime, timezone

        from inspect_ai.log import read_eval_log, write_eval_log

        log_dir_path = Path(log_dir)
        log_dir_path.mkdir(parents=True, exist_ok=True)

        # The single file this run produces. Written after every case
        # completes (not just at the end) so log_dir never shows more than
        # one file for this run, and a crash partway through still leaves a
        # usable log of everything that finished before it.
        out_path = log_dir_path / f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S+00-00')}_{suite.name}.eval"

        logger.info(
            f"Using isolated sessions: running {len(suite.cases)} cases with "
            f"separate server connections per case, collating into {out_path.name}"
        )

        results: list[dict[str, Any]] = []
        accumulated_log: Any | None = None

        with tempfile.TemporaryDirectory(prefix="nxd_eval_case_") as scratch_dir:
            for i, case in enumerate(suite.cases, 1):
                logger.info(
                    f"[{i}/{len(suite.cases)}] {case.id} (isolated session) "
                    f"epoch 1/{epochs}"
                )

                # Create single-case suite. We do NOT pass fail_on_error/continue_on_fail
                # to original_run_suite() -- nxd_eval's real signature for these is
                # unverified, and the try/except below already guarantees the loop
                # continues past any case that errors or fails, regardless of what
                # original_run_suite does internally for a single-case run.
                single_case_suite = replace(suite, cases=[case])

                case_log_path = None
                try:
                    # Critical: server_factory() is called HERE for each case,
                    # creating a fresh MCP server instance with no prior message
                    # history. original_run_suite writes its own .eval file per
                    # call -- into scratch_dir, never log_dir, so it never
                    # appears in the directory the caller is watching.
                    case_log_path = original_run_suite(
                        single_case_suite,
                        mcp_url=None,
                        server_factory=server_factory,  # ← Fresh server per case
                        agent_prompt=agent_prompt,
                        agent_model=agent_model,
                        grader_model=grader_model,
                        epochs=epochs,
                        log_dir=scratch_dir,
                        **kwargs,
                    )
                    case_log = read_eval_log(str(case_log_path))

                    # Fold on a COPY of the accumulator, never the real one:
                    # if folding this case throws partway through (malformed
                    # case_log, unexpected shape), the last known-good
                    # accumulated_log is untouched -- nothing to roll back.
                    trial_log = deepcopy(accumulated_log) if accumulated_log is not None else None
                    trial_log = _fold_eval_log(trial_log, case_log)
                    if (
                        trial_log.status != "error"
                        and case_log.status != "error"
                        and not any(r["status"] == "error" for r in results)
                    ):
                        trial_log.status = "success"

                    # Write to a scratch temp file and atomically replace
                    # out_path only once that write fully succeeds. out_path
                    # itself is never opened for writing directly, so a crash
                    # or exception at any point here leaves it exactly as it
                    # was after the previous successful case -- never
                    # truncated or half-written.
                    # write_eval_log() dispatches its on-disk format by the
                    # location's extension, so the scratch name must still
                    # end in .eval for it to recognize the format (format is
                    # also passed explicitly to remove any ambiguity).
                    tmp_out = out_path.with_name(f"{out_path.stem}.tmp{i}.eval")
                    try:
                        write_eval_log(trial_log, str(tmp_out), format="eval")
                        os.replace(tmp_out, out_path)
                    finally:
                        if tmp_out.exists():
                            try:
                                tmp_out.unlink()
                            except OSError:
                                pass

                    # Only commit the trial to the real accumulator after the
                    # atomic replace above has actually succeeded.
                    accumulated_log = trial_log

                    try:
                        Path(case_log_path).unlink()
                    except OSError:
                        pass

                    results.append({"id": case.id, "status": "completed", "error": None})
                    logger.info(f"  ✓ {case.id} completed (status={case_log.status})")

                except Exception as e:
                    results.append(
                        {"id": case.id, "status": "error", "error": f"{type(e).__name__}: {e}"}
                    )
                    logger.error(
                        f"  ✗ {case.id} errored: {type(e).__name__}: {e} "
                        f"(collated log unaffected -- still holds every case completed before this one)"
                    )
                    # Don't stop; continue with next case regardless of the failure

        completed = sum(1 for r in results if r["status"] == "completed")
        errored = len(results) - completed
        logger.info(
            f"Suite run complete: {completed}/{len(results)} cases completed, {errored} errored"
        )
        for r in results:
            print(f"  {r['id']}: {r['status']}" + (f" ({r['error']})" if r.get("error") else ""))

        if accumulated_log is None:
            raise RuntimeError("All test cases errored before producing a log; nothing to return")

        logger.info(f"Collated log: {out_path}")
        print(f"Collated .eval log ({completed}/{len(results)} cases completed): {out_path}")
        return str(out_path)

    # Apply the patch
    import nxd_eval
    nxd_eval.run_suite = patched_run_suite
    logger.info("Session isolation patch applied to nxd_eval.run_suite")

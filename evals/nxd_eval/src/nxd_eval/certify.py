"""Certification gate + ``nxd-eval certify`` CLI.

A certification asks a single sharp question of an eval log: *can we defend a
pass rate at least ``target`` at the suite's declared confidence?* The answer is
yes only when the **lower bound** of the Wilson interval clears the threshold —
never the point estimate. A run that hits a high mean on too few samples has a
lower bound that sags below the target, and it must fail; that is the whole point
of gating on the interval instead of the mean.

Two failure modes are distinct and both surface:

* **fail** — the sample is big enough to bound the margin, but the lower bound
  sits below the target. The change did not clear the bar.
* **refuse** (insufficient N) — the effective sample size is too small to bound
  the pass rate to the requested half-width at all, so the gate cannot make a
  defensible call either way. The CLI exits non-zero with an explicit
  "insufficient N" message rather than pretending to pass or fail.

The margin the gate demands of the interval is ``halfwidth``; ``certify`` refuses
when the observed Wilson half-width on ``N_eff`` exceeds it, because then the
interval is too wide to separate "cleared the target" from "did not".
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .report import Report


@dataclass(frozen=True)
class CertifyResult:
    """Outcome of a certification gate.

    ``passed`` is True only when ``refused`` is False and the Wilson lower bound
    cleared ``target``. ``refused`` is True when ``N_eff`` cannot bound the pass
    rate to ``halfwidth`` — an insufficient-N verdict, distinct from a plain
    fail. ``passed`` and ``refused`` are never both True.
    """

    passed: bool
    refused: bool
    p_hat: float
    ci_low: float
    ci_high: float
    n: int
    n_eff: float
    target: float
    halfwidth: float
    bucket: str
    reason: str
    detail: dict = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        """0 iff the gate passed; non-zero on fail or refusal."""
        return 0 if self.passed else 1


def certify(
    log_path: str | Path,
    *,
    target: float = 0.90,
    halfwidth: float = 0.05,
    method: str = "wilson",
    bucket: str | None = None,
    alpha: float = 0.05,
    report: Report | None = None,
) -> CertifyResult:
    """Gate an eval log's pass rate against ``target`` at ``1 - alpha`` confidence.

    The gate passes iff the Wilson **lower bound** (computed on ``N_eff``, so
    correlated repeats do not buy unearned tightness) is at least ``target``. It
    **refuses** (``refused=True``, non-zero :attr:`CertifyResult.exit_code`) when
    the observed Wilson half-width on ``N_eff`` exceeds ``halfwidth`` — the
    sample cannot bound the margin, so no defensible pass/fail call exists.

    Args:
        log_path: Path to a ``.eval`` log (ignored if ``report`` is supplied).
        target: Minimum defensible pass rate, e.g. ``0.90``.
        halfwidth: Largest tolerable Wilson half-width; a wider interval is an
            insufficient-N refusal.
        method: Interval method — only ``"wilson"`` is supported (guarding
            against a silent swap to a symmetric Wald bound).
        bucket: Which answer bucket to gate (``answer`` / ``clarify`` /
            ``abstain``); ``None`` gates the overall accuracy.
        alpha: Two-sided significance; the CI is a ``1 - alpha`` interval.
        report: A pre-built :class:`Report` to gate instead of reading the log.
    """
    if method != "wilson":
        raise ValueError(
            f"certify only gates on the Wilson interval; got method={method!r}. "
            "A symmetric Wald bound would overstate the lower reach near 1.0 — "
            "exactly the drift this gate exists to prevent."
        )

    rep = report or Report.from_path(log_path, alpha=alpha, variant="candidate")
    card = rep.overall if bucket in (None, "overall") else rep.cards[bucket]
    ci = card.ci
    observed_hw = ci.halfwidth

    # Insufficient N: the interval is too wide to bound the margin. Refuse rather
    # than emit a pass/fail the sample cannot support.
    if card.n == 0:
        return CertifyResult(
            passed=False,
            refused=True,
            p_hat=0.0,
            ci_low=0.0,
            ci_high=0.0,
            n=0,
            n_eff=0.0,
            target=target,
            halfwidth=halfwidth,
            bucket=bucket or "overall",
            reason="insufficient N: no scored samples in this bucket",
            detail={"observed_halfwidth": None},
        )
    if observed_hw > halfwidth + 1e-9:
        return CertifyResult(
            passed=False,
            refused=True,
            p_hat=card.p_hat,
            ci_low=ci.low,
            ci_high=ci.high,
            n=card.n,
            n_eff=card.eff.n_eff,
            target=target,
            halfwidth=halfwidth,
            bucket=bucket or "overall",
            reason=(
                f"insufficient N: Wilson half-width {observed_hw:.3f} on "
                f"N_eff={card.eff.n_eff:.1f} exceeds the required +/-{halfwidth:.3f}; "
                f"the sample cannot bound the pass rate to the requested margin"
            ),
            detail={
                "observed_halfwidth": observed_hw,
                "required_halfwidth": halfwidth,
                "deff": card.eff.deff,
            },
        )

    # Enough resolution to make a call: gate on the LOWER bound, not the mean.
    passed = ci.low >= target - 1e-9
    if passed:
        reason = (
            f"pass: Wilson lower bound {ci.low:.3f} >= target {target:.3f} "
            f"(p_hat={card.p_hat:.3f}, N_eff={card.eff.n_eff:.1f})"
        )
    elif card.p_hat >= target:
        # The mean clears the bar but the interval does not defend it.
        reason = (
            f"fail: Wilson lower bound {ci.low:.3f} < target {target:.3f} "
            f"even though p_hat={card.p_hat:.3f} — the point estimate clears the "
            f"bar but the sample does not defend it at {round((1 - alpha) * 100)}% "
            f"confidence"
        )
    else:
        # The mean misses the bar outright; the interval never had a chance.
        reason = (
            f"fail: Wilson lower bound {ci.low:.3f} < target {target:.3f} "
            f"— the point estimate p_hat={card.p_hat:.3f} is itself below the "
            f"target, so the claim fails on the mean, not only on the interval"
        )
    return CertifyResult(
        passed=passed,
        refused=False,
        p_hat=card.p_hat,
        ci_low=ci.low,
        ci_high=ci.high,
        n=card.n,
        n_eff=card.eff.n_eff,
        target=target,
        halfwidth=halfwidth,
        bucket=bucket or "overall",
        reason=reason,
        detail={
            "observed_halfwidth": observed_hw,
            "required_halfwidth": halfwidth,
            "deff": card.eff.deff,
        },
    )


# --------------------------------------------------------------------------- #
# gate expression parsing:  'accuracy>=0.90'
# --------------------------------------------------------------------------- #

# Metric names the gate expression accepts. All resolve to the bucket accuracy
# lower-bound gate; the name selects which bucket (or overall) is gated.
_GATE_METRICS = {
    "accuracy": None,       # overall accuracy
    "answer": "answer",
    "clarify": "clarify",
    "abstain": "abstain",
}

_GATE_RE = re.compile(
    r"^\s*(?P<metric>[a-z_]+)\s*(?P<op>>=|>)\s*(?P<value>[0-9]*\.?[0-9]+)\s*$"
)


@dataclass(frozen=True)
class Gate:
    """A parsed gate expression ``'<metric> >= <value>'``."""

    metric: str
    bucket: str | None
    target: float


def parse_gate(expr: str) -> Gate:
    """Parse ``'accuracy>=0.90'`` (or a per-bucket ``'abstain>=0.95'``).

    Only ``>=`` / ``>`` against a float are accepted; ``>`` is treated as ``>=``
    for the lower-bound gate (a strict-greater lower bound is not a meaningful
    certification target). Unknown metrics raise ``ValueError``.
    """
    m = _GATE_RE.match(expr)
    if not m:
        raise ValueError(
            f"cannot parse gate {expr!r}; expected e.g. 'accuracy>=0.90'"
        )
    metric = m.group("metric")
    if metric not in _GATE_METRICS:
        raise ValueError(
            f"unknown gate metric {metric!r}; known: {sorted(_GATE_METRICS)}"
        )
    return Gate(
        metric=metric,
        bucket=_GATE_METRICS[metric],
        target=float(m.group("value")),
    )


# --------------------------------------------------------------------------- #
# CLI:  nxd-eval certify --log ... --gate 'accuracy>=0.90' [--baseline ...]
# --------------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nxd-eval",
        description="Report + certify an nxd_eval run.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cert = sub.add_parser(
        "certify",
        help="gate an eval log's pass rate on the Wilson lower bound",
    )
    # --suite kept as a friendly alias for the log path (a suite run == its log).
    src = cert.add_mutually_exclusive_group(required=True)
    src.add_argument("--log", help="path to the .eval log to certify")
    src.add_argument("--suite", help="alias for --log (the suite's eval log)")
    cert.add_argument(
        "--gate",
        default="accuracy>=0.90",
        help="gate expression, e.g. 'accuracy>=0.90' or 'abstain>=0.95'",
    )
    cert.add_argument(
        "--halfwidth",
        type=float,
        default=0.05,
        help="largest tolerable Wilson half-width before refusing (insufficient N)",
    )
    cert.add_argument(
        "--confidence",
        type=float,
        default=0.95,
        help="declared confidence for the interval (alpha = 1 - confidence)",
    )
    cert.add_argument(
        "--baseline",
        default=None,
        help="baseline .eval log to compute a BH-FDR-corrected regression delta",
    )
    cert.add_argument(
        "--json",
        action="store_true",
        help="emit the report (with regression) as JSON before the verdict",
    )

    rep = sub.add_parser("report", help="emit a KPI report for an eval log")
    rsrc = rep.add_mutually_exclusive_group(required=True)
    rsrc.add_argument("--log", help="path to the .eval log")
    rsrc.add_argument("--suite", help="alias for --log")
    rep.add_argument("--baseline", default=None, help="baseline .eval log")
    rep.add_argument(
        "--confidence", type=float, default=0.95, help="CI confidence"
    )
    rep.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    return parser


def _run_certify(args) -> int:
    gate = parse_gate(args.gate)
    alpha = round(1.0 - args.confidence, 10)
    log_path = args.log or args.suite
    rep = Report.from_path(log_path, alpha=alpha, variant="candidate")

    if args.json:
        baseline = (
            Report.from_path(args.baseline, alpha=alpha, variant="baseline")
            if args.baseline
            else None
        )
        print(rep.to_json(baseline=baseline))

    result = certify(
        log_path,
        target=gate.target,
        halfwidth=args.halfwidth,
        bucket=gate.bucket,
        alpha=alpha,
        report=rep,
    )

    verdict = "REFUSE" if result.refused else ("PASS" if result.passed else "FAIL")
    stream = sys.stdout if result.passed else sys.stderr
    print(
        f"[{verdict}] gate '{args.gate}' on {result.bucket}: {result.reason}",
        file=stream,
    )

    if args.baseline and not args.json:
        baseline = Report.from_path(args.baseline, alpha=alpha, variant="baseline")
        for b, d in rep.regression_against(baseline).items():
            if d.mcnemar_p_adj < 0.05 and d.delta < 0:
                print(
                    f"  regression[{b}]: {d.delta * 100:.1f}pp "
                    f"(BH-FDR p={d.mcnemar_p_adj:.3f}, {d.b} lost / {d.c} gained)",
                    file=sys.stderr,
                )
    return result.exit_code


def _run_report(args) -> int:
    alpha = round(1.0 - args.confidence, 10)
    log_path = args.log or args.suite
    rep = Report.from_path(log_path, alpha=alpha)
    baseline = (
        Report.from_path(args.baseline, alpha=alpha, variant="baseline")
        if args.baseline
        else None
    )
    if args.format == "json":
        print(rep.to_json(baseline=baseline))
    else:
        print(rep.to_markdown(baseline=baseline))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``nxd-eval`` — returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "certify":
        return _run_certify(args)
    if args.command == "report":
        return _run_report(args)
    parser.error(f"unknown command {args.command!r}")
    return 2  # pragma: no cover - argparse exits first


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

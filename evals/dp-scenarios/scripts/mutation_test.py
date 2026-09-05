#!/usr/bin/env python3
"""Drive mutmut over the guarded directories and report survivors as findings.

Why this exists
---------------
``evals/dp-scenarios`` has always asked contributors to mutation-test a new
check by hand: break the guard, rerun, confirm red.  Two things go wrong with
that.  A hand-rolled mutation can fail to apply at all -- a regex that misses
its line, a ``str.replace`` that silently no-ops -- and a run that never changed
the code reads as "the guard is unenforced" when the guard was fine.  And
nobody hand-mutates code they did not just write, which is exactly where the
recurring defect of this suite lives: a gate that exists but never fires.

mutmut applies each mutant through a generated trampoline, so a mutant that did
not apply cannot be reported as a result at all -- the failure mode that
produced two wrong conclusions in the past is structurally impossible here.

Two tiers
---------
``full``     every mutant in the guarded directories.  Nightly.
``changed``  only the modules the diff touches.  Fast enough for a PR.

Both tiers compare against ``mutation-baseline.json``: a per-function count of
mutants the suite did not notice -- ones that survived, and ones no test
reaches at all.  The baseline is keyed by *function* rather than by mutant name
because mutmut numbers mutants by position within a function -- editing a
function renumbers all of its mutants, so a name-keyed baseline would go red on
every edit for reasons unrelated to test quality.  A function-keyed count is
stable under renumbering and still fails the moment a change adds an untested
branch.

Usage
-----
    scripts/mutation_test.py full
    scripts/mutation_test.py changed [--base origin/main]
    scripts/mutation_test.py full --update-baseline
    scripts/mutation_test.py filter dp_scenarios.grading.gates.x_check_gate__mutmut_3
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "mutation-baseline.json"
REPORT_PATH = PROJECT_ROOT / "mutation-report.txt"

# The two directories the tooling guards.  Kept here rather than derived from
# pyproject's ``only_mutate`` so that `changed` can map a changed file back to
# the mutmut module filter without parsing glob patterns.
GUARDED_DIRS = (
    Path("src/dp_scenarios/operator"),
    Path("src/dp_scenarios/grading"),
)

# ``dp_scenarios.grading.gates.x_phase_ok__mutmut_12`` ->
# ("dp_scenarios.grading.gates", "phase_ok")
_MUTANT_NAME = re.compile(r"^(?P<module>[\w.]+?)\.x_(?P<function>\w+?)__mutmut_\d+$")

REPORTED_STATUSES = ("survived", "no tests", "timeout", "suspicious", "segfault")

# Both mean "the suite did not notice this change", and both are failed on.
# ``no tests`` deserves the same weight as ``survived``: it is what a brand-new
# function with no test at all reports, because the covering-test analysis found
# nothing that executes it. Treating it as merely informational would let a run
# pass a change that added an entirely unexercised gate, which is the defect
# this tooling exists to catch.
UNNOTICED_STATUSES = ("survived", "no tests")

# No verdict was reached for these: the child died or ran out of time, so the
# mutant was neither killed nor shown to survive.
UNVERDICTED_STATUSES = ("timeout", "suspicious", "segfault")


class MutationError(RuntimeError):
    pass


class _Tee:
    """Mirror everything printed into the report file CI publishes.

    The findings are the product of this job, and a reader who only has the
    workflow summary should see the same text the operator saw locally.
    """

    def __init__(self, stream: object, path: Path) -> None:
        self._stream = stream
        self._file = path.open("w", encoding="utf-8")

    def write(self, text: str) -> int:
        self._file.write(text)
        self._file.flush()
        return self._stream.write(text)  # type: ignore[attr-defined,no-any-return]

    def flush(self) -> None:
        self._file.flush()
        self._stream.flush()  # type: ignore[attr-defined]

    def close(self) -> None:
        self._file.close()


def _run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=capture,
        check=False,
    )


def _mutmut(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return _run(["uv", "run", "--project", str(PROJECT_ROOT), "mutmut", *args], capture=capture)


def changed_modules(base: str) -> list[str]:
    """Return mutmut module filters for guarded files changed against ``base``.

    Deterministic by construction: the same diff always yields the same filter
    list, in sorted order, so a red PR job is reproducible by copy-pasting the
    command the job prints.
    """

    merge_base = _run(["git", "merge-base", base, "HEAD"], capture=True)
    ref = merge_base.stdout.strip() if merge_base.returncode == 0 else base
    diff = _run(["git", "diff", "--name-only", ref, "--"], capture=True)
    if diff.returncode != 0:
        raise MutationError(f"could not diff against {ref!r}: {diff.stderr.strip()}")

    repo_root = Path(
        _run(["git", "rev-parse", "--show-toplevel"], capture=True).stdout.strip()
    )
    filters: set[str] = set()
    for line in diff.stdout.splitlines():
        if not line.endswith(".py"):
            continue
        absolute = (repo_root / line).resolve()
        try:
            relative = absolute.relative_to(PROJECT_ROOT)
        except ValueError:
            continue
        if not any(relative.is_relative_to(guarded) for guarded in GUARDED_DIRS):
            continue
        module = ".".join(relative.with_suffix("").parts[1:])  # drop the leading "src"
        filters.add(f"{module}.*")
    return sorted(filters)


def in_scope(mutant_name: str, filters: list[str]) -> bool:
    """Whether this mutant is one the current run actually re-checked.

    ``mutmut results`` reads every ``.meta`` file under ``mutants/``, including
    verdicts left behind by an earlier run with a different scope.  Without this
    filter, a scoped run reports the previous run's survivors as its own -- a
    local re-run would blame a one-line change for thirteen unrelated
    functions.  An empty filter list means the whole scope, so everything counts.
    """

    return not filters or any(fnmatch.fnmatch(mutant_name, pattern) for pattern in filters)


def parse_results(text: str, filters: list[str]) -> dict[str, list[str]]:
    """Group ``mutmut results`` output by status, within the current scope."""

    grouped: dict[str, list[str]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if ": " not in stripped:
            continue
        name, _, status = stripped.rpartition(": ")
        if status not in REPORTED_STATUSES or not in_scope(name, filters):
            continue
        grouped.setdefault(status, []).append(name)
    return grouped


def evaluated_count(text: str, filters: list[str]) -> int:
    """How many mutants this run reached a verdict on, in scope, at any status.

    Deliberately not derived from :func:`parse_results`: that keeps only
    :data:`REPORTED_STATUSES`, and ``killed`` is not among them, so a run that
    killed every mutant -- the best possible outcome -- would count as zero and
    be failed as an aborted run.
    """

    total = 0
    for line in text.splitlines():
        stripped = line.strip()
        if ": " not in stripped:
            continue
        name, _, status = stripped.rpartition(": ")
        if not status or not in_scope(name, filters):
            continue
        total += 1
    return total


def function_key(mutant_name: str) -> str:
    match = _MUTANT_NAME.match(mutant_name)
    if not match:
        # Method mutants carry a class segment; fall back to trimming the index
        # so an unrecognised shape still lands in a stable bucket rather than
        # being silently dropped from the comparison.
        return mutant_name.rsplit("__mutmut_", 1)[0]
    return f"{match['module']}.{match['function']}"


def survivor_counts(mutants: list[str]) -> dict[str, int]:
    """Count unnoticed mutants per function."""

    return dict(sorted(Counter(function_key(name) for name in mutants).items()))


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.is_file():
        return {}
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in data.get("survivors_by_function", {}).items()}


def write_baseline(counts: dict[str, int], *, scope: str) -> None:
    BASELINE_PATH.write_text(
        json.dumps(
            {
                "_comment": (
                    "Surviving mutants per function, from scripts/mutation_test.py. "
                    "Keyed by function because mutmut numbers mutants positionally. "
                    "Every entry is a mutation the suite does not notice: see the "
                    "'Mutation testing' section of README.md before adding one."
                ),
                "scope": scope,
                "survivors_by_function": counts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def regressions(counts: dict[str, int], baseline: dict[str, int]) -> dict[str, tuple[int, int]]:
    return {
        key: (baseline.get(key, 0), observed)
        for key, observed in counts.items()
        if observed > baseline.get(key, 0)
    }


def explain(mutants: list[str], keys: set[str], limit: int) -> None:
    """Print the diff of each survivor under a regressed function.

    A count alone is not actionable.  ``mutmut show`` prints the exact source
    change the suite failed to notice, which names the untested property
    directly.
    """

    offenders = [name for name in mutants if function_key(name) in keys][:limit]
    for name in offenders:
        print(f"\n--- surviving mutant: {name} ---")
        shown = _mutmut("show", name, capture=True)
        sys.stdout.write(shown.stdout)
        print(f"    reproduce: cd evals/dp-scenarios && uv run mutmut run '{name}'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("full", "changed", "filter"))
    parser.add_argument("filters", nargs="*", help="explicit mutmut mutant-name filters (mode=filter)")
    parser.add_argument("--base", default="origin/main", help="diff base for mode=changed")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--max-children", type=int, default=None)
    parser.add_argument("--explain-limit", type=int, default=20)
    parser.add_argument("--clean", action="store_true", help="discard ./mutants before running")
    parser.add_argument(
        "--allow-unverdicted",
        action="store_true",
        help="report a run in which some mutants crashed or timed out (never the default off macOS)",
    )
    args = parser.parse_args(argv)

    if shutil.which("uv") is None:
        raise MutationError("uv is required to run the dp-scenarios project environment")

    if args.mode == "changed":
        filters = changed_modules(args.base)
        if not filters:
            print("No guarded module changed; nothing to mutate.")
            return 0
    elif args.mode == "filter":
        filters = list(args.filters)
        if not filters:
            raise MutationError("mode=filter needs at least one mutant-name filter")
    else:
        filters = []

    if args.clean:
        shutil.rmtree(PROJECT_ROOT / "mutants", ignore_errors=True)

    run_args = ["run", *filters]
    if args.max_children is not None:
        run_args += ["--max-children", str(args.max_children)]
    quoted = " ".join(f"'{f}'" for f in filters)
    printable = quoted or "(all guarded modules)"
    print(f"scope: {printable}")
    # Printed even on a green run: when this job goes red weeks from now, the
    # first thing its reader needs is the command that reproduces it.
    print(f"reproduce: cd evals/dp-scenarios && uv run mutmut run {quoted}\n".rstrip() + "\n", flush=True)

    started = time.monotonic()
    completed = _mutmut(*run_args)
    elapsed = time.monotonic() - started
    # mutmut exits non-zero when mutants survive, which is the normal state
    # here. A genuine tool failure is caught by the empty-result check below,
    # not by this exit code.
    print(f"\nmutmut run finished in {elapsed / 60:.1f} min (exit {completed.returncode})")

    results = _mutmut("results", capture=True)
    if results.returncode != 0:
        raise MutationError(f"mutmut results failed:\n{results.stdout}{results.stderr}")
    grouped = parse_results(results.stdout, filters)

    unnoticed = [name for status in UNNOTICED_STATUSES for name in grouped.get(status, [])]
    for status in REPORTED_STATUSES:
        print(f"  {status:<12} {len(grouped.get(status, []))}")

    # A mutant that crashed or timed out has no verdict. Reporting it as
    # anything other than an error is the failure this tooling exists to
    # remove: a run that did not measure something must not read as a run that
    # measured it and found nothing.
    unverdicted = sum(len(grouped.get(status, [])) for status in UNVERDICTED_STATUSES)
    if unverdicted:
        print(
            f"\n{unverdicted} mutant(s) reached no verdict (crash or timeout). "
            "The score below is a floor, not a measurement."
        )
        if sys.platform == "darwin":
            print(
                "  On macOS this is expected: sqlite3.connect() segfaults in a forked "
                "child, and mutmut forks per mutant. See 'Mutation testing' in README.md. "
                "The authoritative run is CI, on Linux."
            )
        elif not args.allow_unverdicted:
            print("  Refusing to report a partial run as a result. Pass --allow-unverdicted to override.")
            return 3

    # A run that evaluated nothing must not read as a run that evaluated
    # everything and found nothing wrong. `regressions()` iterates *observed*
    # counts, so an empty result set compares nothing against the baseline,
    # finds no regression and exits 0 -- the report says "no mutation the suite
    # fails to notice" when the truth is that no mutation was tried. mutmut
    # aborting (a bad filter, a collection error, a killed process) lands
    # exactly here, and it is the one remaining way for either tier to be
    # structurally green.
    #
    # The scope having no mutants at all is a different thing and is legitimate:
    # `scoped` mode with a diff that touches no guarded file exits before this
    # point.
    evaluated = evaluated_count(results.stdout, filters)
    if not evaluated:
        print(
            f"\nmutmut reported no mutants for this scope (exit {completed.returncode}). "
            "That is a failed run, not a clean one -- nothing was measured. "
            f"Reproduce with: cd evals/dp-scenarios && uv run mutmut run {quoted}".rstrip()
        )
        return 4

    counts = survivor_counts(unnoticed)

    if args.update_baseline:
        # Only the whole-scope run may write the baseline. A scoped run sees
        # nothing outside the modules it mutated, so writing its counts would
        # silently erase every recorded survivor in the rest of the package and
        # turn the next full run into a wall of false regressions.
        if args.mode != "full":
            raise MutationError("--update-baseline requires mode=full")
        write_baseline(counts, scope=printable)
        print(f"\nWrote {BASELINE_PATH.name} ({len(counts)} functions).")
        return 0

    # An absent baseline is not a regression. Failing here would mean the first
    # run on a fresh checkout reports every long-standing gap as something this
    # change introduced -- the loudest possible false alarm, and the fastest way
    # to get the job switched off.
    if not BASELINE_PATH.is_file():
        print(
            f"\nNo {BASELINE_PATH.name} to compare against, so nothing is failed on. "
            f"Record the current state with `scripts/mutation_test.py full --update-baseline`; "
            f"from then on this run fails on anything above it."
        )
        return 0

    # Comparison is per observed function, so a scoped run needs no filtering:
    # a baseline entry for a function this run did not mutate is simply never
    # consulted.
    new = regressions(counts, load_baseline())
    if not new:
        print("\nNo mutation the suite fails to notice, beyond the recorded baseline.")
        return 0

    print(f"\n{len(new)} function(s) gained unnoticed mutants (survived or untested):")
    for key, (was, now) in sorted(new.items()):
        print(f"  {key}: {was} -> {now}")
    explain(unnoticed, set(new), args.explain_limit)
    print(
        "\nEach diff above is a change to the guarded code that the whole suite "
        "still passes with. Either add a test that fails on it, or -- if it is "
        "genuinely equivalent -- record it with "
        "`scripts/mutation_test.py full --update-baseline` and say why in the PR."
    )
    return 1


if __name__ == "__main__":
    tee = _Tee(sys.stdout, REPORT_PATH)
    sys.stdout = tee  # type: ignore[assignment]
    try:
        code = main()
    except MutationError as error:
        print(f"error: {error}")
        code = 2
    finally:
        sys.stdout = sys.__stdout__
        tee.close()
    raise SystemExit(code)

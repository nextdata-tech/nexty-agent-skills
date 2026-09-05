"""The mutation wrapper's own decision logic.

`scripts/mutation_test.py` decides whether a mutation run passes or fails, and
it had no tests. Two of its defects were found by smoke-testing it against a
synthetic change rather than by reading it -- a scoped run reporting a previous
run's survivors as its own, and `no tests` not being failed on -- and both were
the same shape: the gate reporting green without having measured what it
claims. These pin the decisions that shape matters for.
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mutation_test.py"


def _load() -> types.ModuleType:
    module = types.ModuleType("mutation_test_under_test")
    module.__file__ = str(_SCRIPT)
    exec(compile(_SCRIPT.read_text(encoding="utf-8"), str(_SCRIPT), "exec"), module.__dict__)
    return module


@pytest.fixture
def mt() -> types.ModuleType:
    return _load()


# --- what counts as a regression ------------------------------------------


def test_a_function_absent_from_the_baseline_regresses_on_its_first_survivor(mt) -> None:
    """A new function has no baseline entry, so any unnoticed mutant is new.

    This is what makes a stale baseline dangerous rather than merely
    out of date: five functions were added to the guarded directories by a
    change that landed after the baseline was recorded, and every unnoticed
    mutant in them is a regression by construction -- attributed to whoever
    merges next.
    """

    assert mt.regressions({"operator.matcher.solicits_operator": 3}, {}) == {
        "operator.matcher.solicits_operator": (0, 3)
    }


def test_a_count_at_or_below_the_baseline_is_not_a_regression(mt) -> None:
    baseline = {"grading.scans.supported_path_scan": 143}
    assert mt.regressions({"grading.scans.supported_path_scan": 143}, baseline) == {}
    assert mt.regressions({"grading.scans.supported_path_scan": 12}, baseline) == {}
    assert mt.regressions({"grading.scans.supported_path_scan": 144}, baseline) == {
        "grading.scans.supported_path_scan": (143, 144)
    }


def test_a_baseline_entry_the_run_never_mutated_is_not_consulted(mt) -> None:
    """A scoped run must not be failed by functions outside its scope."""

    assert mt.regressions({}, {"grading.gates.gate_capability": 922}) == {}


# --- what counts as unnoticed ---------------------------------------------


def test_no_tests_is_unnoticed_alongside_survived(mt) -> None:
    """`no tests` is what a brand-new unexercised function reports.

    Treating it as informational would let exactly the defect this tooling
    exists to catch -- a gate nothing executes -- through the gate.
    """

    assert set(mt.UNNOTICED_STATUSES) == {"survived", "no tests"}
    assert set(mt.UNVERDICTED_STATUSES) == {"timeout", "suspicious", "segfault"}
    # No status is both measured-and-unnoticed and unverdicted.
    assert not set(mt.UNNOTICED_STATUSES) & set(mt.UNVERDICTED_STATUSES)


def test_a_scoped_run_ignores_another_runs_leftover_verdicts(mt) -> None:
    """`mutmut results` reads every .meta under mutants/, including stale ones."""

    text = "\n".join(
        [
            "operator.matcher.xǁMatcherBankǁ_classify__mutmut_3: survived",
            "grading.scans.supported_path_scan__mutmut_9: survived",
        ]
    )
    scoped = mt.parse_results(text, ["operator.matcher.*"])
    assert scoped == {"survived": ["operator.matcher.xǁMatcherBankǁ_classify__mutmut_3"]}
    # No filter means the whole scope, so nothing is dropped.
    assert len(mt.parse_results(text, [])["survived"]) == 2


def test_method_mutants_group_under_a_stable_key(mt) -> None:
    counts = mt.survivor_counts(
        [
            "operator.engine.xǁOperatorEngineǁrun__mutmut_1",
            "operator.engine.xǁOperatorEngineǁrun__mutmut_2",
            "operator.matcher.solicits_operator__mutmut_1",
        ]
    )
    assert sum(counts.values()) == 3
    assert len(counts) == 2, counts


# --- the guard that makes an aborted run loud -----------------------------


def _fake_mutmut(results_stdout: str, run_exit: int = 1, *, seen: list | None = None):
    def fake(*args, capture: bool = False):
        if seen is not None:
            seen.append(args[0] if args else "run")
        if args and args[0] == "results":
            return subprocess.CompletedProcess(args, 0, stdout=results_stdout, stderr="")
        return subprocess.CompletedProcess(args, run_exit, stdout="", stderr="")

    return fake


def test_a_run_that_evaluated_nothing_fails_instead_of_reporting_clean(mt, capsys) -> None:
    """The last structural way for the gate to be green without measuring.

    `regressions()` iterates *observed* counts, so an empty result set compares
    nothing against the baseline, finds no regression and exits 0 -- printing
    "No mutation the suite fails to notice" when nothing was tried. mutmut
    aborting on a collection error lands exactly here, and it did: the first
    attempt at regenerating the baseline died on a container-only test failure
    and would have been reported as a clean run.
    """

    mt._mutmut = _fake_mutmut("")
    assert mt.main(["full"]) == 4
    out = capsys.readouterr().out
    assert "failed run, not a clean one" in out
    assert "No mutation the suite fails to notice" not in out


def test_a_run_that_killed_every_mutant_is_not_mistaken_for_an_aborted_one(mt, capsys) -> None:
    """The best possible outcome must not be reported as a failed run.

    ``killed`` is not in ``REPORTED_STATUSES`` -- only the unnoticed and the
    unverdicted are listed -- so deriving the evaluated count from the grouped
    statuses made a run that killed everything indistinguishable from a run
    that measured nothing. ``evaluated_count`` reads every in-scope verdict
    line instead, whatever its status.
    """

    mt._mutmut = _fake_mutmut("operator.matcher.solicits_operator__mutmut_1: killed")
    mt.load_baseline = lambda: {}
    mt.BASELINE_PATH = Path("/nonexistent/mutation-baseline.json")
    assert mt.main(["full"]) == 0
    assert "failed run, not a clean one" not in capsys.readouterr().out


def test_the_evaluated_count_respects_the_run_scope(mt) -> None:
    """A stale verdict from another scope must not vouch for this run.

    Without this the guard could be satisfied entirely by `.meta` files an
    earlier, wider run left behind under `mutants/` -- so a scoped run that
    itself measured nothing would look like it had measured something. It is
    the same leftover-verdict problem `in_scope` exists for, one level up.
    """

    text = "\n".join(
        [
            "grading.scans.supported_path_scan__mutmut_9: killed",
            "grading.gates.gate_capability__mutmut_2: survived",
        ]
    )
    assert mt.evaluated_count(text, []) == 2
    assert mt.evaluated_count(text, ["operator.matcher.*"]) == 0
    assert mt.evaluated_count(text, ["grading.scans.*"]) == 1


def test_the_function_key_fallback_produces_a_stable_bucket(mt) -> None:
    """The branch that keys every real baseline entry, and its escape hatch.

    `_MUTANT_NAME` matches the ordinary `module.function__mutmut_N` shape.
    Method mutants carry mutmut's `xǁClassǁmethod` mangling and a name it
    cannot parse must still land somewhere stable, or it is silently dropped
    from the comparison -- an unnoticed mutant that no baseline entry can ever
    account for.
    """

    # A real mutmut name carries an ``x_`` prefix on the function segment --
    # ``dp_scenarios.operator.matcher.x_solicits_operator__mutmut_4`` -- and the
    # regex exists to strip it. Without the prefix the name falls through to the
    # fallback, which returns the same string, so a fixture that omits it tests
    # the fallback while appearing to test the regex.
    real = "dp_scenarios.operator.matcher.x_solicits_operator__mutmut_4"
    assert mt._MUTANT_NAME.match(real), "fixture must exercise the regex branch"
    assert mt.function_key(real) == "dp_scenarios.operator.matcher.solicits_operator"

    # Method mutants carry mutmut's class mangling and do not match the regex;
    # they must still bucket stably rather than being dropped.
    method = "dp_scenarios.operator.engine.xǁOperatorEngineǁrun__mutmut_1"
    assert not mt._MUTANT_NAME.match(method), "fixture must exercise the fallback"
    assert mt.function_key(method) == mt.function_key(
        "dp_scenarios.operator.engine.xǁOperatorEngineǁrun__mutmut_2"
    )
    assert "__mutmut_" not in mt.function_key(method)


def test_an_unverdicted_run_is_refused_unless_explicitly_allowed(mt, capsys, monkeypatch) -> None:
    """A crashed or timed-out mutant has no verdict, so the score is a floor.

    Reporting it as anything else is the failure this tooling exists to remove.
    The override exists because macOS cannot avoid it, so it must be explicit.
    """

    monkeypatch.setattr(mt.sys, "platform", "linux")
    mt._mutmut = _fake_mutmut("operator.engine.xǁOperatorEngineǁrun__mutmut_1: segfault")
    assert mt.main(["full"]) == 3
    assert "Refusing to report a partial run" in capsys.readouterr().out

    mt._mutmut = _fake_mutmut("operator.engine.xǁOperatorEngineǁrun__mutmut_1: segfault")
    mt.BASELINE_PATH = Path("/nonexistent/mutation-baseline.json")
    assert mt.main(["full", "--allow-unverdicted"]) == 0


def test_recording_a_baseline_clears_another_runs_verdicts_first(mt, tmp_path, monkeypatch) -> None:
    """`--update-baseline` must record only what this run measured.

    `mutmut results` reads every `.meta` under `mutants/`, and in `full` mode
    `in_scope` returns True for everything, so a run that aborted early would
    otherwise write a previous scoped run's leftovers into the baseline. That
    is the one moment a wrong baseline gets created, and a wrong baseline is
    what this wrapper exists to prevent.
    """

    stale = tmp_path / "mutants"
    stale.mkdir()
    (stale / "leftover.meta").write_text("from an earlier scope", encoding="utf-8")
    monkeypatch.setattr(mt, "MUTANTS_DIR", stale)
    monkeypatch.setattr(mt, "BASELINE_PATH", tmp_path / "mutation-baseline.json")

    # Ordering is the property, not the end state: clearing *after* the run
    # would leave the assertion below true while reintroducing the bug, because
    # `mutmut results` would already have read the leftovers. Record whether the
    # tree still existed at each mutmut call instead.
    existed_at: dict[str, bool] = {}

    def fake(*args, capture: bool = False):
        existed_at[args[0] if args else "run"] = stale.exists()
        if args and args[0] == "results":
            return subprocess.CompletedProcess(
                args, 0, stdout="dp_scenarios.operator.matcher.x_solicits_operator__mutmut_1: survived\n", stderr=""
            )
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    mt._mutmut = fake
    assert mt.main(["full", "--update-baseline"]) == 0
    assert existed_at["run"] is False, "the run must not inherit another scope's verdicts"
    assert existed_at["results"] is False
    assert not stale.exists()
    assert (tmp_path / "mutation-baseline.json").is_file()

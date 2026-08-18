"""The runner-side deterministic gate must BITE on a wrong-number closure.

The scenario it guards ships ground truth stating both the correct netted
totals and the exact totals a closure that forgot to net refunds produces. The
point of wiring the checker into the harness is that the second kind of closure
can no longer pass on a generous judge read. These tests assert that directly,
by building both closures and running the real checker over each — a green run
alone would not distinguish a working gate from one that never fires.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import stat
import sys
from decimal import Decimal
from pathlib import Path

import pytest

EVALS_DIR = Path(__file__).resolve().parents[1]
SCENARIO = EVALS_DIR / "public" / "derive-models-from-questions"
FIXTURES = SCENARIO / "fixtures"

duckdb = pytest.importorskip("duckdb")


def _load_run_module():
    """Import evals/run.py by path — it is a script, not an installed package.

    It imports its siblings (``eval_backends``) as top-level modules, so
    ``evals/`` has to be importable before the module body executes.
    """
    if str(EVALS_DIR) not in sys.path:
        sys.path.insert(0, str(EVALS_DIR))
    spec = importlib.util.spec_from_file_location("evals_run", EVALS_DIR / "run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


run = _load_run_module()

CHECK_CFG = {"script": "check_derived_closure.py", "deps": ["duckdb"]}

# A closure the checker accepts: reads the source, joins a landed ruling,
# reconciles a signed measure against an independent read of the source.
TRANSFORM_SRC = '''
from decimal import Decimal

BASE_MODELS = ("transactions", "merchant_category", "nxd_decisions")
DERIVED_MODELS = ("classified_spend",)
PHYSICAL_MODELS = BASE_MODELS + DERIVED_MODELS


def _assert_measure_reconciles(source_rows, derived_total):
    expected = sum(Decimal(r["amount"]) for r in source_rows if r["kind"] != "transfer")
    if expected != derived_total:
        raise RuntimeError(f"{derived_total} != {expected}")
'''


# A closure that lands NOTHING itself: it carries an `ingest` the checker can
# run, exactly as a real closure does. The agent is entitled to leave no
# database behind — the skill's own dry-run writes one to a temp directory and
# then discards it — so the checker has to be able to produce one.
INGESTING_TRANSFORM_SRC = TRANSFORM_SRC + '''
import csv as _csv
from pathlib import Path as _Path

from nxd.core.context import DuckDbOutput  # noqa: F401
from nxd import data_product as _dp

CATEGORIES = {
    "AWS": "cogs", "Anthropic": "cogs", "OpenAI": "cogs",
    "Deel": "opex", "Figma": "opex", "Lufthansa": "opex",
    "Monzo": "opex", "WeWork": "opex",
}

NET_REFUNDS = __NET_REFUNDS__


@_dp.on_transform()
def ingest(duckdb, secrets):
    import duckdb as _duckdb

    src = _Path(secrets["csv_source"]) / "transactions" / "transactions.csv"
    rows = list(_csv.DictReader(src.open()))
    landed = []
    for r in rows:
        if r["kind"] == "transfer":
            continue
        if not NET_REFUNDS and r["kind"] == "refund":
            continue
        landed.append((r["txn_id"], CATEGORIES.get(r["merchant"], "needs_review"),
                       r["currency"], float(Decimal(r["amount"]))))

    # The unnetted variant deliberately skips its own reconciliation: that is
    # precisely the closure this scenario exists to catch — one whose numbers are
    # wrong and whose asserts did not stop it. Running the assert here would make
    # it fail as a broken transform instead of as a wrong-totals closure.
    if NET_REFUNDS:
        _assert_measure_reconciles(rows, sum(Decimal(str(r[3])) for r in landed))

    con = _duckdb.connect(duckdb.path)
    con.execute("CREATE TABLE classified_spend "
                "(txn_id VARCHAR, category VARCHAR, currency VARCHAR, net_amount DOUBLE)")
    con.executemany("INSERT INTO classified_spend VALUES (?, ?, ?, ?)", landed)
    con.close()
'''


def _write_ingesting_closure(root: Path, *, net_refunds: bool) -> None:
    """A closure that materializes on demand and lands no database of its own."""
    _write_closure(root)
    src = INGESTING_TRANSFORM_SRC.replace("__NET_REFUNDS__", str(net_refunds))
    (root / "transform" / "main.py").write_text(src, encoding="utf-8")
    # A real closure declares its ingest dependencies and expects the runtime to
    # provide them; `nxd` is the internal wheel that cannot be installed.
    (root / "requirements.txt").write_text(
        "nxd.data_product[spec]\nduckdb==1.5.4\n", encoding="utf-8"
    )


def _write_closure(root: Path) -> None:
    (root / "transform").mkdir(parents=True, exist_ok=True)
    (root / "transform" / "main.py").write_text(TRANSFORM_SRC, encoding="utf-8")
    for rel in ("spec.py", "models.py", "infra-profile.yaml", "requirements.txt"):
        (root / rel).write_text("# closure\n", encoding="utf-8")

    (root / "data" / "transactions").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        FIXTURES / "data" / "transactions.csv",
        root / "data" / "transactions" / "transactions.csv",
    )

    (root / "data" / "merchant_category").mkdir(parents=True, exist_ok=True)
    (root / "data" / "merchant_category" / "merchant_category.csv").write_text(
        "merchant,category\nAWS,cogs\nAnthropic,cogs\nOpenAI,cogs\n"
        "Deel,opex\nFigma,opex\nLufthansa,opex\nMonzo,opex\nWeWork,opex\n",
        encoding="utf-8",
    )

    # The ruling ledger is a landed model, and it must disclose the currency
    # stance: this closure declines to convert, so it records the missing rates.
    # Each row is classified on both axes — settled-or-not (status) and
    # authored-by (provenance) — because they are independent questions.
    (root / "data" / "nxd_decisions").mkdir(parents=True, exist_ok=True)
    (root / "data" / "nxd_decisions" / "nxd_decisions.csv").write_text(
        "decision_id,status,provenance,ruling,applies_to,detail\n"
        "d1,proposed,agent_authored,merchant-to-category mapping,"
        "merchant_category,classification over observed merchants\n"
        "d2,blocked,deferred,no exchange rate exists in the export,"
        "classified_spend,"
        "amounts stay in source currency; cross-currency totals are blocked "
        "until FX rates arrive\n",
        encoding="utf-8",
    )


def _land_totals(root: Path, *, net_refunds: bool) -> None:
    """Materialize the spend measure the checker reads.

    ``net_refunds=False`` is the failure this scenario exists to catch: the
    refund rows are dropped while their matching charges are kept, so every
    total is the charges-only figure truth.json names.
    """
    categories = {
        "AWS": "cogs", "Anthropic": "cogs", "OpenAI": "cogs",
        "Deel": "opex", "Figma": "opex", "Lufthansa": "opex",
        "Monzo": "opex", "WeWork": "opex",
    }
    rows = list(csv.DictReader((FIXTURES / "data" / "transactions.csv").open()))
    landed = []
    for r in rows:
        if r["kind"] == "transfer":
            continue
        if not net_refunds and r["kind"] == "refund":
            continue
        landed.append(
            (
                r["txn_id"],
                categories.get(r["merchant"], "needs_review"),
                r["currency"],
                float(Decimal(r["amount"])),
            )
        )
    con = duckdb.connect(str(root / "data.duckdb"))
    con.execute(
        "CREATE TABLE classified_spend "
        "(txn_id VARCHAR, category VARCHAR, currency VARCHAR, net_amount DOUBLE)"
    )
    con.executemany("INSERT INTO classified_spend VALUES (?, ?, ?, ?)", landed)
    con.close()


def _land_ruling(root: Path, ruling: dict[str, str]) -> None:
    """Overwrite the closure's landed merchant->category CSV with `ruling`."""
    (root / "data" / "merchant_category" / "merchant_category.csv").write_text(
        "merchant,category\n" + "".join(f"{m},{c}\n" for m, c in ruling.items()),
        encoding="utf-8",
    )


def _land_totals_under(root: Path, ruling: dict[str, str], *, net_refunds: bool = True) -> None:
    """Land a measure classified by `ruling`, which the closure also records."""
    _land_ruling(root, ruling)
    rows = list(csv.DictReader((FIXTURES / "data" / "transactions.csv").open()))
    landed = []
    for r in rows:
        if r["kind"] == "transfer":
            continue
        if not net_refunds and r["kind"] == "refund":
            continue
        landed.append(
            (
                r["txn_id"],
                ruling.get(r["merchant"], "needs_review"),
                r["currency"],
                float(Decimal(r["amount"])),
            )
        )
    con = duckdb.connect(str(root / "data.duckdb"))
    con.execute(
        "CREATE TABLE classified_spend "
        "(txn_id VARCHAR, category VARCHAR, currency VARCHAR, net_amount DOUBLE)"
    )
    con.executemany("INSERT INTO classified_spend VALUES (?, ?, ?, ?)", landed)
    con.close()


SEEDED_RULING = {
    "AWS": "cogs", "Anthropic": "cogs", "OpenAI": "cogs",
    "Deel": "opex", "Figma": "opex", "Lufthansa": "opex",
    "Monzo": "opex", "WeWork": "opex",
}


def _facts(ws: Path) -> list[str]:
    return [run.deterministic_check_fact(SCENARIO, ws, CHECK_CFG)]


def test_correct_closure_passes(tmp_path):
    _write_closure(tmp_path)
    _land_totals(tmp_path, net_refunds=True)

    facts = _facts(tmp_path)
    assert run.deterministic_check_passed(facts) is True
    assert run.deterministic_check_infrastructure_error(facts) is None


def test_unnetted_refunds_closure_fails_and_names_the_bug(tmp_path):
    """The gate must bite, and the detail must name WHICH total is wrong."""
    _write_closure(tmp_path)
    _land_totals(tmp_path, net_refunds=False)

    facts = _facts(tmp_path)
    assert run.deterministic_check_passed(facts) is False
    assert run.deterministic_check_infrastructure_error(facts) is None

    detail = run.deterministic_check_detail(facts)
    assert "totals:" in detail
    assert "charges-only" in detail


def test_defensible_ruling_is_graded_on_its_own_terms(tmp_path):
    """An uncovered merchant routed to `needs_review` must not fail the totals.

    The COGS/opex ruling exists in no column of the export and no user is
    available to confirm one, so it is a judgement rather than a fact. The
    scenario's own `unclassified-visible` check asks for uncovered merchants to
    land in an explicit bucket; grading totals against a mapping the closure was
    never shown punished exactly that. Monzo is a bank, and calling it
    unclassified is defensible.
    """
    _write_closure(tmp_path)
    _land_totals_under(tmp_path, dict(SEEDED_RULING, Monzo="needs_review"))

    facts = _facts(tmp_path)
    assert run.deterministic_check_passed(facts) is True
    assert run.deterministic_check_infrastructure_error(facts) is None


def test_ruling_freedom_does_not_excuse_unnetted_refunds(tmp_path):
    """Netting is wrong under EVERY ruling, so the gate must still bite.

    Guards the obvious way to defang this: if the expected totals follow the
    closure's ruling, a closure must not be able to escape the netting check by
    reclassifying. The charges-only diagnostic must also be recomputed under the
    closure's ruling rather than quoting the seeded figure.
    """
    _write_closure(tmp_path)
    _land_totals_under(
        tmp_path, dict(SEEDED_RULING, Monzo="needs_review"), net_refunds=False
    )

    facts = _facts(tmp_path)
    assert run.deterministic_check_passed(facts) is False

    detail = run.deterministic_check_detail(facts)
    assert "charges-only" in detail
    # The seeded opex charges-only figure includes Monzo; this ruling excludes
    # it, so quoting 354408.96 here would prove the fallback basis was used.
    assert "354408.96" not in detail


def test_measure_contradicting_its_own_ruling_fails(tmp_path):
    """Self-consistency is still enforced.

    A closure cannot dodge the gate by landing a ruling that disagrees with the
    measure it actually computed -- that is the loophole a ruling-derived basis
    would otherwise open.
    """
    _write_closure(tmp_path)
    # Measure classifies Anthropic as opex; the recorded ruling says cogs.
    _land_totals_under(tmp_path, dict(SEEDED_RULING, Anthropic="opex"))
    _land_ruling(tmp_path, SEEDED_RULING)

    facts = _facts(tmp_path)
    assert run.deterministic_check_passed(facts) is False


def test_closure_without_a_landed_database_is_still_graded(tmp_path):
    """No landed database must mean "materialize and grade", not "cannot check".

    A closure is entitled to leave no database behind: the skill's pre-handoff
    dry-run writes one to a temporary directory and discards it as scratch. Such
    a closure was previously unverifiable, so the totals gate — the one check no
    structural rule substitutes for — never ran on it.
    """
    _write_ingesting_closure(tmp_path, net_refunds=True)
    assert not list(tmp_path.glob("**/*.duckdb")), "test must start with no database"

    facts = _facts(tmp_path)
    assert run.deterministic_check_infrastructure_error(facts) is None
    assert run.deterministic_check_passed(facts) is True


def test_materialized_closure_with_wrong_numbers_still_fails(tmp_path):
    """Materializing must not become a way to pass: the numbers are still graded."""
    _write_ingesting_closure(tmp_path, net_refunds=False)
    assert not list(tmp_path.glob("**/*.duckdb"))

    facts = _facts(tmp_path)
    assert run.deterministic_check_passed(facts) is False
    assert run.deterministic_check_infrastructure_error(facts) is None

    detail = run.deterministic_check_detail(facts)
    assert "totals:" in detail
    assert "charges-only" in detail


def test_closure_dependencies_are_installed_except_the_internal_wheel(tmp_path):
    """The transform ingests through its declared deps, so they must be installed.

    A live run failed with ``ModuleNotFoundError: No module named 'dlt'`` because
    the transform ran on the bare checker interpreter. It has to run under the
    closure's own requirements — minus ``nxd``, which is an internal package on a
    private index that the harness stubs instead.
    """
    checker = importlib.util.spec_from_file_location(
        "check_derived_closure", FIXTURES / "check_derived_closure.py"
    )
    mod = importlib.util.module_from_spec(checker)
    checker.loader.exec_module(mod)

    (tmp_path / "requirements.txt").write_text(
        "nxd.data_product[spec]\n"
        "dlt[duckdb]==1.28.2\n"
        "duckdb==1.5.4\n"
        "# a comment\n"
        "\n"
        "pandas==2.3.3\n",
        encoding="utf-8",
    )
    assert mod.closure_requirements(tmp_path) == [
        "dlt[duckdb]==1.28.2",
        "duckdb==1.5.4",
        "pandas==2.3.3",
    ]


def test_unrunnable_closure_fails_rather_than_being_excused(tmp_path):
    """Unrunnable is not unchecked — a transform that cannot execute still fails."""
    _write_closure(tmp_path)
    (tmp_path / "transform" / "main.py").write_text(
        TRANSFORM_SRC + "\n\ndef ingest(duckdb, secrets):\n    raise RuntimeError('boom')\n",
        encoding="utf-8",
    )

    facts = _facts(tmp_path)
    assert run.deterministic_check_passed(facts) is False
    assert "no queryable database" in run.deterministic_check_detail(facts)


def test_missing_closure_fails_rather_than_passing_vacuously(tmp_path):
    facts = _facts(tmp_path)
    assert run.deterministic_check_passed(facts) is False


def test_missing_checker_is_infrastructure_not_agent_failure(tmp_path):
    facts = [run.deterministic_check_fact(SCENARIO, tmp_path, {"script": "nope.py"})]
    assert run.deterministic_check_passed(facts) is False
    assert "checker not found" in (run.deterministic_check_infrastructure_error(facts) or "")


def test_absent_fact_is_fail_closed():
    """A gate that never ran must never read as a pass."""
    assert run.deterministic_check_passed([]) is False
    assert run.deterministic_check_passed(["some unrelated fact"]) is False
    assert run.deterministic_check_passed([run.DETERMINISTIC_CHECK_PREFIX + "{bad json"]) is False


def test_scenario_declares_the_opt_in():
    """The wiring is inert unless the scenario opts in; assert it does."""
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    cfg = checks.get("deterministic_check")
    assert cfg, "derive-models-from-questions must declare deterministic_check"
    assert (FIXTURES / cfg["script"]).is_file()


def test_answer_key_stays_out_of_the_agent_workspace():
    """The checker and its truth file must remain runner-side."""
    assert "truth.json" in run.DERIVATION_RUNNER_SIDE_FIXTURES
    assert "check_derived_closure.py" in run.DERIVATION_RUNNER_SIDE_FIXTURES


def test_redaction_markers_use_a_private_file_and_are_cleaned_up(tmp_path, monkeypatch):
    captured = {}

    class Completed:
        returncode = 0
        stdout = "ALL CHECKS PASSED\n"
        stderr = ""

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        marker_path = Path(cmd[cmd.index("--secret-marker-file") + 1])
        trace_path = Path(cmd[cmd.index("--trace") + 1])
        captured["marker_path"] = marker_path
        captured["trace_path"] = trace_path
        assert marker_path.read_text(encoding="utf-8") == "opaque-synthetic-secret\n"
        assert stat.S_IMODE(marker_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(trace_path.stat().st_mode) == 0o600
        assert not any("opaque-synthetic-secret" in str(part) for part in cmd)
        return Completed()

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    facts = [
        run.deterministic_check_fact(
            SCENARIO,
            tmp_path,
            {"script": "check_derived_closure.py", "deps": [],
             "redaction_markers": ["opaque-synthetic-secret"], "wants_trace": True},
            trace="runner trace",
        )
    ]

    assert run.deterministic_check_passed(facts) is True
    assert not captured["marker_path"].exists()
    assert not captured["trace_path"].exists()


def test_non_list_redaction_markers_fail_closed(tmp_path):
    facts = [run.deterministic_check_fact(
        SCENARIO, tmp_path,
        {"script": "check_derived_closure.py", "redaction_markers": "secret"},
    )]
    assert run.deterministic_check_infrastructure_error(facts) == (
        "redaction_markers must be a list"
    )


def test_runner_authored_trace_source_fails_closed_until_stdio_harness_exists(tmp_path):
    facts = [
        run.deterministic_check_fact(
            SCENARIO, tmp_path,
            {"script": "check_derived_closure.py", "trace_source": "runner_mcp"},
            trace="nxd-desktop build_data_product",
        )
    ]

    assert run.deterministic_check_passed(facts) is False
    assert run.deterministic_check_infrastructure_error(facts) == (
        "runner-authored MCP trace source is unavailable"
    )


def test_unknown_trace_source_fails_closed(tmp_path):
    facts = [run.deterministic_check_fact(
        SCENARIO, tmp_path,
        {"script": "check_derived_closure.py", "trace_source": "typo"},
    )]
    assert run.deterministic_check_infrastructure_error(facts) == (
        "unknown trace source: 'typo'"
    )

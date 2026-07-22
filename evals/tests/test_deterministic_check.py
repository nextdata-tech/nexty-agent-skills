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
    (root / "data" / "nxd_decisions").mkdir(parents=True, exist_ok=True)
    (root / "data" / "nxd_decisions" / "nxd_decisions.csv").write_text(
        "decision_id,status,ruling,applies_to,detail\n"
        "d1,proposed,merchant-to-category mapping,merchant_category,"
        "classification over observed merchants\n"
        "d2,blocked,no exchange rate exists in the export,classified_spend,"
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

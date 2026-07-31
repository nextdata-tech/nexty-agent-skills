"""Exercise the public custom-contract checker with valid and broken closures."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path


CHECKER = (Path(__file__).parents[1] / "public" / "pocket-custom-contracts" /
           "fixtures" / "check_custom_contracts.py")
spec = importlib.util.spec_from_file_location("custom_contract_checker", CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

RUNNER = Path(__file__).parents[1] / "run.py"
runner_spec = importlib.util.spec_from_file_location("eval_runner_pocket_custom", RUNNER)
runner = importlib.util.module_from_spec(runner_spec)
sys.modules[runner_spec.name] = runner
sys.path.insert(0, str(RUNNER.parent))
try:
    runner_spec.loader.exec_module(runner)
finally:
    sys.path.remove(str(RUNNER.parent))

ASYNC_VERIFIER_ERROR = (
    "Pocket custom verifier must be synchronous; the runtime does not await "
    "async verifier functions"
)


def input_verifier_source(*, async_verifier=False, nonliteral_secret_fields=False,
                          literal_secret=False, mixed_decorated=False) -> str:
    prefix = "async def" if async_verifier else "def"
    nonliteral_fields = (
        "password_columns = ('password',)\n"
        "token_fields = []\n"
        "token = 0\n"
        if nonliteral_secret_fields else ""
    )
    fields = 'token = "literal-secret"\n' if literal_secret else nonliteral_fields
    extra = '''
@data_product.on_verify()
async def second_verify():
    bad = []
    if bad:
        return VerifyResult(VerifyResultEnum.FAILED, {"bad": bad})
    return VerifyResult(VerifyResultEnum.PASS, {})
''' if mixed_decorated else ""
    return f'''from nxd import data_product
from nxd.core.context import VerifyResult, VerifyResultEnum
{fields}@data_product.on_verify()
{prefix} verify():
    bad = []
    if bad:
        return VerifyResult(VerifyResultEnum.FAILED, {{"bad": bad}})
    return VerifyResult(VerifyResultEnum.PASS, {{}})
{extra}if __name__ == '__main__': data_product.verify()
'''


def write_closure(root: Path, *, duplicate=False, decorative=False) -> None:
    (root / "contracts" / "expectations").mkdir(parents=True)
    (root / "contracts" / "promises").mkdir(parents=True)
    (root / "data" / "orders").mkdir(parents=True)
    (root / "data" / "orders" / "orders.csv").write_text("line_id,order_id,currency\nl1,o1,EUR\n")
    (root / "csv-source-path").write_text("data\n")
    (root / "infra-profile.yaml").write_text("""apiVersion: infra.nextdata.com/v1
kind: Profile
metadata:
  name: desktop-local
spec:
  services:
    - name: duckdb
      driver: nxd:local/duckdb/storage:0.1.0
      attributes: []
    - name: python-compute
      driver: nxd:local/python/compute:0.1.0
      attributes: []
    - name: csv-source
      driver: nxd:local/file/storage:0.1.0
      attributes: []
""")
    promise_name = "accepted-currency" if duplicate else "order-total-reconciles"
    (root / "spec.py").write_text(f'''_csv = "/infra-profile/desktop-local#/services/csv-source"\n_compute = "/infra-profile/desktop-local#/services/python-compute"\n_duckdb = "/infra-profile/desktop-local#/services/duckdb"\norders = object()\nspec = (data_product()\n.input("orders", source_aligned_input().source(_csv).config({{"model_paths": {{"orders": "orders/orders.csv"}}}}).expectation(custom("accepted-currency").description("currency set").model(orders).verify(script("contracts/expectations/accepted.py").compute(_compute))))\n.output(data_product_output().promise(orders).promise(custom("{promise_name}").description("reconciliation").model(orders).verify(script("contracts/promises/reconciles.py").compute(_compute))).port("duckdb", storage(_duckdb))))\n''')
    input_verifier = '''import csv
from nxd import data_product
from nxd.core.context import VerifyResult, VerifyResultEnum
@data_product.on_verify()
def verify(source):
    with open(source.path_for("orders"), newline="") as handle:
        bad = [row["currency"] for row in csv.DictReader(handle) if row["currency"] not in {"EUR", "USD"}]
    if bad:
        return VerifyResult(VerifyResultEnum.FAILED, {"bad": bad})
    return VerifyResult(VerifyResultEnum.PASS, {})
if __name__ == '__main__': data_product.verify()
'''
    output_verifier = '''import duckdb
from nxd import data_product
from nxd.core.context import VerifyResult, VerifyResultEnum
@data_product.on_verify()
def verify(output):
    with duckdb.connect(output.path, read_only=True) as conn:
        bad = conn.execute(f"SELECT order_id FROM {output.full_table_name('orders')} GROUP BY order_id HAVING COUNT(DISTINCT order_total) != 1 OR MIN(order_total) != SUM(line_total)").fetchall()
    if bad:
        return VerifyResult(VerifyResultEnum.FAILED, {"bad": bad})
    return VerifyResult(VerifyResultEnum.PASS, {})
if __name__ == '__main__': data_product.verify()
'''
    (root / "contracts" / "expectations" / "accepted.py").write_text(input_verifier)
    (root / "contracts" / "promises" / "reconciles.py").write_text(output_verifier)
    if decorative:
        (root / "contracts" / "promises" / "extra.py").write_text(input_verifier)


def test_valid_closure_passes(tmp_path: Path) -> None:
    write_closure(tmp_path)
    assert checker.check(tmp_path) == []


def test_sync_no_arg_verifier_is_accepted_by_both_checkers(tmp_path: Path) -> None:
    write_closure(tmp_path)
    (tmp_path / "contracts" / "expectations" / "accepted.py").write_text(
        input_verifier_source()
    )
    assert checker.check(tmp_path) == []
    proc = complete_self_check(tmp_path / "full", no_arg_verifier=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_async_verifier_is_rejected_by_both_checkers(tmp_path: Path) -> None:
    write_closure(tmp_path)
    (tmp_path / "contracts" / "expectations" / "accepted.py").write_text(
        input_verifier_source(async_verifier=True)
    )
    assert ASYNC_VERIFIER_ERROR in checker.check(tmp_path)
    proc = complete_self_check(tmp_path / "full", async_verifier=True)
    assert proc.returncode != 0
    assert ASYNC_VERIFIER_ERROR in proc.stdout


def test_nonliteral_password_and_token_fields_are_accepted_by_both_checkers(tmp_path: Path) -> None:
    write_closure(tmp_path)
    (tmp_path / "contracts" / "expectations" / "accepted.py").write_text(
        input_verifier_source(nonliteral_secret_fields=True)
    )
    assert checker.check(tmp_path) == []
    proc = complete_self_check(tmp_path / "full", nonliteral_secret_fields=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_literal_secret_assignment_is_rejected_by_both_checkers(tmp_path: Path) -> None:
    write_closure(tmp_path)
    (tmp_path / "contracts" / "expectations" / "accepted.py").write_text(
        input_verifier_source(literal_secret=True)
    )
    assert any("secret-like assignment" in error for error in checker.check(tmp_path))
    proc = complete_self_check(tmp_path / "full", literal_secret=True)
    assert proc.returncode != 0
    assert "contains a literal secret-like assignment" in proc.stdout


def test_mixed_sync_and_async_verifiers_count_as_duplicates(tmp_path: Path) -> None:
    write_closure(tmp_path)
    (tmp_path / "contracts" / "expectations" / "accepted.py").write_text(
        input_verifier_source(mixed_decorated=True)
    )
    errors = checker.check(tmp_path)
    assert any(error.startswith("bad verifier") for error in errors)
    assert ASYNC_VERIFIER_ERROR in errors
    proc = complete_self_check(tmp_path / "full", mixed_decorated=True)
    assert proc.returncode != 0
    assert "needs exactly one @data_product.on_verify()" in proc.stdout
    assert ASYNC_VERIFIER_ERROR in proc.stdout


def test_hidden_staged_skill_specs_are_not_generated_artifacts(tmp_path: Path) -> None:
    write_closure(tmp_path / "data_product")
    hidden_spec = tmp_path / ".skills" / "reference" / "spec.py"
    hidden_spec.parent.mkdir(parents=True)
    hidden_spec.write_text("not_a_generated_closure = True\n")
    assert checker.check(tmp_path) == []


def test_pocket_custom_checker_stays_runner_side_but_input_fixtures_stage(
        tmp_path: Path) -> None:
    scenario = Path(__file__).parents[1] / "public" / "pocket-custom-contracts"
    workspace, _ = runner.build_workspace(
        tmp_path, runner.SkillSet("no_skills", "test", []), scenario,
    )
    fixtures = scenario / "fixtures"
    assert not (workspace / "check_custom_contracts.py").exists()
    for name in ("orders.csv", "models.py"):
        assert (workspace / name).read_bytes() == (fixtures / name).read_bytes()


def test_other_scenario_keeps_same_named_checker_fixture(tmp_path: Path) -> None:
    scenario = tmp_path / "another-contract-scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    checker_fixture = fixtures / "check_custom_contracts.py"
    checker_fixture.write_text("print('ordinary fixture')\n", encoding="utf-8")
    workspace, _ = runner.build_workspace(
        tmp_path / "build", runner.SkillSet("no_skills", "test", []), scenario,
    )
    assert (workspace / checker_fixture.name).read_bytes() == checker_fixture.read_bytes()


def test_duplicate_name_and_decorative_script_fail(tmp_path: Path) -> None:
    write_closure(tmp_path, duplicate=True, decorative=True)
    errors = checker.check(tmp_path)
    assert any("distinct custom names" in error for error in errors)
    assert any("decorative script" in error for error in errors)


def test_inert_verifier_fails(tmp_path: Path) -> None:
    write_closure(tmp_path)
    (tmp_path / "contracts" / "expectations" / "accepted.py").write_text(
        "from nxd import data_product\n@data_product.on_verify()\ndef verify(): ...\nif __name__ == '__main__': data_product.verify()\n"
    )
    assert any("bad verifier" in error for error in checker.check(tmp_path))


def test_literal_dead_verifier_branch_fails(tmp_path: Path) -> None:
    write_closure(tmp_path)
    verifier_path = tmp_path / "contracts" / "expectations" / "accepted.py"
    verifier_path.write_text(verifier_path.read_text().replace("if bad:", "if False:"))
    assert any("bad verifier" in error for error in checker.check(tmp_path))


def test_missing_verify_chains_and_scripts_fail(tmp_path: Path) -> None:
    """The checker must fail the precise adversarial removal mutation."""
    write_closure(tmp_path)
    spec_path = tmp_path / "spec.py"
    spec_path.write_text(
        spec_path.read_text()
        .replace('.verify(script("contracts/expectations/accepted.py").compute(_compute))', "")
        .replace('.verify(script("contracts/promises/reconciles.py").compute(_compute))', "")
    )
    (tmp_path / "contracts" / "expectations" / "accepted.py").unlink()
    (tmp_path / "contracts" / "promises" / "reconciles.py").unlink()
    errors = checker.check(tmp_path)
    assert any("exactly one verify" in error for error in errors)


def test_shared_script_escaping_path_and_bad_main_guard_fail(tmp_path: Path) -> None:
    write_closure(tmp_path)
    spec_path = tmp_path / "spec.py"
    spec_path.write_text(
        spec_path.read_text()
        .replace("contracts/promises/reconciles.py", "contracts/expectations/accepted.py")
        .replace('"orders": "orders/orders.csv"', '"orders": "../orders.csv"')
    )
    verifier_path = tmp_path / "contracts" / "expectations" / "accepted.py"
    verifier_path.write_text(verifier_path.read_text().replace(
        "if __name__ == '__main__': data_product.verify()", "data_product.verify()"
    ))
    errors = checker.check(tmp_path)
    assert any("unique verifier scripts" in error for error in errors)
    assert any("safe relative mapping" in error for error in errors)
    assert any("bad verifier" in error for error in errors)


def test_custom_model_path_must_exist_under_data(tmp_path: Path) -> None:
    write_closure(tmp_path)
    spec_path = tmp_path / "spec.py"
    spec_path.write_text(spec_path.read_text().replace("orders/orders.csv", "orders/missing.csv"))
    assert any("resolve under csv-source-path" in error for error in checker.check(tmp_path))


def test_csv_source_path_must_be_contained_relative_export_root(tmp_path: Path) -> None:
    write_closure(tmp_path)
    (tmp_path / "csv-source-path").write_text("/tmp\n")
    assert any("csv-source-path" in error for error in checker.check(tmp_path))


def test_csv_source_path_is_required(tmp_path: Path) -> None:
    write_closure(tmp_path)
    (tmp_path / "csv-source-path").unlink()
    assert any("csv-source-path" in error for error in checker.check(tmp_path))


def test_public_checker_rejects_labeled_csv_input_service(tmp_path: Path) -> None:
    write_closure(tmp_path)
    spec_path = tmp_path / "spec.py"
    spec_path.write_text(spec_path.read_text().replace(
        "/services/csv-source", "/services/csv-source-orders"
    ))
    assert any("unlabeled desktop-local csv-source" in error
               for error in checker.check(tmp_path))


def swap_duckdb_and_compute_drivers(profile_path: Path) -> None:
    profile_path.write_text(profile_path.read_text()
                            .replace("nxd:local/duckdb/storage:0.1.0", "TEMP_DRIVER")
                            .replace("nxd:local/python/compute:0.1.0", "nxd:local/duckdb/storage:0.1.0")
                            .replace("TEMP_DRIVER", "nxd:local/python/compute:0.1.0"))


def test_infra_service_drivers_must_bind_to_their_service_names(tmp_path: Path) -> None:
    write_closure(tmp_path)
    swap_duckdb_and_compute_drivers(tmp_path / "infra-profile.yaml")
    assert any("desktop-local" in error for error in checker.check(tmp_path))


def test_custom_output_requires_ordinary_promise_on_duckdb_port(tmp_path: Path) -> None:
    write_closure(tmp_path)
    spec_path = tmp_path / "spec.py"
    spec_path.write_text(spec_path.read_text().replace('"duckdb", storage(_duckdb)', '"s3", storage("s3")'))
    errors = checker.check(tmp_path)
    assert any("DuckDB output port" in error for error in errors)


def test_custom_output_requires_duckdb_storage_service(tmp_path: Path) -> None:
    write_closure(tmp_path)
    spec_path = tmp_path / "spec.py"
    spec_path.write_text(spec_path.read_text().replace("storage(_duckdb)", "storage(_csv)"))
    assert any("DuckDB output port" in error for error in checker.check(tmp_path))


def test_generated_verifiers_execute_valid_and_failure_fixtures(tmp_path: Path, monkeypatch) -> None:
    """Exercise generated scripts, not merely their AST shape."""
    import duckdb
    write_closure(tmp_path)
    class Enum: PASS = "PASS"; FAILED = "FAILED"
    class Result:
        def __init__(self, result, context): self.result, self.context = result, context
    dp = types.SimpleNamespace(on_verify=lambda: lambda fn: fn, verify=lambda: None)
    monkeypatch.setitem(sys.modules, "nxd", types.SimpleNamespace(data_product=dp))
    monkeypatch.setitem(sys.modules, "nxd.core", types.ModuleType("nxd.core"))
    ctx = types.ModuleType("nxd.core.context"); ctx.VerifyResult = Result; ctx.VerifyResultEnum = Enum
    monkeypatch.setitem(sys.modules, "nxd.core.context", ctx)
    def load(path):
        spec = importlib.util.spec_from_file_location(path.stem, path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
    inp = load(tmp_path / "contracts" / "expectations" / "accepted.py")
    out = load(tmp_path / "contracts" / "promises" / "reconciles.py")
    csv_path = tmp_path / "orders.csv"; csv_path.write_text("line_id,order_id,currency\nl1,o1,EUR\nl2,o2,USD\n")
    source = types.SimpleNamespace(path_for=lambda model: str(csv_path))
    assert inp.verify(source).result == Enum.PASS
    csv_path.write_text("line_id,order_id,currency\nl1,o1,GBP\n")
    assert inp.verify(source).result == Enum.FAILED
    db_path = tmp_path / "out.duckdb"; conn = duckdb.connect(db_path)
    conn.execute("create table orders(line_id varchar, order_id varchar, order_total decimal, line_total decimal)")
    conn.execute("insert into orders values ('l1', 'o1', 20, 10), ('l2', 'o1', 20, 10)"); conn.close()
    output = types.SimpleNamespace(path=str(db_path), full_table_name=lambda model: "main.orders")
    assert out.verify(output).result == Enum.PASS  # valid multiline order
    conn = duckdb.connect(db_path); conn.execute("delete from orders"); conn.execute("insert into orders values ('l1', 'o1', 20, 9), ('l2', 'o1', 20, 10)"); conn.close()
    assert out.verify(output).result == Enum.FAILED


def complete_self_check(tmp_path: Path, *, dead_verifier=False, absolute_model_path=False,
                        nested_main_guard=False, wrong_duckdb_storage=False, missing_model_path=False,
                        bad_csv_source_path=False, missing_csv_source_path=False, swapped_drivers=False,
                        wrong_profile_name=False, nested_escape=False,
                        without_input_custom=False, output_only=False,
                        multiple_inputs=False, labeled_input=False,
                        wrong_csv_driver=False, no_arg_verifier=False,
                        async_verifier=False, nonliteral_secret_fields=False,
                        literal_secret=False,
                        mixed_decorated=False):
    """Phase A must not mistake verifier script paths for transform executors."""
    write_closure(tmp_path)
    (tmp_path / "CONTEXT.md").write_text("# context\n")
    (tmp_path / "data" / "orders").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "orders" / "orders.csv").write_text(
        "line_id,order_id,currency,order_total,line_total\no-1-1,o-1,EUR,10.00,10.00\n"
    )
    (tmp_path / "models.py").write_text((CHECKER.parent / "models.py").read_text())
    # The checker parses, but does not import, this spec. The scripts are nested
    # custom verifiers and must not be constrained to transform/main.py.
    (tmp_path / "spec.py").write_text('''from nxd.spec import data_product, script, custom, source_aligned_input, data_product_output, storage, simple_sensor\nfrom models import orders\n_csv = "/infra-profile/desktop-local#/services/csv-source"\n_compute = "/infra-profile/desktop-local#/services/python-compute"\n_duckdb = "/infra-profile/desktop-local#/services/duckdb"\nspec = (\n    data_product(name="orders", infra_profile="desktop-local")\n    .transform(script("transform/main.py").compute(_compute).secrets([_csv]).when(simple_sensor(startup=False, when="any")))\n    .input("orders", source_aligned_input().source(_csv).config({"model_paths": {"orders": "orders/orders.csv"}}).expectation(custom("accepted-currency").description("currency set").model(orders).verify(script("contracts/expectations/accepted.py").compute(_compute))))\n    .output(data_product_output().promise(orders).promise(custom("order-total-reconciles").description("reconcile").model(orders).verify(script("contracts/promises/reconciles.py").compute(_compute))).port("duckdb", storage(_duckdb)))\n)\n''')
    if labeled_input:
        spec_path = tmp_path / "spec.py"
        spec_path.write_text(spec_path.read_text().replace(
            "/services/csv-source", "/services/csv-source-orders"
        ))
    if multiple_inputs:
        spec_path = tmp_path / "spec.py"
        spec_path.write_text(spec_path.read_text().replace(
            '    .output(data_product_output()',
            '    .input("orders-again", source_aligned_input().source(_csv).config({"model_paths": {"orders": "orders/orders.csv"}}))\n'
            '    .output(data_product_output()',
        ))
    if without_input_custom:
        spec_path = tmp_path / "spec.py"
        spec_path.write_text(spec_path.read_text().replace(
            '.expectation(custom("accepted-currency").description("currency set").model(orders).verify(script("contracts/expectations/accepted.py").compute(_compute)))',
            "",
        ))
        (tmp_path / "contracts" / "expectations" / "accepted.py").unlink()
    if output_only:
        spec_path = tmp_path / "spec.py"
        spec_path.write_text('''from nxd.spec import data_product, script, custom, data_product_output, storage, simple_sensor
from models import orders
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"
spec = (
    data_product(name="orders", infra_profile="desktop-local")
    .transform(script("transform/main.py").compute(_compute).secrets([]).when(simple_sensor(startup=False, when="any")))
    .output(data_product_output().promise(orders).promise(custom("order-total-reconciles").description("reconcile").model(orders).verify(script("contracts/promises/reconciles.py").compute(_compute))).port("duckdb", storage(_duckdb)))
)
''')
        (tmp_path / "contracts" / "expectations" / "accepted.py").unlink()
        (tmp_path / "csv-source-path").unlink()
        profile_path = tmp_path / "infra-profile.yaml"
        profile_path.write_text(profile_path.read_text().replace(
            "    - name: csv-source\n"
            "      driver: nxd:local/file/storage:0.1.0\n"
            "      attributes: []\n",
            "",
        ))
    if wrong_csv_driver:
        profile_path = tmp_path / "infra-profile.yaml"
        profile_path.write_text(profile_path.read_text().replace(
            "nxd:local/file/storage:0.1.0",
            "nxd:local/duckdb/storage:0.1.0",
        ))
    (tmp_path / "transform").mkdir()
    (tmp_path / "transform" / "main.py").write_text('''from pathlib import Path\nBASE_MODELS = ("orders",)\nPHYSICAL_MODELS = ("orders",)\ndef ingest(duckdb, secrets):\n    import duckdb as db\n    con = db.connect(duckdb.path); con.execute("create table orders (order_id varchar, currency varchar)"); con.execute("insert into orders values ('o-1', 'EUR')"); con.close(); Path(duckdb.path).parent.joinpath(".transform-complete").touch()\n''')
    if dead_verifier:
        (tmp_path / "contracts" / "expectations" / "accepted.py").write_text('''from nxd import data_product
from nxd.core.context import VerifyResult, VerifyResultEnum
@data_product.on_verify()
def verify(source):
    if False:
        return VerifyResult(VerifyResultEnum.FAILED, {})
    return VerifyResult(VerifyResultEnum.PASS, {})
if __name__ == "__main__":
    data_product.verify()
''')
    if (no_arg_verifier or async_verifier or nonliteral_secret_fields or
            literal_secret or mixed_decorated):
        (tmp_path / "contracts" / "expectations" / "accepted.py").write_text(
            input_verifier_source(
                async_verifier=async_verifier,
                nonliteral_secret_fields=nonliteral_secret_fields,
                literal_secret=literal_secret,
                mixed_decorated=mixed_decorated,
            )
        )
    if absolute_model_path:
        spec_path = tmp_path / "spec.py"
        spec_path.write_text(spec_path.read_text().replace("orders/orders.csv", "/tmp/orders.csv"))
    if nested_main_guard:
        verifier_path = tmp_path / "contracts" / "expectations" / "accepted.py"
        verifier_path.write_text(verifier_path.read_text().replace(
            "if __name__ == '__main__': data_product.verify()",
            "def never():\n    if __name__ == '__main__': data_product.verify()",
        ))
    if wrong_duckdb_storage:
        spec_path = tmp_path / "spec.py"
        spec_path.write_text(spec_path.read_text().replace("storage(_duckdb)", "storage(_csv)"))
    if missing_model_path:
        spec_path = tmp_path / "spec.py"
        spec_path.write_text(spec_path.read_text().replace("orders/orders.csv", "orders/missing.csv"))
    if bad_csv_source_path:
        (tmp_path / "csv-source-path").write_text("/tmp\n")
    if missing_csv_source_path:
        (tmp_path / "csv-source-path").unlink()
    if swapped_drivers:
        swap_duckdb_and_compute_drivers(tmp_path / "infra-profile.yaml")
    if wrong_profile_name:
        profile_path = tmp_path / "infra-profile.yaml"
        profile_path.write_text(profile_path.read_text().replace("name: desktop-local", "name: wrong-profile"))
    if nested_escape:
        verifier_path = tmp_path / "contracts" / "expectations" / "accepted.py"
        verifier_path.write_text(verifier_path.read_text() + "\n# See ../../POLICY.md\n")
    return subprocess.run([sys.executable, str(Path(__file__).parents[2] / "scripts" / "self_check.py")], cwd=tmp_path, text=True, capture_output=True)


def test_complete_self_check_accepts_exact_unlabeled_source_aligned_input(tmp_path: Path) -> None:
    """The runtime-valid `_csv` source wiring must pass end to end."""
    proc = complete_self_check(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELF-CHECK OK" in proc.stdout


def test_complete_self_check_rejects_literal_dead_verifier_branch(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, dead_verifier=True)
    assert proc.returncode != 0
    assert "dead branches" in proc.stdout


def test_complete_self_check_rejects_absolute_custom_model_path(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, absolute_model_path=True)
    assert proc.returncode != 0
    assert "safe relative path" in proc.stdout


def test_complete_self_check_rejects_nested_main_guard(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, nested_main_guard=True)
    assert proc.returncode != 0
    assert "main guard" in proc.stdout


def test_complete_self_check_rejects_csv_storage_on_duckdb_port(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, wrong_duckdb_storage=True)
    assert proc.returncode != 0
    assert "DuckDB output declaration" in proc.stdout


def test_complete_self_check_rejects_missing_custom_model_csv(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, missing_model_path=True)
    assert proc.returncode != 0
    assert "existing csv-source-path/*.csv file" in proc.stdout


def test_complete_self_check_rejects_absolute_csv_source_path(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, bad_csv_source_path=True)
    assert proc.returncode != 0
    assert "csv-source-path" in proc.stdout


def test_complete_self_check_requires_csv_source_path(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, missing_csv_source_path=True)
    assert proc.returncode != 0
    assert "csv-source-path" in proc.stdout


def test_complete_self_check_rejects_swapped_service_drivers(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, swapped_drivers=True)
    assert proc.returncode != 0
    assert "duckdb must use" in proc.stdout


def test_complete_self_check_requires_matching_profile_metadata_name(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, wrong_profile_name=True)
    assert proc.returncode != 0
    assert "metadata.name must be desktop-local" in proc.stdout


def test_complete_self_check_rejects_labeled_source_aligned_input(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, labeled_input=True)
    assert proc.returncode != 0
    assert "labeled CSV services are transform-only" in proc.stdout


def test_complete_self_check_accepts_multiple_inputs_sharing_unlabeled_csv(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, multiple_inputs=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELF-CHECK OK" in proc.stdout


def test_complete_self_check_accepts_output_only_promise_without_csv_artifacts(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, output_only=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELF-CHECK OK" in proc.stdout


def test_complete_self_check_rejects_wrong_csv_driver_for_non_custom_input(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, without_input_custom=True, wrong_csv_driver=True)
    assert proc.returncode != 0
    assert "csv-source must use nxd:local/file/storage:0.1.0" in proc.stdout


def test_complete_self_check_scans_nested_verifiers_for_escape_paths(tmp_path: Path) -> None:
    proc = complete_self_check(tmp_path, nested_escape=True)
    assert proc.returncode != 0
    assert "contracts/expectations/accepted.py: references '../../POLICY.md'" in proc.stdout

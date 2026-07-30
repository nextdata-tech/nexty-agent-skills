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
    (root / "spec.py").write_text(f'''_csv = "csv-source"\n_compute = "python-compute"\n_duckdb = "duckdb"\norders = object()\nspec = (data_product()\n.input("orders", source_aligned_input().source(_csv).config({{"model_paths": {{"orders": "orders/orders.csv"}}}}).expectation(custom("accepted-currency").description("currency set").model(orders).verify(script("contracts/expectations/accepted.py").compute(_compute))))\n.output(data_product_output().promise(orders).promise(custom("{promise_name}").description("reconciliation").model(orders).verify(script("contracts/promises/reconciles.py").compute(_compute))).port("duckdb", storage(_duckdb))))\n''')
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


def test_hidden_staged_skill_specs_are_not_generated_artifacts(tmp_path: Path) -> None:
    write_closure(tmp_path / "data_product")
    hidden_spec = tmp_path / ".skills" / "reference" / "spec.py"
    hidden_spec.parent.mkdir(parents=True)
    hidden_spec.write_text("not_a_generated_closure = True\n")
    assert checker.check(tmp_path) == []


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
                        wrong_profile_name=False):
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
    return subprocess.run([sys.executable, str(Path(__file__).parents[2] / "scripts" / "self_check.py")], cwd=tmp_path, text=True, capture_output=True)


def test_complete_self_check_accepts_custom_verifier_scripts(tmp_path: Path) -> None:
    """Phase A must not mistake verifier script paths for transform executors."""
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

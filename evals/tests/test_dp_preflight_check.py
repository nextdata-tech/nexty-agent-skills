"""The generated-code preflight must catch what `nxd validate` structurally cannot.

`nxd validate` imports a data product bundle and resolves its infra-profile
services. It never executes a transform, never executes a contract, and never
installs the package. So four faults validate clean and fail later, or worse,
never fail and silently assert nothing:

  flat-layout   several shipped top-level modules with no packaging guard; the
                failure surfaces at `nxd launch`, which no public scenario runs
  verify-bind   a contract parameter not named after a declared service; the
                failure surfaces when the contract runs
  verify-weak   a contract that can only return PASS; this never surfaces at all,
                which is what makes it the worst of the four
  version-drift spec.py and pyproject.toml disagreeing on the version
  surface       access modifiers and executor configs nobody asked for, which
                change deployed behaviour and never fail anything
  contract-driver a contract wired with the contract-executor driver rather than
                the storage driver, which hands it a bare Context and breaks every
                attribute access the moment the body does real work

The `surface` check earned its place empirically: it was written as prose first,
and the same generation shipped `.managed_access()` and an invented executor
config twice running. The four checks that were executable were all fixed on the
second pass; the one that was prose was not.

The skill described the first in prose and an agent shipped a product without it
anyway, so the rules are executable now. These tests pin the checker's behaviour
against a fixture pair: one product satisfying every rule, one tripping all four.

Carrying test for entries/2026-09-16-contract-binding-and-flat-layout-guards.md.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "src" / "nxd-build-data-product" / "scripts" / "preflight_check.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dp_preflight"
GUARDED = FIXTURES / "guarded"
UNGUARDED = FIXTURES / "unguarded"


def _load_checker():
    spec = importlib.util.spec_from_file_location("dp_preflight_check", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["dp_preflight_check"] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _checks(root: Path) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for finding in checker.run_checks(root):
        grouped.setdefault(finding.check, []).append(finding)
    return grouped


def test_checker_ships_with_the_skill():
    """The skill is distributed as a directory; the script must travel with it."""
    assert CHECKER.is_file(), f"preflight checker missing at {CHECKER}"


def test_guarded_product_is_clean():
    assert checker.run_checks(GUARDED) == []


@pytest.mark.parametrize(
    "check",
    ["flat-layout", "verify-bind", "verify-weak", "version-drift", "surface", "contract-driver"],
)
def test_unguarded_product_trips_every_check(check):
    assert check in _checks(UNGUARDED), f"{check} not reported on the unguarded fixture"


def test_flat_layout_accepts_either_guard(tmp_path):
    """py-modules and a root __init__.py are both valid; one is required."""
    for name in ("spec", "models", "transform"):
        (tmp_path / f"{name}.py").write_text("# module\n")

    assert _named(checker.check_flat_layout(tmp_path)) == ["flat-layout"]

    (tmp_path / "__init__.py").write_text("")
    assert checker.check_flat_layout(tmp_path) == []

    (tmp_path / "__init__.py").unlink()
    (tmp_path / "pyproject.toml").write_text(
        '[tool.setuptools]\npy-modules = ["spec", "models", "transform"]\n'
    )
    assert checker.check_flat_layout(tmp_path) == []


def test_flat_layout_catches_an_incomplete_py_modules_list(tmp_path):
    """A partial list is the failure mode a glance at pyproject.toml misses."""
    for name in ("spec", "models", "transform"):
        (tmp_path / f"{name}.py").write_text("# module\n")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.setuptools]\npy-modules = ["spec", "models"]\n'
    )

    findings = checker.check_flat_layout(tmp_path)
    assert _named(findings) == ["flat-layout"]
    assert "transform" in findings[0].message


def test_a_single_shipped_module_needs_no_guard(tmp_path):
    (tmp_path / "spec.py").write_text("# module\n")
    assert checker.check_flat_layout(tmp_path) == []


def test_nxdignored_modules_do_not_count_as_shipped(tmp_path):
    """local_test.py never reaches the platform, so it cannot break the layout."""
    (tmp_path / "spec.py").write_text("# module\n")
    (tmp_path / "local_test.py").write_text("# local only\n")
    (tmp_path / ".nxdignore").write_text("local_test.py\n")

    assert checker.shipped_top_level_modules(tmp_path) == ["spec"]
    assert checker.check_flat_layout(tmp_path) == []


def test_verify_bind_accepts_the_service_name_and_rejects_a_generic_one(tmp_path):
    (tmp_path / "spec.py").write_text(
        '.service(service_name="adls", driver="nxd:kubernetes/contract:1.0.0")\n'
    )
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    body = "    return VerifyResult(VerifyResultEnum.FAILED, {})\n"

    (contracts / "good.py").write_text(f"def verify(adls, models):\n{body}")
    assert checker.check_contracts(tmp_path) == []

    (contracts / "good.py").unlink()
    (contracts / "bad.py").write_text(f"def verify(input, models):\n{body}")
    findings = checker.check_contracts(tmp_path)
    assert _named(findings) == ["verify-bind"]
    assert "'input'" in findings[0].message
    assert "adls" in findings[0].message


def test_verify_bind_normalises_hyphens_to_underscores(tmp_path):
    """Spec names carry hyphens; Python signatures cannot."""
    (tmp_path / "spec.py").write_text('.input("pos-raw-data", source_aligned_input())\n')
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "c.py").write_text(
        "def verify(pos_raw_data, models):\n    return VerifyResult(VerifyResultEnum.FAILED, {})\n"
    )

    assert checker.check_contracts(tmp_path) == []


def test_verify_weak_is_reported_even_when_binding_is_correct(tmp_path):
    """The two contract faults are independent; a well-bound stub is still a stub."""
    (tmp_path / "spec.py").write_text('.service(service_name="adls", driver="d")\n')
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "stub.py").write_text(
        "def verify(adls, models):\n    return VerifyResult(VerifyResultEnum.PASS, {})\n"
    )

    assert _named(checker.check_contracts(tmp_path)) == ["verify-weak"]


def test_version_drift_is_a_warning_not_an_error(tmp_path):
    """Drift is worth reporting but must not block a hand-off on its own."""
    (tmp_path / "spec.py").write_text('version="1.0.0-dev",\n')
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')

    findings = checker.check_version_coherence(tmp_path)
    assert _named(findings) == ["version-drift"]
    assert findings[0].level == checker.WARN


def test_exit_code_is_driven_by_errors_not_warnings(tmp_path, capsys):
    """A warning-only product still hands off cleanly."""
    (tmp_path / "spec.py").write_text('version="1.0.0-dev",\n')
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')

    assert checker.main([str(tmp_path)]) == 0
    assert checker.main([str(UNGUARDED)]) == 1
    assert checker.main([str(GUARDED)]) == 0


def test_surface_flags_an_unjustified_access_modifier(tmp_path):
    (tmp_path / "spec.py").write_text("storage(ADLS).managed_access()\n")

    findings = checker.check_unrequested_surface(tmp_path)
    assert _named(findings) == ["surface"]
    assert findings[0].level == checker.WARN
    assert "managed_access" in findings[0].message


def test_surface_accepts_a_modifier_the_readme_justifies(tmp_path):
    """The check asks for a written rationale, not for the modifier's removal."""
    (tmp_path / "spec.py").write_text("storage(ADLS).managed_access()\n")
    (tmp_path / "README.md").write_text(
        "The port uses `managed_access()` because the consumer team holds its own grants.\n"
    )

    assert checker.check_unrequested_surface(tmp_path) == []


def test_surface_tells_storage_configs_from_executor_configs(tmp_path):
    """Storage configs are calls; executor configs are bare names. Only the latter is surface."""
    (tmp_path / "spec.py").write_text(
        "storage(ADLS).config(adls_config(file_type=SupportedFormat.CSV))\n"
    )
    assert checker.check_unrequested_surface(tmp_path) == []

    (tmp_path / "spec.py").write_text("script('t.py').config(k8s_executor_config)\n")
    findings = checker.check_unrequested_surface(tmp_path)
    assert _named(findings) == ["surface"]
    assert "k8s_executor_config" in findings[0].message


def test_surface_findings_do_not_fail_the_run(tmp_path, capsys):
    """Intent is not mechanically knowable, so surface warns and never blocks."""
    (tmp_path / "spec.py").write_text("storage(ADLS).managed_access()\n")

    assert checker.main([str(tmp_path)]) == 0


def test_contract_driver_rejects_the_executor_driver(tmp_path):
    (tmp_path / "spec.py").write_text(
        '.service(service_name="adls", driver="nxd:kubernetes/contract:1.0.0")\n'
    )
    findings = checker.check_contract_driver(tmp_path)
    assert _named(findings) == ["contract-driver"]
    assert findings[0].level == checker.ERROR


def test_contract_driver_accepts_a_storage_driver(tmp_path):
    (tmp_path / "spec.py").write_text('.service(service_name="adls", driver="nxd:adls:2.0.0")\n')
    assert checker.check_contract_driver(tmp_path) == []


def _named(findings) -> list[str]:
    return [finding.check for finding in findings]

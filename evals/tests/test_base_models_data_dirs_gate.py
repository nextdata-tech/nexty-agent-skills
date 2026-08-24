"""Phase A's ``data/``-directory comparison must respect the connector type.

``BASE_MODELS == data/ dirs`` is the right invariant for a csv-source or
file-source closure, whose every base model is exported to ``data/``. It is
wrong for an api-source or db-source closure: those base models are fetched over
the network and correctly have no directory, while the closure may still carry
``data/`` for reference data it authored itself.

That combination is not exotic. ``reference/api-source.md`` § "Landed reference
data in an API closure" instructs the author to write ``data/<name>/<name>.csv``
for exactly this, and the pack requires every ruling to land as data, so a
closure recording one carries ``data/nxd_decisions/``. Equality therefore fired
on **every correct api-source closure** — and a gate that fires on every correct
closure gets worked around rather than obeyed.

These tests pin both halves: the false positive stays fixed, and the real
finding a directory naming no base model represents still fires.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]
SELF_CHECK = EVALS_DIR.parent / "src" / "nxd-run-job-loop" / "scripts" / "self_check.py"

CODE = "struct.base_models_vs_data_dirs"

CSV = "/infra-profile/desktop-local#/services/csv-source"
FILE = "/infra-profile/desktop-local#/services/file-source"
API = "/infra-profile/desktop-local#/services/api-source"
API_LABELLED = "/infra-profile/desktop-local#/services/api-source-github"
DB_LABELLED = "/infra-profile/desktop-local#/services/db-source-orders"

MODELS_PY = '''\
from nxd.spec import dimension, field, primary_key, semantic_model
from nxd.spec.data_types import string

m = semantic_model("m").description("A model.").schema({
    "k": field(string(), primary_key(), dimension(name="m_k", description="Key.")),
})
'''


def _spec_py(service_ref: str) -> str:
    return (
        'from nxd.spec import data_product, data_product_output, script, storage\n'
        'from models import m\n'
        f'_src = "{service_ref}"\n'
        '_compute = "/infra-profile/desktop-local#/services/python-compute"\n'
        '_duckdb = "/infra-profile/desktop-local#/services/duckdb"\n'
        '_output = data_product_output().promise(m).port("duckdb", storage(_duckdb))\n'
        'spec = (data_product(name="d", domain="desktop.local", version="0.0.1",\n'
        '                     infra_profile="desktop-local")\n'
        '        .transform(script("transform/main.py").compute(_compute).secrets([_src]))\n'
        '        .output(_output))\n'
    )


def _transform_py(base_models: tuple[str, ...]) -> str:
    listed = ", ".join(f'"{name}"' for name in base_models)
    trailing = "," if len(base_models) == 1 else ""
    return (
        "import dlt\n"
        "from nxd import data_product\n"
        "from nxd.core.context import DuckDbOutput\n"
        f"BASE_MODELS = ({listed}{trailing})\n"
        f"PHYSICAL_MODELS = ({listed}{trailing})\n"
        "@data_product.on_transform()\n"
        "def ingest(duckdb: DuckDbOutput, secrets: dict) -> None:\n"
        "    pass\n"
    )


def _closure(tmp_path: Path, *, service_ref: str,
             base_models: tuple[str, ...],
             data_dirs: tuple[str, ...]) -> Path:
    root = tmp_path / "closure"
    (root / "transform").mkdir(parents=True)
    (root / "models.py").write_text(MODELS_PY, encoding="utf-8")
    (root / "spec.py").write_text(_spec_py(service_ref), encoding="utf-8")
    (root / "transform" / "main.py").write_text(_transform_py(base_models),
                                                encoding="utf-8")
    for name in data_dirs:
        d = root / "data" / name
        d.mkdir(parents=True)
        (d / f"{name}.csv").write_text("k\n1\n", encoding="utf-8")
    shutil.copyfile(SELF_CHECK, root / "self_check.py")
    return root


def _codes(closure: Path) -> set[str]:
    proc = subprocess.run([sys.executable, "self_check.py", "--json"],
                          cwd=closure, capture_output=True, text=True)
    report = json.loads(proc.stdout)
    return {d["code"] for d in report["diagnostics"]}


# --- the false positive, which is the whole point of the change ---------------

def test_api_source_closure_landing_reference_data_is_not_a_finding(tmp_path):
    """The shape reference/api-source.md tells the author to write."""
    closure = _closure(
        tmp_path, service_ref=API,
        base_models=("issues_landed", "nxd_decisions"),   # issues fetched
        data_dirs=("nxd_decisions",),                     # only the ruling lands
    )
    assert CODE not in _codes(closure)


def test_labelled_api_source_is_recognised(tmp_path):
    """Labelled instances (api-source-github) declare the same kind."""
    closure = _closure(tmp_path, service_ref=API_LABELLED,
                       base_models=("issues_landed", "nxd_decisions"),
                       data_dirs=("nxd_decisions",))
    assert CODE not in _codes(closure)


def test_labelled_db_source_is_recognised(tmp_path):
    closure = _closure(tmp_path, service_ref=DB_LABELLED,
                       base_models=("orders_landed", "nxd_decisions"),
                       data_dirs=("nxd_decisions",))
    assert CODE not in _codes(closure)


# --- what must STILL fire -----------------------------------------------------

def test_api_source_directory_naming_no_base_model_still_fires(tmp_path):
    """Containment, not silence: a directory that lands nothing is a finding."""
    closure = _closure(tmp_path, service_ref=API,
                       base_models=("issues_landed", "nxd_decisions"),
                       data_dirs=("nxd_decisions", "stray"))
    assert CODE in _codes(closure)


def test_csv_source_keeps_equality(tmp_path):
    """Every csv-source base model is exported; a missing directory is a bug."""
    closure = _closure(tmp_path, service_ref=CSV,
                       base_models=("a", "b"),
                       data_dirs=("a",))
    assert CODE in _codes(closure)


def test_file_source_keeps_equality(tmp_path):
    closure = _closure(tmp_path, service_ref=FILE,
                       base_models=("a", "b"),
                       data_dirs=("a",))
    assert CODE in _codes(closure)


def test_csv_source_matching_exactly_is_clean(tmp_path):
    closure = _closure(tmp_path, service_ref=CSV,
                       base_models=("a",), data_dirs=("a",))
    assert CODE not in _codes(closure)

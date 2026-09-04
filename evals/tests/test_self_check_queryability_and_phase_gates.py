"""Three checks that shift a silent failure left, into the offline self-check.

Each one was found by a cleanroom reproduction — rebuilding a data product from
`dp-blueprint.md` alone — where it cost either a wrong answer or a full closure
before anything reported it.

**`runtime.dry_run_not_runnable`.** A db-source/api-source closure reads its
connection out of `secrets`, which the offline harness cannot supply, so Phase B
raises before the transform does anything. `reference/api-source.md` already said
that is expected. What it did not say is that failing Phase B also SKIPS Phases
C, D and E — the closure-record, policy-boundary and reach-gate checks. The
cleanroom run lost all three to that expected KeyError and carried a missing
contract wiring and a hardcoded policy value into a build. Phase B must now
report NOT RUNNABLE and continue.

**`closure.contract_phase_unsupported`.** An Input's Expectations compile to
`pre_transform` contracts, and this runtime executes those only for a declared
CSV source-aligned input. An api-source closure declares none, so the approved
inventory can never be satisfied — but the only symptom was a bare
`contract_inventory_mismatch` after a whole closure existed, whose obvious
"fix" is to wire the expectations as output promises and silently move a phase
the user approved.

**`struct.model_not_queryable`.** `run_semantic_query` REQUIRES a measure, so a
promised model backing no `semantic_view` cannot be selected at all. Its rows are
reachable only through another model's metric across a join — where a filter
scopes that model's aggregate rather than this model's spine, quietly returning
every row and looking like it worked. Its sibling, a `join(...)` with no
`dimension(...)`, is the same defect and rides `struct.key_not_groupable`.
"""

from __future__ import annotations

import importlib.util
import ast
import json
import re
import subprocess
import sys

import pytest
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]
SELF_CHECK = EVALS_DIR.parent / "src" / "nxd-run-job-loop" / "scripts" / "self_check.py"

# `dlt` is the real discriminator, and `nxd` deliberately is not: self_check
# installs stub `nxd` modules so a closure parses without the wheel, but nothing
# stubs dlt. CI installs neither, so the executable transform cases are skipped
# there while the structural cases still run.
_HAS_DLT = importlib.util.find_spec("dlt") is not None
_needs_dlt = pytest.mark.skipif(
    not _HAS_DLT, reason="dlt not installed; the transform cannot be imported"
)

MODELS_HEAD = (
    "from nxd.spec import Agg, semantic_model, semantic_view\n"
    "from nxd.spec.data_types import number, string\n"
    "from nxd.spec import dimension, field, join, metric, metric_field, primary_key\n\n"
)

def _model(name, *, extra_fields="", view=True):
    src = (
        f'{name} = (\n'
        f'    semantic_model("{name}")\n'
        f'    .description("One row per {name}.")\n'
        f'    .schema(\n'
        f'        {{\n'
        f'            "id": field(string(), primary_key(), dimension(name="{name}_id", description="Key.")),\n'
        f'{extra_fields}'
        f'        }}\n'
        f'    )\n'
        f')\n\n'
    )
    if view:
        src += (
            f'{name}_metrics = semantic_view("{name}_metrics", {name}).schema(\n'
            f'    {{"{name}_count": metric_field(number(), metric(Agg.COUNT, of={name}.field("id"),\n'
            f'        name="{name}_count", description="Rows."))}}\n'
            f')\n\n'
        )
    return src


def _spec(models, views, service, optional_models=()):
    imports = ", ".join(models + list(optional_models) + views)
    promises = "".join(f"    .promise({m})\n" for m in models)
    optional = "".join(f"    .model({m})\n" for m in optional_models)
    registers = "".join(f"    .model({v})\n" for v in views)
    return (
        "from nxd.spec import data_product, data_product_output, script, storage\n"
        f"from models import {imports}\n\n"
        f'{service}'
        '_compute = "/infra-profile/desktop-local#/services/python-compute"\n'
        '_duckdb = "/infra-profile/desktop-local#/services/duckdb"\n\n'
        "_output = (\n    data_product_output()\n"
        f"{promises}{optional}{registers}"
        '    .port("duckdb", storage(_duckdb))\n)\n\n'
        "spec = (\n    data_product(name=\"t\", domain=\"desktop.local\", version=\"0.0.1\",\n"
        '                 infra_profile="desktop-local")\n'
        '    .transform(script("transform/main.py").compute(_compute).secrets([_src]))\n'
        "    .output(_output)\n)\n"
    )


def _run(tmp_path: Path, models_src: str, spec_src: str, transform_src: str,
         base_models: tuple[str, ...]) -> dict:
    """Run the whole script against a synthetic closure and decode its report.

    The exit code is deliberately not asserted: these closures carry no lock, so
    Phase C fails for an unrelated reason. What is asserted is which diagnostics
    the report contains — and, for the dry-run case, that Phase C was REACHED.
    """
    (tmp_path / "models.py").write_text(models_src)
    (tmp_path / "spec.py").write_text(spec_src)
    (tmp_path / "transform").mkdir(exist_ok=True)
    (tmp_path / "transform" / "main.py").write_text(transform_src)
    (tmp_path / "requirements.txt").write_text("nxd.data_product[spec]\n")
    for m in base_models:
        d = tmp_path / "data" / m
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{m}.csv").write_text("id\n1\n")
    (tmp_path / "csv-source-path").write_text("data\n")
    script = tmp_path / "self_check.py"
    script.write_text(SELF_CHECK.read_text())
    proc = subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    match = re.search(r"\{[\s\S]*\}\s*$", proc.stdout)
    assert match, f"no JSON report emitted:\n{out}"
    return json.loads(match.group(0))


def _codes(report: dict) -> list[str]:
    return [d["code"] for d in report["diagnostics"]]


def _fake_state_class():
    """Load only the self-check's offline state model for semantic unit tests."""
    tree = ast.parse(SELF_CHECK.read_text())
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "FakeTransformState")
    ns = {"json": json, "GENERIC_STATE_KEY": "__nxd_generic__"}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(SELF_CHECK), "exec"), ns)
    return ns["FakeTransformState"]


def test_fake_transform_state_matches_current_kernel_boundary():
    FakeState = _fake_state_class()

    single = FakeState(["orders"], {"orders": {"cursor": 3}})
    assert single.models() == ["orders"]
    assert single.for_model("orders") is single
    single["cursor"] = 4
    assert single.persist() == {"orders": {"cursor": 4}}

    multi = FakeState(["orders", "users"])
    orders = multi.for_model("orders")
    assert orders is multi.for_model("orders")
    orders["cursor"] = 7
    multi["flat_cursor"] = 8
    generic = multi.generic()
    generic["batch"] = 1
    persisted = multi.persist()
    assert persisted == {
        "orders": {"cursor": 7},
        "users": {},
        "__nxd_generic__": {"batch": 1},
    }
    assert multi.dropped_flat_write
    assert multi["flat_cursor"] == 8
    with pytest.raises(KeyError):
        multi.for_model("missing")

    unserializable = FakeState(["orders"])
    unserializable["bad"] = float("nan")
    with pytest.raises(ValueError):
        unserializable.persist()


CSV_SERVICE = '_src = "/infra-profile/desktop-local#/services/csv-source"\n'
API_SERVICE = '_src = "/infra-profile/desktop-local#/services/api-source"\n'

CSV_TRANSFORM = (
    "import os\nfrom pathlib import Path\nfrom typing import Any\n"
    "import dlt\nfrom dlt.sources.filesystem import filesystem, read_csv\n"
    "from nxd import data_product\nfrom nxd.core.context import DuckDbOutput\n\n"
    'BASE_MODELS = ("orders",)\nDERIVED_MODELS = ()\n'
    'PHYSICAL_MODELS = ("orders",)\n\n'
    "@data_product.on_transform()\n"
    "def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:\n"
    '    source_root = Path(secrets["csv_source"])\n'
    "    run_dir = Path(duckdb.path).parent\n"
    "    pipelines_dir = run_dir / 'dlt-pipelines'\n"
    "    pipelines_dir.mkdir(parents=True, exist_ok=True)\n"
    "    os.environ['DLT_DATA_DIR'] = str(run_dir / 'dlt-data')\n"
    "    pipeline = dlt.pipeline(pipelines_dir=str(pipelines_dir),\n"
    "        destination=dlt.destinations.duckdb(credentials=duckdb.path),\n"
    "        dataset_name=duckdb.schema)\n"
    "    resources = []\n"
    "    for model in BASE_MODELS:\n"
    "        reader = filesystem(bucket_url=str(source_root / model), file_glob='*.csv') | read_csv()\n"
    "        resources.append(reader.with_name(duckdb.model_tables[model]))\n"
    "    pipeline.run(resources, write_disposition='replace')\n"
    "    actual = set(pipeline.default_schema.data_table_names())\n"
    "    expected = {duckdb.model_tables[m] for m in PHYSICAL_MODELS}\n"
    "    if actual != expected:\n"
    "        raise RuntimeError(f'{sorted(actual)} != {sorted(expected)}')\n"
    "    (run_dir / '.transform-complete').touch()\n\n"
    'if __name__ == "__main__":\n    data_product.main()\n'
)

STATEFUL_TRANSFORM = CSV_TRANSFORM.replace(
    "def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:\n",
    "def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any], transform_state) -> None:\n"
    "    state = transform_state.for_model(\"orders\")\n"
    "    state[\"cursor\"] = state.get(\"cursor\", 0) + 1\n",
)

STATEFUL_NO_WRITE_TRANSFORM = CSV_TRANSFORM.replace(
    "def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:\n",
    "def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any], transform_state) -> None:\n",
)

API_TRANSFORM = CSV_TRANSFORM.replace(
    '    source_root = Path(secrets["csv_source"])\n',
    '    base_url = secrets["base_url"]\n',
)

OPTIONAL_EMPTY_TRANSFORM = (
    CSV_TRANSFORM.replace(
        'BASE_MODELS = ("orders",)\nDERIVED_MODELS = ()\n',
        'BASE_MODELS = ("orders", "reviews")\nDERIVED_MODELS = ()\n'
        'OPTIONAL_EMPTY_MODELS = ("reviews",)\n',
    )
    .replace(
        "    for model in BASE_MODELS:\n"
        "        reader = filesystem(bucket_url=str(source_root / model), file_glob='*.csv') | read_csv()\n",
        "    for model in BASE_MODELS:\n"
        "        if model in OPTIONAL_EMPTY_MODELS and not (source_root / model).is_dir():\n"
        "            continue\n"
        "        reader = filesystem(bucket_url=str(source_root / model), file_glob='*.csv') | read_csv()\n",
    )
    .replace(
        'PHYSICAL_MODELS = ("orders",)\n',
        'PHYSICAL_MODELS = ("orders", "reviews")\n',
    )
    .replace(
        'PHYSICAL_MODELS = ("orders", "reviews")\n',
        'PHYSICAL_MODELS = BASE_MODELS + DERIVED_MODELS\n',
    )
    .replace(
        "    if actual != expected:\n"
        "        raise RuntimeError(f'{sorted(actual)} != {sorted(expected)}')\n",
        "    optional = {duckdb.model_tables[m] for m in OPTIONAL_EMPTY_MODELS}\n"
        "    missing = expected - actual\n"
        "    absent_optional = missing & optional\n"
        "    if actual != expected - absent_optional:\n"
        "        raise RuntimeError(f'{sorted(actual)} != {sorted(expected - absent_optional)}')\n",
    )
)
assert "if model in OPTIONAL_EMPTY_MODELS and not (source_root / model).is_dir()" in OPTIONAL_EMPTY_TRANSFORM

REQUIRED_MISSING_TRANSFORM = CSV_TRANSFORM.replace(
    'PHYSICAL_MODELS = ("orders",)\n',
    'PHYSICAL_MODELS = ("orders", "reviews")\n',
).replace(
    "    if actual != expected:\n"
    "        raise RuntimeError(f'{sorted(actual)} != {sorted(expected)}')\n",
    "    # The self-check must diagnose the missing required table.\n",
)


# --- struct.model_not_queryable ---------------------------------------------

def test_promised_model_backing_no_view_is_flagged(tmp_path):
    models = MODELS_HEAD + _model("orders", view=False)
    report = _run(tmp_path, models, _spec(["orders"], [], CSV_SERVICE),
                  CSV_TRANSFORM, ("orders",))
    assert "struct.model_not_queryable" in _codes(report), (
        "a promised model with no semantic_view is unqueryable — "
        "run_semantic_query requires a measure"
    )


def test_promised_model_with_a_view_is_not_flagged(tmp_path):
    models = MODELS_HEAD + _model("orders", view=True)
    report = _run(tmp_path, models, _spec(["orders"], ["orders_metrics"], CSV_SERVICE),
                  CSV_TRANSFORM, ("orders",))
    assert "struct.model_not_queryable" not in _codes(report), (
        "a single COUNT view is enough to make the model reachable; "
        "flagging it here would fire on every correct closure"
    )


def test_optional_model_without_a_view_is_flagged(tmp_path):
    models = MODELS_HEAD + _model("orders") + _model("reviews", view=False)
    report = _run(
        tmp_path,
        models,
        _spec(["orders"], ["orders_metrics"], CSV_SERVICE,
              optional_models=("reviews",)),
        OPTIONAL_EMPTY_TRANSFORM,
        ("orders",),
    )
    assert "struct.model_not_queryable" in _codes(report), (
        "an optional physical model still needs a semantic view when it is "
        "present and queried"
    )


def test_semantic_view_cannot_be_promised(tmp_path):
    models = MODELS_HEAD + _model("orders", view=True)
    spec = _spec(["orders"], ["orders_metrics"], CSV_SERVICE).replace(
        "    .model(orders_metrics)\n", "    .promise(orders_metrics)\n"
    )
    report = _run(tmp_path, models, spec, CSV_TRANSFORM, ("orders",))
    assert "struct.promise_of_view" in _codes(report)


# --- optional physical outputs ----------------------------------------------

def _optional_closure(tmp_path, transform=OPTIONAL_EMPTY_TRANSFORM,
                      optional_models=("reviews",), base_models=("orders",)):
    models = MODELS_HEAD + _model("orders") + _model("reviews")
    return _run(
        tmp_path,
        models,
        _spec(["orders"], ["orders_metrics", "reviews_metrics"], CSV_SERVICE,
              optional_models=optional_models),
        transform,
        base_models,
    )


@_needs_dlt
def test_zero_row_optional_output_may_be_absent(tmp_path):
    report = _optional_closure(tmp_path)
    codes = _codes(report)
    assert "runtime.model_table_missing" not in codes, codes
    assert "runtime.row_count" in codes, codes
    optional_count = next(
        d for d in report["diagnostics"]
        if d["code"] == "runtime.row_count" and d["evidence"].get("model") == "reviews"
    )
    assert optional_count["evidence"] == {
        "model": "reviews", "count": 0, "materialized": False, "optional": True
    }


@_needs_dlt
def test_non_empty_optional_output_is_queryable(tmp_path):
    report = _optional_closure(tmp_path, base_models=("orders", "reviews"))
    missing = [
        d for d in report["diagnostics"]
        if d["code"] == "runtime.model_table_missing" and d["evidence"].get("model") == "reviews"
    ]
    assert not missing, missing
    review_count = next(
        d for d in report["diagnostics"]
        if d["code"] == "runtime.row_count" and d["evidence"].get("model") == "reviews"
    )
    assert review_count["evidence"]["count"] == 1
    assert "materialized" not in review_count["evidence"]


@_needs_dlt
def test_required_zero_row_output_still_has_specific_missing_table_diagnostic(tmp_path):
    report = _run(
        tmp_path,
        MODELS_HEAD + _model("orders") + _model("reviews"),
        _spec(["orders", "reviews"], ["orders_metrics", "reviews_metrics"], CSV_SERVICE),
        REQUIRED_MISSING_TRANSFORM,
        ("orders",),
    )
    missing = [
        d for d in report["diagnostics"]
        if d["code"] == "runtime.model_table_missing"
        and d["evidence"].get("model") == "reviews"
    ]
    assert missing, report["diagnostics"]


def test_optional_metadata_requires_a_literal_physical_model_registration(tmp_path):
    invalid = OPTIONAL_EMPTY_TRANSFORM.replace(
        'OPTIONAL_EMPTY_MODELS = ("reviews",)',
        'OPTIONAL_EMPTY_MODELS = ("not_a_physical_model",)',
    )
    report = _optional_closure(tmp_path, transform=invalid)
    assert "struct.optional_models_invalid" in _codes(report)


def test_optional_metadata_cannot_name_a_semantic_view(tmp_path):
    transform = CSV_TRANSFORM.replace(
        'PHYSICAL_MODELS = ("orders",)\n',
        'PHYSICAL_MODELS = ("orders", "orders_metrics")\n'
        'OPTIONAL_EMPTY_MODELS = ("orders_metrics",)\n',
    )
    report = _run(
        tmp_path,
        MODELS_HEAD + _model("orders"),
        _spec(["orders"], ["orders_metrics"], CSV_SERVICE),
        transform,
        ("orders",),
    )
    assert "struct.optional_models_invalid" in _codes(report)


def test_optional_metadata_cannot_be_promised(tmp_path):
    # The tuple is valid but the spec promises the optional model: exercise the
    # rule without relying on the transform runtime.
    report = _run(
        tmp_path,
        MODELS_HEAD + _model("orders") + _model("reviews"),
        _spec(["orders", "reviews"], ["orders_metrics", "reviews_metrics"], CSV_SERVICE),
        OPTIONAL_EMPTY_TRANSFORM,
        ("orders",),
    )
    assert "struct.optional_model_promised" in _codes(report)


def test_optional_metadata_requires_catalog_registration(tmp_path):
    report = _optional_closure(tmp_path, optional_models=())
    assert "struct.optional_model_not_registered" in _codes(report)


def test_every_physical_model_cannot_be_optional(tmp_path):
    transform = CSV_TRANSFORM.replace(
        'BASE_MODELS = ("orders",)\nDERIVED_MODELS = ()\n',
        'BASE_MODELS = ("orders",)\nDERIVED_MODELS = ()\n'
        'OPTIONAL_EMPTY_MODELS = ("orders",)\n',
    )
    report = _run(
        tmp_path,
        MODELS_HEAD + _model("orders"),
        _spec([], [], CSV_SERVICE, optional_models=("orders",)),
        transform,
        ("orders",),
    )
    assert "struct.optional_models_invalid" in _codes(report), report["diagnostics"]


# --- struct.key_not_groupable, the join-shaped half -------------------------

JOIN_ONLY = '            "cust": field(string(), join(to="customers", to_column="id")),\n'
JOIN_PLUS_DIM = (
    '            "cust": field(string(), join(to="customers", to_column="id"),\n'
    '                dimension(name="cust", description="Customer this row is about.")),\n'
)


def _two_models(join_field):
    return (MODELS_HEAD + _model("customers", view=True)
            + _model("orders", extra_fields=join_field, view=True))


def test_join_without_a_dimension_is_flagged(tmp_path):
    report = _run(tmp_path, _two_models(JOIN_ONLY),
                  _spec(["customers", "orders"],
                        ["customers_metrics", "orders_metrics"], CSV_SERVICE),
                  CSV_TRANSFORM.replace('BASE_MODELS = ("orders",)',
                                        'BASE_MODELS = ("customers", "orders")')
                              .replace('PHYSICAL_MODELS = ("orders",)',
                                       'PHYSICAL_MODELS = ("customers", "orders")'),
                  ("customers", "orders"))
    groupable = [d for d in report["diagnostics"]
                 if d["code"] == "struct.key_not_groupable" and "join(" in d["message"]]
    assert groupable, (
        "a join-only field never reaches describe_models, so the model cannot "
        "be filtered or grouped by the entity it points at"
    )


def test_join_composed_with_a_dimension_is_not_flagged(tmp_path):
    report = _run(tmp_path, _two_models(JOIN_PLUS_DIM),
                  _spec(["customers", "orders"],
                        ["customers_metrics", "orders_metrics"], CSV_SERVICE),
                  CSV_TRANSFORM.replace('BASE_MODELS = ("orders",)',
                                        'BASE_MODELS = ("customers", "orders")')
                              .replace('PHYSICAL_MODELS = ("orders",)',
                                       'PHYSICAL_MODELS = ("customers", "orders")'),
                  ("customers", "orders"))
    groupable = [d for d in report["diagnostics"]
                 if d["code"] == "struct.key_not_groupable" and "join(" in d["message"]]
    assert not groupable, groupable


# --- runtime.dry_run_not_runnable, and the phases it must not eat -----------
#
# The decision itself is a named predicate so it can be tested WITHOUT importing
# the closure's transform. CI installs neither `dlt` nor `nxd`, so a synthetic
# transform fails at `runtime.import_failed` long before `ingest()` runs — which
# is exactly why the reach- and grant-gate suites extract their blocks rather
# than executing a closure end to end. These extraction tests therefore run
# everywhere; the end-to-end pair below is an extra that runs only where the
# runtime deps exist.

_WAIVER = re.compile(r"(def dry_run_waived\(exc, network_declared\):[\s\S]*?\n    return [^\n]*\n)")


def _waived(exc, network_declared):
    src = SELF_CHECK.read_text()
    match = _WAIVER.search(src)
    assert match, "the dry_run_waived predicate was renamed or removed"
    ns: dict = {}
    exec(match.group(1), ns)
    return ns["dry_run_waived"](exc, network_declared)


def test_missing_secret_is_waived_only_for_a_network_connector():
    assert _waived(KeyError("base_url"), True), (
        "an api-source/db-source closure reads its connection from secrets, "
        "which the offline harness cannot supply — a known limit, not a defect"
    )
    assert not _waived(KeyError("csv_source"), False), (
        "a CSV closure declares no network source, so a missing secret is a "
        "real fault and must still fail Phase B"
    )


def test_the_waiver_is_keyed_on_the_connector_not_the_exception_type():
    assert not _waived(RuntimeError("base_url"), True), (
        "only a missing secret is waived. A transform that genuinely raises "
        "must still fail Phase B on a network closure too — otherwise the "
        "waiver becomes a blanket amnesty for every api-source transform."
    )
    assert not _waived(ValueError("boom"), True)


def test_phase_b_failure_no_longer_short_circuits_phase_c():
    """The regression this whole gate exists for, asserted on the source.

    Losing Phases C, D and E to an expected KeyError is how a missing contract
    wiring and a hardcoded policy value reached a build. The read-back sweeps and
    the completion-marker check must all be guarded by `dry_run_runnable`, and
    the stage must close as `skipped` — never `passed`.
    """
    src = SELF_CHECK.read_text()
    assert 'close_stage("s2_transform", "skipped"' in src, (
        "a not-runnable dry run must not report the stage as passed"
    )
    guarded = src.count("if dry_run_runnable else ()")
    assert guarded >= 3, (
        f"every sweep over the dry-run database must be guarded; found {guarded}"
    )
    assert "if dry_run_runnable and not (run / \".transform-complete\").exists():" in src, (
        "the completion marker cannot exist when the transform never ran"
    )
    # and the guard must sit BEFORE Phase C, or C is skipped anyway
    assert src.index("dry_run_runnable = True") < src.index("Phase C ---")


@_needs_dlt
def test_credentialed_dry_run_reports_not_runnable_and_reaches_phase_c(tmp_path):
    models = MODELS_HEAD + _model("orders", view=True)
    report = _run(tmp_path, models, _spec(["orders"], ["orders_metrics"], API_SERVICE),
                  API_TRANSFORM, ("orders",))
    codes = _codes(report)
    assert "runtime.dry_run_not_runnable" in codes, codes
    assert "runtime.transform_raised" not in codes, (
        "the expected KeyError must not be reported as a transform fault"
    )
    unreached = [d for d in report["diagnostics"]
                 if d["code"] == "meta.stage_not_reached" and "s3_closure" in d["message"]]
    assert not unreached, (
        "Phase B being not-runnable must not skip Phase C"
    )


@_needs_dlt
def test_a_csv_closure_still_fails_on_a_real_key_error(tmp_path):
    models = MODELS_HEAD + _model("orders", view=True)
    broken = CSV_TRANSFORM.replace('secrets["csv_source"]', 'secrets["nope"]')
    report = _run(tmp_path, models, _spec(["orders"], ["orders_metrics"], CSV_SERVICE),
                  broken, ("orders",))
    codes = _codes(report)
    assert "runtime.transform_raised" in codes, codes
    assert "runtime.dry_run_not_runnable" not in codes


@_needs_dlt
def test_stateful_transform_is_injected_and_verified_again(tmp_path):
    models = MODELS_HEAD + _model("orders", view=True)
    report = _run(tmp_path, models, _spec(["orders"], ["orders_metrics"], CSV_SERVICE),
                  STATEFUL_TRANSFORM, ("orders",))
    codes = _codes(report)
    assert not {
        "runtime.state_unserializable",
        "runtime.state_not_persisted",
        "runtime.state_flat_write",
        "runtime.rerun_row_count_changed",
    } & set(codes), codes


@_needs_dlt
def test_stateful_transform_that_lands_rows_without_state_fails(tmp_path):
    models = MODELS_HEAD + _model("orders", view=True)
    report = _run(tmp_path, models, _spec(["orders"], ["orders_metrics"], CSV_SERVICE),
                  STATEFUL_NO_WRITE_TRANSFORM, ("orders",))
    assert "runtime.state_not_persisted" in _codes(report)


# --- closure.contract_phase_unsupported -------------------------------------
#
# Extracted and run standalone, the way test_reach_gate_phase_e.py runs Phase E:
# the rule reads only `is_v3_lock`, `v3_pre_transform_contracts` and
# `declared_sources`, all already in scope at that point in the real script.

_RULE = re.compile(
    r"(    if is_v3_lock and v3_pre_transform_contracts and \"csv-source\" not in declared_sources:"
    r"[\s\S]*?\n        \)\n)",
)


def _run_rule(pre_transform, sources):
    src = SELF_CHECK.read_text()
    match = _RULE.search(src)
    assert match, "the contract_phase_unsupported rule was renamed or removed"
    fired = []
    ns = {
        "is_v3_lock": True,
        "v3_pre_transform_contracts": set(pre_transform),
        "declared_sources": set(sources),
        "cerr": lambda code, msg, at="", ev=None: fired.append((code, msg)),
    }
    exec("def _r():\n" + match.group(1).replace("\n    ", "\n        "), ns)
    ns["_r"]()
    return fired


def test_pre_transform_contracts_on_an_api_source_are_rejected():
    fired = _run_rule({"exp_issue_identity", "exp_state_type_known"}, {"api-source"})
    assert fired and fired[0][0] == "closure.contract_phase_unsupported"
    message = fired[0][1]
    assert "exp_issue_identity" in message, "the message must name the ids"
    assert "dp-blueprint.md" in message, "the fix is a spec edit, not a closure edit"


def test_pre_transform_contracts_on_a_csv_source_are_fine():
    assert not _run_rule({"exp_issue_identity"}, {"csv-source"}), (
        "the CSV path is exactly where an input expectation DOES execute"
    )


def test_no_pre_transform_contracts_is_fine():
    assert not _run_rule(set(), {"api-source"})

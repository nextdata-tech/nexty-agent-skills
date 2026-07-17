#!/usr/bin/env python3
"""Acceptance test for the generated data-product closure (run me before finishing).

Validates the closure the way the desktop supervisor would consume it — minus
the kernel:

  1. STATIC: the closure is complete and internally consistent — the naming
     invariant holds across models.py / models.yaml / manifest model_tables /
     the data/ connector layout; the wiring YAMLs carry the exact S0 driver
     ids and the verbatim ``__NXD_STAGING_DATA__`` placeholder; spec.py
     promises the models and uses ``.semantic_tools()``; models.py places the
     provided inferred blobs verbatim; the transform is dlt-through-port (no
     direct DuckDB writes, no DDL).
  2. LIVE: actually EXECUTES transform/main.py (nxd stubbed, dlt real)
     against the closure's own data/ connector export into a scratch run dir,
     then verifies the produced DuckDB: every promised model landed as
     ``main.<name>``, row counts and numeric column sums match the CSVs, and
     the ``.transform-complete`` readiness marker was touched.

Usage (from the workspace/closure root):

    uv run --python 3.12 --with "dlt[duckdb]==1.28.2" --with "duckdb==1.5.4" \
        --with "pandas==2.3.3" --with pyyaml \
        python check_generated_closure.py [closure_dir]

Notes:
  * nxd itself is STUBBED (spec API + transform runtime + DuckDbOutput), so
    no nxd wheel is needed; dlt/duckdb/pandas/pyyaml must be importable.
  * This encodes the runnability contract only. Judgment calls (how the
    intent was interpreted, the quality of the final report) are graded
    separately, not here.

Exit 0 and ``ALL CHECKS PASSED`` when everything holds; exit 1 otherwise;
exit 2 when a required package is missing.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import tempfile
import types
from dataclasses import dataclass, field
from pathlib import Path

SEMANTIC_KEY = "__nxd_semantic__"

DUCKDB_STORAGE_DRIVER = "nxd:local/duckdb/storage:0.1.0"
GENERIC_SECRETS_DRIVER = "nxd:generic-secrets:1.0.0"
PYTHON_COMPUTE_DRIVER = "nxd:local/python/compute:0.1.0"
STAGING_PLACEHOLDER = "__NXD_STAGING_DATA__"

REQUIRED_FILES = [
    "spec.py",
    "models.py",
    "transform/main.py",
    "requirements.txt",
    "deployment-spec.yaml",
    "manifest.yaml",
    "models.yaml",
    "csv-source-path",
]

# ---------------------------------------------------------------------------
# nxd stubs — enough surface to execute models.py, spec.py, and
# transform/main.py without the nxd wheel, while capturing what they declare.
# ---------------------------------------------------------------------------

_MODELS: list["_SemanticModel"] = []
_PROMISED: list[str] = []
_SEMANTIC_TOOLS_CALLS: list[dict] = []
_RPC_OUTPUT_CALLS: list[int] = []
_TRANSFORMS: list = []


class _AttributeSpec:
    def __init__(self, name=None, data_type=None, **kwargs):
        self.name = name
        self.data_type = data_type
        self._metadata: dict = {}

    def semantic_annotation(self, blob):  # post-stopgap public API
        self._metadata[SEMANTIC_KEY] = (
            blob if isinstance(blob, str) else json.dumps(blob)
        )
        return self

    def referencing(self, *args, **kwargs):
        return self

    def __getattr__(self, item):
        def _chain(*args, **kwargs):
            return self

        return _chain


def _attribute(data_type=None, name=None, *args, **kwargs):
    return _AttributeSpec(name=name, data_type=data_type)


class _SemanticModel:
    def __init__(self, name):
        self.name = name
        self._attributes: dict[str, _AttributeSpec] = {}
        _MODELS.append(self)

    def description(self, *_a, **_k):
        return self

    def link(self, *_a, **_k):
        return self

    def schema(self, mapping):
        for key, value in dict(mapping).items():
            attr = value if isinstance(value, _AttributeSpec) else _AttributeSpec(name=key)
            if attr.name is None:
                attr.name = key
            self._attributes[key] = attr
        return self

    def __getattr__(self, item):
        def _chain(*args, **kwargs):
            return self

        return _chain


class _Anything:
    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, item):
        return self


class _OutputChain:
    def promise(self, model):
        _PROMISED.append(getattr(model, "name", str(model)))
        return self

    def port(self, *args, **kwargs):
        return self

    def __getattr__(self, item):
        def _chain(*args, **kwargs):
            return self

        return _chain


class _SpecChain:
    def semantic_tools(self, *args, **kwargs):
        _SEMANTIC_TOOLS_CALLS.append({"args": args, "kwargs": kwargs})
        return self

    def __getattr__(self, item):
        def _chain(*args, **kwargs):
            return self

        return _chain


def _data_product(*args, **kwargs):
    return _SpecChain()


def _data_product_output(*args, **kwargs):
    return _OutputChain()


def _data_product_rpc_output(*args, **kwargs):
    _RPC_OUTPUT_CALLS.append(1)
    return _OutputChain()


@dataclass
class _DuckDbOutput:
    path: str
    schema: str
    model_tables: dict
    models: dict = field(default_factory=dict)

    def full_table_name(self, model: str) -> str:
        table = self.model_tables.get(model)
        if not table:
            raise ValueError(f"Invalid model name {model!r}")
        return f"{self.schema}.{table}"

    def models_dict(self) -> dict:
        return self.models


class _DataProductRuntime:
    """Stub for `from nxd import data_product` (the transform runtime)."""

    def on_transform(self, *args, **kwargs):
        if args and callable(args[0]) and not kwargs:
            _TRANSFORMS.append(args[0])
            return args[0]

        def deco(fn):
            _TRANSFORMS.append(fn)
            return fn

        return deco

    def main(self):
        return None

    def __getattr__(self, item):
        return _Anything()


def _install_stubs() -> None:
    def module(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        mod.__getattr__ = lambda item: _Anything()  # PEP 562 fallback
        sys.modules[name] = mod
        return mod

    nxd = module("nxd")
    runtime = _DataProductRuntime()
    nxd.data_product = runtime
    dp_mod = module("nxd.data_product")
    dp_mod.on_transform = runtime.on_transform
    dp_mod.main = runtime.main

    spec = module("nxd.spec")
    spec.semantic_model = _SemanticModel
    spec.attribute = _attribute
    spec.Predicate = _Anything()
    spec.data_product = _data_product
    spec.data_product_output = _data_product_output
    spec.data_product_rpc_output = _data_product_rpc_output
    spec.storage = _Anything()
    spec.code = _Anything()
    nxd.spec = spec

    model_mod = module("nxd.spec._model")
    model_mod.AttributeSpec = _AttributeSpec
    module("nxd.spec.data_types")  # every factory via __getattr__

    core = module("nxd.core")
    ctx = module("nxd.core.context")
    ctx.DuckDbOutput = _DuckDbOutput
    core.context = ctx
    nxd.core = core


def _exec_module(path: Path, module_name: str) -> types.ModuleType:
    source = path.read_text(encoding="utf-8")
    mod = types.ModuleType(module_name)
    mod.__file__ = str(path)
    sys.modules[module_name] = mod
    exec(compile(source, str(path), "exec"), mod.__dict__)  # noqa: S102
    return mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical_roles(blob) -> list[str]:
    roles = blob["roles"] if isinstance(blob, dict) and "roles" in blob else [blob]
    return sorted(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in roles)


def _registry_from_models() -> dict[str, dict[str, list[str]]]:
    registry: dict[str, dict[str, list[str]]] = {}
    for model in _MODELS:
        columns: dict[str, list[str]] = {}
        for col, attr in model._attributes.items():
            raw = attr._metadata.get(SEMANTIC_KEY)
            if raw is None:
                continue
            blob = json.loads(raw) if isinstance(raw, str) else raw
            columns[col] = _canonical_roles(blob)
        registry[model.name] = columns
    return registry


def _csv_stats(model_dir: Path) -> tuple[list[str], int, dict[str, float]]:
    """Header, data-row count, and per-numeric-column sum across the model's CSVs."""
    header: list[str] = []
    rows = 0
    values: dict[str, list[str]] = {}
    for csv_file in sorted(model_dir.glob("*.csv")):
        with io.open(csv_file, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            file_header = next(reader, None) or []
            if not header:
                header = file_header
                values = {col: [] for col in header}
            for row in reader:
                if not any(cell.strip() for cell in row):
                    continue
                rows += 1
                for col, cell in zip(header, row):
                    values[col].append(cell)
    sums: dict[str, float] = {}
    for col, cells in values.items():
        non_empty = [c for c in cells if c.strip() != ""]
        if not non_empty:
            continue
        try:
            sums[col] = sum(float(c) for c in non_empty)
        except ValueError:
            continue
    return header, rows, sums


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def run_checks(root: Path) -> list[tuple[str, str]]:
    import duckdb
    import yaml

    failures: list[tuple[str, str]] = []
    passed: list[str] = []

    def check(check_id: str, ok: bool, why: str = "") -> None:
        (passed.append(check_id) if ok else failures.append((check_id, why)))

    # 1. Closure completeness.
    missing = [f for f in REQUIRED_FILES if not (root / f).is_file()]
    check("closure-files-present", not missing, f"missing: {missing}")
    if missing:
        _emit(passed, failures)
        return failures

    manifest = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8")) or {}
    deployment = yaml.safe_load((root / "deployment-spec.yaml").read_text(encoding="utf-8")) or {}
    models_yaml = yaml.safe_load((root / "models.yaml").read_text(encoding="utf-8")) or {}

    # 2. Manifest wiring: executor + the output port shape S0 pins.
    executor = manifest.get("executor") or {}
    ports = ((manifest.get("output") or {}).get("ports") or {})
    port = ports.get("output") or {}
    config = port.get("config") or {}
    model_tables = config.get("model_tables") or {}
    errs = []
    if executor.get("driver") != PYTHON_COMPUTE_DRIVER:
        errs.append(f"executor.driver={executor.get('driver')!r} != {PYTHON_COMPUTE_DRIVER!r}")
    if "csv-source" not in (executor.get("secrets") or []):
        errs.append("executor.secrets missing 'csv-source'")
    if set(ports) != {"output"}:
        errs.append(f"output.ports keys {sorted(ports)} != ['output'] (port name == transform param)")
    if port.get("service") != "output":
        errs.append(f"port service={port.get('service')!r} != 'output'")
    if config.get("path") != STAGING_PLACEHOLDER:
        errs.append(f"config.path={config.get('path')!r} — must be the verbatim {STAGING_PLACEHOLDER}")
    if config.get("schema") != "main":
        errs.append(f"config.schema={config.get('schema')!r} != 'main'")
    if not model_tables or not isinstance(model_tables, dict):
        errs.append("config.model_tables missing/empty")
    check("manifest-wiring", not errs, "; ".join(errs))

    # 3. The naming invariant inside model_tables: identity map, lowercase.
    bad = [
        f"{k!r}: {v!r}"
        for k, v in model_tables.items()
        if k != v or not re.fullmatch(r"[a-z_][a-z0-9_]*", str(k) or "")
    ]
    check("model-tables-identity-lowercase", bool(model_tables) and not bad,
          f"model_tables must map <name> -> <name>, lowercase snake_case: {bad}")
    models = sorted(str(k) for k in model_tables)

    # 4. Deployment spec: the two S0 services with exact driver ids.
    services = {s.get("name"): s.get("driver") for s in (deployment.get("services") or [])}
    errs = []
    if services.get("output") != DUCKDB_STORAGE_DRIVER:
        errs.append(f"service 'output' driver={services.get('output')!r} != {DUCKDB_STORAGE_DRIVER!r}")
    if services.get("csv-source") != GENERIC_SECRETS_DRIVER:
        errs.append(f"service 'csv-source' driver={services.get('csv-source')!r} != {GENERIC_SECRETS_DRIVER!r}")
    check("deployment-spec-services", not errs, "; ".join(errs))

    # 5. csv-source-path: relative, resolves, one subdir per model with CSVs.
    raw = (root / "csv-source-path").read_text(encoding="utf-8").strip()
    errs = []
    csv_root = None
    if not raw:
        errs.append("csv-source-path is empty")
    elif Path(raw).is_absolute():
        errs.append(f"csv-source-path {raw!r} is absolute — must be relative to the closure root")
    else:
        csv_root = (root / raw).resolve()
        if not csv_root.is_dir():
            errs.append(f"csv-source-path {raw!r} does not resolve to a directory")
        else:
            for m in models:
                if not list((csv_root / m).glob("*.csv")):
                    errs.append(f"no CSVs at <csv-source>/{m}/*.csv")
    check("csv-source-layout", not errs, "; ".join(errs))
    if csv_root is None or errs:
        _emit(passed, failures)
        return failures

    csv_stats = {m: _csv_stats(csv_root / m) for m in models}

    # 6. models.yaml: promised models == model_tables keys; attributes are the
    #    CSV headers byte-exactly, typed as the inferred model dictated.
    inferred_path = root / "inferred_model.json"
    inferred = {}
    if inferred_path.is_file():
        inferred = (json.loads(inferred_path.read_text(encoding="utf-8"))).get("models", {})
    declared = {m.get("name"): m for m in (models_yaml.get("models") or [])}
    errs = []
    if sorted(declared) != models:
        errs.append(f"models.yaml names {sorted(declared)} != model_tables {models}")
    else:
        for m in models:
            attrs = declared[m].get("attributes") or {}
            header = csv_stats[m][0]
            if sorted(attrs) != sorted(header):
                errs.append(f"{m}: attributes {sorted(attrs)} != CSV header {sorted(header)}")
                continue
            for col, spec_ in attrs.items():
                want = ((inferred.get(m, {}).get("columns", {}).get(col) or {}).get("data_type"))
                got = (spec_ or {}).get("data-type")
                if want and got != want:
                    errs.append(f"{m}.{col}: data-type {got!r} != inferred {want!r}")
    check("models-yaml-matches-connector", not errs, "; ".join(errs[:4]))

    # 7. models.py under stubs: names + the provided blobs placed verbatim.
    sys.path.insert(0, str(root))
    try:
        _exec_module(root / "models.py", "models")
    except Exception as exc:  # noqa: BLE001 — surface the author error verbatim
        check("models-py-loads", False, f"executing models.py raised {exc!r}")
        _emit(passed, failures)
        return failures
    check("models-py-loads", True)

    model_names = sorted(m.name for m in _MODELS)
    check("models-py-names", model_names == models,
          f"semantic_model names {model_names} != model_tables {models} "
          "(bare lowercase physical names; no extra/marker models on desktop)")

    registry = _registry_from_models()
    errs = []
    if inferred:
        for m, spec_ in inferred.items():
            placed = registry.get(m, {})
            for col, col_spec in spec_.get("columns", {}).items():
                want = sorted(
                    json.dumps(r, sort_keys=True, separators=(",", ":"))
                    for r in col_spec.get("roles", [])
                )
                got = placed.get(col, [])
                if want and got != want:
                    errs.append(f"{m}.{col}: placed roles differ from inferred_model.json")
                elif not want and got:
                    errs.append(f"{m}.{col}: annotated, but the inferred model left it unannotated")
            extra = set(placed) - set(spec_.get("columns", {}))
            if extra:
                errs.append(f"{m}: blobs on unknown columns {sorted(extra)}")
    else:
        errs.append("inferred_model.json not found next to the closure — cannot verify placement")
    check("blobs-placed-verbatim", not errs, "; ".join(errs[:4]))

    # 8. spec.py under stubs: promises + .semantic_tools(), no rpc output.
    try:
        _exec_module(root / "spec.py", "spec_under_test")
    except Exception as exc:  # noqa: BLE001
        check("spec-py-loads", False, f"executing spec.py raised {exc!r}")
        _emit(passed, failures)
        return failures
    check("spec-py-loads", True)
    check("spec-promises-models", sorted(set(_PROMISED)) == models,
          f"promised {sorted(set(_PROMISED))} != model_tables {models}")
    st_ok = (
        len(_SEMANTIC_TOOLS_CALLS) == 1
        and bool(_SEMANTIC_TOOLS_CALLS[0]["kwargs"].get("service")
                 or _SEMANTIC_TOOLS_CALLS[0]["args"])
    )
    check("spec-semantic-tools", st_ok,
          f"need exactly one .semantic_tools(service=...) call; saw {len(_SEMANTIC_TOOLS_CALLS)}")
    check("spec-no-rpc-output", not _RPC_OUTPUT_CALLS,
          "data_product_rpc_output() called — it raises alongside .semantic_tools()")

    # 9. Transform source: dlt-through-port, no direct-write escape hatches.
    source = (root / "transform" / "main.py").read_text(encoding="utf-8")
    must = [
        ("on_transform", r"on_transform"),
        ("DuckDbOutput handle", r"DuckDbOutput"),
        ("names from output.model_tables", r"output\.model_tables"),
        ("dlt pipeline", r"dlt\.pipeline\("),
        ("filesystem source", r"filesystem\("),
        ("read_csv reader", r"read_csv"),
        ("duckdb destination on the port path", r"credentials\s*=\s*output\.path"),
        ("dataset from the port schema", r"dataset_name\s*=\s*output\.schema"),
        ("run-local pipelines_dir", r"pipelines_dir"),
        ("idempotent replace", r"write_disposition\s*=\s*['\"]replace['\"]"),
        ("read-back of produced tables", r"data_table_names\("),
        ("readiness marker", r"\.transform-complete"),
        ("connector via secrets", r"csv_source"),
        ("entrypoint", r"data_product\.main\(\)"),
    ]
    errs = [f"missing {label}" for label, pat in must if not re.search(pat, source)]
    forbidden = [
        ("direct duckdb write", r"duckdb\.connect"),
        ("DDL", r"(?i)CREATE\s+(OR\s+REPLACE\s+)?(TABLE|VIEW)"),
        ("staging placeholder leaked into code", STAGING_PLACEHOLDER),
    ]
    errs += [f"forbidden: {label}" for label, pat in forbidden if re.search(pat, source)]
    check("transform-dlt-through-port", not errs, "; ".join(errs[:5]))

    # 10. LIVE: execute the transform against the closure's own connector data.
    live_failures = _live_run(root, models, dict(model_tables), csv_root,
                              csv_stats, check, duckdb)
    if live_failures:
        _emit(passed, failures)
        return failures

    # 11. Requirements: the proven pins + the nxd wheel.
    req = (root / "requirements.txt").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in req.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    errs = []
    if not any(re.fullmatch(r"dlt\[duckdb\]==1\.28\.2", ln) for ln in lines):
        errs.append("missing pin dlt[duckdb]==1.28.2")
    if not any(re.fullmatch(r"duckdb==1\.5\.4", ln) for ln in lines):
        errs.append("missing pin duckdb==1.5.4")
    if not any(ln.startswith("pandas") for ln in lines):
        errs.append("missing pandas (dlt read_csv requires it)")
    if not any(ln.startswith("nxd") for ln in lines):
        errs.append("missing the nxd wheel dependency")
    check("requirements-pinned", not errs, "; ".join(errs))

    _emit(passed, failures)
    return failures


def _live_run(root, models, model_tables, csv_root, csv_stats, check, duckdb) -> bool:
    """Execute the transform for real. Returns True on a fatal (early-emit) failure."""
    import inspect

    os.environ.pop("NXD_DESKTOP_REPO_ROOT", None)  # keep the run hermetic
    try:
        _exec_module(root / "transform" / "main.py", "transform_main_under_test")
    except Exception as exc:  # noqa: BLE001
        check("transform-loads", False, f"importing transform/main.py raised {exc!r}")
        return True
    check("transform-loads", True)

    if not _TRANSFORMS:
        check("transform-registered", False, "no @data_product.on_transform() function registered")
        return True
    fn = _TRANSFORMS[-1]
    params = list(inspect.signature(fn).parameters)
    sig_ok = params[:1] == ["output"] and "secrets" in params
    check("transform-registered", sig_ok,
          f"params {params} — first must be 'output' (== the manifest port name), plus 'secrets'")
    if not sig_ok:
        return True

    with tempfile.TemporaryDirectory(prefix="closure-live-run-") as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        staging = run_dir / "data.duckdb"
        out = _DuckDbOutput(path=str(staging), schema="main", model_tables=model_tables)
        old_dlt_dir = os.environ.get("DLT_DATA_DIR")
        try:
            fn(output=out, secrets={"csv_source": str(csv_root)})
        except Exception as exc:  # noqa: BLE001
            check("live-transform-run", False, f"transform raised {exc!r}")
            return True
        finally:
            if old_dlt_dir is None:
                os.environ.pop("DLT_DATA_DIR", None)
            else:
                os.environ["DLT_DATA_DIR"] = old_dlt_dir
        check("live-transform-run", True)

        check("live-staging-materialized",
              staging.is_file() and staging.stat().st_size > 0,
              "staging DuckDB missing/empty after the transform")
        check("live-readiness-marker", (run_dir / ".transform-complete").is_file(),
              ".transform-complete not touched in the run dir (parent of output.path)")

        con = duckdb.connect(str(staging), read_only=True)
        try:
            landed = {
                r[0]
                for r in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main' AND table_name NOT LIKE '\\_dlt%' ESCAPE '\\'"
                ).fetchall()
            }
            check("live-naming-invariant", landed == set(models),
                  f"main.* data tables {sorted(landed)} != promised {models}")

            errs = []
            for m in models:
                header, rows, sums = csv_stats[m]
                try:
                    count = con.execute(f"SELECT COUNT(*) FROM main.{m}").fetchone()[0]
                except Exception as exc:  # noqa: BLE001
                    errs.append(f"unquoted SELECT ... FROM main.{m} failed: {exc!r}")
                    continue
                if count != rows:
                    errs.append(f"main.{m}: {count} rows != {rows} CSV data rows")
                cols = {r[0] for r in con.execute(f"DESCRIBE main.{m}").fetchall()}
                missing_cols = [c for c in header if c not in cols]
                if missing_cols:
                    errs.append(f"main.{m}: CSV columns not landed byte-exactly: {missing_cols}")
                    continue
                for col, want in sums.items():
                    got = con.execute(f'SELECT SUM("{col}") FROM main.{m}').fetchone()[0]
                    if got is None or abs(float(got) - want) > 0.01:
                        errs.append(f"main.{m}.{col}: SUM {got} != CSV sum {round(want, 2)}")
            check("live-data-integrity", not errs, "; ".join(errs[:4]))
        finally:
            con.close()
    return False


def _emit(passed: list[str], failures: list[tuple[str, str]]) -> None:
    for check_id in passed:
        print(f"PASS {check_id}")
    for check_id, why in failures:
        print(f"FAIL {check_id}: {why}")
    total = len(passed) + len(failures)
    if failures:
        print(f"{len(failures)}/{total} CHECKS FAILED")
    else:
        print(f"ALL CHECKS PASSED ({total}/{total})")


def main() -> int:
    try:
        import dlt  # noqa: F401
        import duckdb  # noqa: F401
        import pandas  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as exc:
        print(
            f"missing dependency ({exc.name}). Run:\n"
            '  uv run --python 3.12 --with "dlt[duckdb]==1.28.2" '
            '--with "duckdb==1.5.4" --with "pandas==2.3.3" --with pyyaml '
            "python check_generated_closure.py"
        )
        return 2

    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    _install_stubs()
    return 1 if run_checks(root) else 0


if __name__ == "__main__":
    raise SystemExit(main())

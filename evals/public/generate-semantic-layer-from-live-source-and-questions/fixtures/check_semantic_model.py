#!/usr/bin/env python3
"""Acceptance test for the authored semantic model (run me before finishing).

Loads ``models.py`` (with the nxd spec API stubbed, so no nxd wheel is
needed), extracts the per-field ``__nxd_semantic__`` role blobs, validates
them against the LIVE ``source.duckdb`` tables, and then actually EXECUTES the
four stakeholder questions by compiling the declared concepts to SQL and
comparing the rows against reference queries. A model that only *looks*
plausible — wrong join target, boolean flag summed numerically, metric on the
wrong column — fails here at "query time" instead of at pod boot.

Usage (from the workspace root; duckdb package required):

    uv run --with duckdb python check_semantic_model.py \
        [models.py] [source.duckdb] [schema.json]

Notes:
  * This encodes only the ANSWERABILITY of the four stakeholder questions the
    task already states (plus the role-grammar rules the kernel enforces). It
    is not the grading rubric.
  * "Total revenue" compiles to the unconditional SUM — the role grammar has
    no filtered metrics. How the refunded/cancelled ambiguity is surfaced and
    documented is graded separately, not here.

Exit 0 and ``ALL CHECKS PASSED`` when everything holds; exit 1 otherwise.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

SEMANTIC_KEY = "__nxd_semantic__"
AGGS = {"count", "count_distinct", "sum", "avg", "min", "max"}

# ---------------------------------------------------------------------------
# nxd API stubs — just enough surface to execute a canonical models.py and
# capture semantic_model instances + their attributes' _metadata blobs.
# ---------------------------------------------------------------------------

_MODELS: list["_SemanticModel"] = []


class _AttributeSpec:
    def __init__(self, name=None, data_type=None, **kwargs):
        self.name = name
        self.data_type = data_type
        self._metadata: dict = {}

    # public setter (post-stopgap API), routed to the same place
    def semantic_annotation(self, blob):
        self._metadata[SEMANTIC_KEY] = (
            blob if isinstance(blob, str) else json.dumps(blob)
        )
        return self

    def referencing(self, *args, **kwargs):
        return self

    def __getattr__(self, item):  # any other chained call is a no-op
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


def _install_stubs() -> None:
    def module(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        mod.__getattr__ = lambda item: _Anything()  # PEP 562 fallback
        sys.modules[name] = mod
        return mod

    nxd = module("nxd")
    spec = module("nxd.spec")
    spec.semantic_model = _SemanticModel
    spec.attribute = _attribute
    spec.Predicate = _Anything()
    model_mod = module("nxd.spec._model")
    model_mod.AttributeSpec = _AttributeSpec
    module("nxd.spec.data_types")  # every factory via __getattr__
    nxd.spec = spec


def load_models(models_path: Path) -> dict[str, dict[str, list[dict]]]:
    """Exec models.py under the stubs → {model: {column: [role, ...]}}."""
    _install_stubs()
    source = models_path.read_text(encoding="utf-8")
    namespace = {"__name__": "models", "__file__": str(models_path)}
    exec(compile(source, str(models_path), "exec"), namespace)  # noqa: S102

    registry: dict[str, dict[str, list[dict]]] = {}
    for model in _MODELS:
        columns: dict[str, list[dict]] = {}
        for col, attr in model._attributes.items():
            raw = attr._metadata.get(SEMANTIC_KEY)
            if raw is None:
                continue
            blob = json.loads(raw) if isinstance(raw, str) else raw
            columns[col] = blob["roles"] if "roles" in blob else [blob]
        registry[model.name] = columns
    return registry


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _rows(con, sql: str) -> set[tuple]:
    out = set()
    for row in con.execute(sql).fetchall():
        norm = tuple(
            round(float(v), 2) if isinstance(v, float) else v for v in row
        )
        out.add(norm)
    return out


def _by_kind(columns: dict[str, list[dict]], kind: str) -> list[tuple[str, dict]]:
    return [(col, role) for col, roles in columns.items()
            for role in roles if role.get("kind") == kind]


def run_checks(registry, duck_path: Path, schema_path: Path) -> list[tuple[str, str]]:
    import duckdb

    con = duckdb.connect(str(duck_path), read_only=True)
    failures: list[tuple[str, str]] = []
    passed: list[str] = []

    def check(check_id: str, ok: bool, why: str = "") -> None:
        (passed.append(check_id) if ok else failures.append((check_id, why)))

    live: dict[str, list[str]] = {}
    for table in ("customers", "orders"):
        live[table] = [r[0] for r in con.execute(f"DESCRIBE main.{_qi(table)}").fetchall()]

    # 1. Both profiled models declared under their bare physical names.
    profiled = {name: cols for name, cols in registry.items() if name in live}
    check("models-present", set(profiled) == {"customers", "orders"},
          f"declared={sorted(registry)} — need bare 'customers' and 'orders'")
    if set(profiled) != {"customers", "orders"}:
        _emit(passed, failures)
        return failures

    # 2. Every annotated attribute is a real column, byte-exact.
    bad = [f"{m}.{c}" for m, cols in profiled.items() for c in cols
           if c not in live[m]]
    check("columns-exist-exact", not bad, f"not in profiled tables: {bad}")

    # 3. Role grammar.
    grammar_errs: list[str] = []
    metric_names: list[str] = []
    dim_names: list[str] = []
    for model, cols in registry.items():
        for col, roles in cols.items():
            for role in roles:
                kind = role.get("kind")
                loc = f"{model}.{col}"
                if kind not in {"grain", "dimension", "metric", "join"}:
                    grammar_errs.append(f"{loc}: kind={kind!r}")
                elif kind == "metric":
                    if role.get("agg") not in AGGS:
                        grammar_errs.append(f"{loc}: agg={role.get('agg')!r}")
                    if role.get("boolean") and role.get("agg") != "sum":
                        grammar_errs.append(f"{loc}: boolean:true requires agg sum")
                    if not role.get("name") or not str(role.get("description") or "").strip():
                        grammar_errs.append(f"{loc}: metric needs name+description")
                    else:
                        metric_names.append(role["name"])
                elif kind == "dimension":
                    if not role.get("name") or not str(role.get("description") or "").strip():
                        grammar_errs.append(f"{loc}: dimension needs name+description")
                    else:
                        dim_names.append(role["name"])
                elif kind == "join":
                    if role.get("to_model") not in registry:
                        grammar_errs.append(f"{loc}: to_model={role.get('to_model')!r} undeclared")
                    if role.get("cardinality", "many_to_one") != "many_to_one":
                        grammar_errs.append(f"{loc}: cardinality must be many_to_one")
    check("role-grammar", not grammar_errs, "; ".join(grammar_errs[:4]))
    dup = sorted({n for n in metric_names if metric_names.count(n) > 1}
                 | {n for n in dim_names if dim_names.count(n) > 1})
    check("concept-names-unique", not dup, f"duplicates: {dup}")

    # 4. Grains: declared, and actually unique + non-null on the full table.
    for model in ("customers", "orders"):
        grain_cols = [c for c, _ in _by_kind(profiled[model], "grain")
                      if c in live[model]]
        if not grain_cols:
            check(f"grain-{model}", False, "no grain declared")
            continue
        cols_sql = ", ".join(_qi(c) for c in grain_cols)
        null_cond = " OR ".join(_qi(c) + " IS NULL" for c in grain_cols)
        total, distinct, nulls = con.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT ({cols_sql})), "
            f"COUNT(*) FILTER (WHERE {null_cond}) "
            f"FROM main.{_qi(model)}"
        ).fetchone()
        check(f"grain-{model}", distinct == total and nulls == 0,
              f"grain {grain_cols}: distinct={distinct}/{total}, nulls={nulls}")

    # 5. Join: on the MANY side (orders) → customers, valid to_column,
    #    unique ONE side, full FK containment.
    joins = [(col, role) for col, role in _by_kind(profiled["orders"], "join")
             if role.get("to_model") == "customers" and col in live["orders"]]
    join_ok, join_why, join_edge = False, "no orders→customers join declared", None
    for col, role in joins:
        to_col = role.get("to_column") or col
        if to_col not in live["customers"]:
            join_why = f"to_column {to_col!r} not on customers"
            continue
        total, distinct = con.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT {_qi(to_col)}) FROM main.customers"
        ).fetchone()
        if distinct != total:
            join_why = f"to_column {to_col} not unique on customers"
            continue
        orphans = con.execute(
            f"SELECT COUNT(*) FROM main.orders WHERE {_qi(col)} IS NOT NULL "
            f"AND {_qi(col)} NOT IN (SELECT {_qi(to_col)} FROM main.customers "
            f"WHERE {_qi(to_col)} IS NOT NULL)"
        ).fetchone()[0]
        if orphans:
            join_why = f"{orphans} orphan FK values via {col}->{to_col}"
            continue
        join_ok, join_edge = True, (col, to_col)
        break
    check("join-orders-to-customers", join_ok, join_why)
    if any(role.get("to_model") == "orders"
           for _, role in _by_kind(profiled["customers"], "join")):
        check("join-declared-on-many-side", False,
              "customers declares a join to orders — belongs on the MANY side")

    # 6. Answerability — execute each stakeholder question from the declared
    #    concepts and compare rows against a reference query.
    o, c = profiled["orders"], profiled["customers"]

    def metrics(cols, table, agg=None, boolean=None):
        out = []
        for col, role in _by_kind(cols, "metric"):
            if col not in live[table]:
                continue
            if agg and role.get("agg") not in agg:
                continue
            if boolean is not None and bool(role.get("boolean")) is not boolean:
                continue
            out.append(col)
        return out

    def dims(cols, table):
        return [col for col, _ in _by_kind(cols, "dimension") if col in live[table]]

    # Q1: total revenue by sales channel (unconditional sum — no filtered
    # metrics exist in the grammar; the status ambiguity is graded elsewhere).
    ref = _rows(con, "SELECT channel, SUM(amount_usd) FROM main.orders GROUP BY 1")
    q1 = any(
        _rows(con, f"SELECT {_qi(d)}, SUM({_qi(m)}) FROM main.orders GROUP BY 1") == ref
        for m in metrics(o, "orders", agg={"sum"}, boolean=False)
        for d in dims(o, "orders")
    )
    check("q1-revenue-by-channel", q1,
          "no (sum metric x dimension) on orders reproduces revenue by channel")

    # Q2: churned customers per segment (boolean CASE-sum, as the dialect compiles it).
    case = ("SUM(CASE WHEN CAST({col} AS VARCHAR) IN "
            "('true','TRUE','True','t','1','yes','YES') THEN 1 ELSE 0 END)")
    ref = _rows(con, "SELECT segment, " + case.format(col="is_churned")
                + " FROM main.customers GROUP BY 1")
    q2 = any(
        _rows(con, f"SELECT {_qi(d)}, " + case.format(col=_qi(m))
              + " FROM main.customers GROUP BY 1") == ref
        for m in metrics(c, "customers", agg={"sum"}, boolean=True)
        for d in dims(c, "customers")
    )
    check("q2-churned-per-segment", q2,
          "no (boolean sum metric x dimension) on customers reproduces churn by segment")

    # Q3: which countries place the most orders (cross-table via the join).
    q3 = False
    if join_ok:
        fk, to_col = join_edge
        # Reference uses the canonical FK edge, independent of what was declared.
        ref = _rows(con,
                    "SELECT ct.country, COUNT(DISTINCT o.order_id) FROM main.orders o "
                    "JOIN main.customers ct ON o.customer_id = ct.customer_id GROUP BY 1")
        for agg_name, expr in (("count", "COUNT({m})"), ("count_distinct", "COUNT(DISTINCT {m})")):
            for m in metrics(o, "orders", agg={agg_name}):
                for d in dims(c, "customers"):
                    sql = (f"SELECT ct.{_qi(d)}, " + expr.format(m="o." + _qi(m))
                           + f" FROM main.orders o JOIN main.customers ct "
                           f"ON o.{_qi(fk)} = ct.{_qi(to_col)} GROUP BY 1")
                    if _rows(con, sql) == ref:
                        q3 = True
    check("q3-orders-by-country", q3,
          "no (count metric on orders x customers dimension) via the declared join "
          "reproduces order counts by country")

    # Q4: average order value.
    ref = _rows(con, "SELECT AVG(amount_usd) FROM main.orders")
    q4 = any(
        _rows(con, f"SELECT AVG({_qi(m)}) FROM main.orders") == ref
        for m in metrics(o, "orders", agg={"avg"}, boolean=False)
    )
    check("q4-average-order-value", q4, "no avg metric on orders reproduces AOV")

    # 7. schema.json handoff artifact exists and matches the live tables.
    ok, why = False, f"{schema_path.name} missing"
    if schema_path.exists():
        try:
            doc = json.loads(schema_path.read_text(encoding="utf-8"))
            tables = doc.get("tables", {})
            missing = {"customers", "orders"} - set(tables)
            if missing:
                why = f"tables missing from schema.json: {sorted(missing)}"
            else:
                drift = [
                    t for t in ("customers", "orders")
                    if sorted(tables[t].get("columns", {})) != sorted(live[t])
                ]
                ok, why = not drift, f"column drift vs live tables: {drift}"
        except (json.JSONDecodeError, AttributeError) as exc:
            why = f"schema.json unreadable: {exc}"
    check("schema-json-artifact", ok, why)

    _emit(passed, failures)
    con.close()
    return failures


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
    argv = sys.argv[1:]
    models_path = Path(argv[0]) if len(argv) > 0 else Path("models.py")
    duck_path = Path(argv[1]) if len(argv) > 1 else Path("source.duckdb")
    schema_path = Path(argv[2]) if len(argv) > 2 else Path("schema.json")
    for required in (models_path, duck_path):
        if not required.exists():
            print(f"not found: {required}", file=sys.stderr)
            return 2
    try:
        registry = load_models(models_path)
    except Exception as exc:  # noqa: BLE001 — surface the author error verbatim
        print(f"FAIL load-models: executing {models_path} raised {exc!r}")
        return 1
    return 1 if run_checks(registry, duck_path, schema_path) else 0


if __name__ == "__main__":
    raise SystemExit(main())

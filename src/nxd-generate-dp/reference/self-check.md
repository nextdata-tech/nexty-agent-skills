# The pre-handoff self-check script

## Contents

- What the two phases are
- What this script does NOT cover
- The script
- Reading a failure

## What the two phases are

The dry-run for Step 7 of nxd-generate-dp, in two phases:

- **Phase A — structural check of `models.py` and `spec.py`.** Parses both files
  with `ast` and checks them against the pinned DSL surface in
  [reference/nxd-spec-api.md](nxd-spec-api.md). Nothing is imported and nothing
  is executed, because the `nxd` wheel is an internal package on a private index
  and is NOT installable here — a real import raises
  `ModuleNotFoundError: No module named 'nxd'`.
- **Phase B — dry-run of the transform** against a scratch DuckDB: the
  supervisor's execution minus the kernel.

One script, one command, one exit code. What to check and how to read a failure
is in SKILL.md; this file is the runnable script.

## What this script does NOT cover

Read this before you trust a green result. Phase A is a *structural* check, not
a runtime one, and the gap is real:

- **It checks signatures against a pinned surface (`nxd` v0.41.139), not against
  the installed wheel.** If the DSL has drifted since that pin, Phase A enforces
  the pin, not reality. Re-derive the changed signature and update
  `nxd-spec-api.md` and this script together — the drift protocol is in that
  file's "Version pin and drift" section.
- **It cannot execute the builders.** Everything `nxd.spec` validates at build
  time is unexercised: value-shape errors inside a role blob, `FieldRef`
  resolution for `metric(of=...)`, and the supervisor's spec→YAML compilation at
  create time. **A closure can pass Phase A in full and still fail when the
  supervisor pins it.**
- **It cannot see dynamic constructs.** A schema entry built from a variable, a
  comprehension, or a `**` spread is reported as `unverified:
  <model>.<column>` and is NOT checked. The printed unverified list is the
  honest scope boundary — read it.
- **It says nothing about whether the semantics are right.** Whether a column
  should be a dimension, whether a metric's aggregation answers the question,
  whether the key is the real grain — no static check can know. Only closed-set
  violations (misspelled kwargs, unknown `Agg` members, unknown dtypes,
  misplaced roles, broken naming invariant) fail.

Phase B executes for real, so what it reports is what will happen — but it
covers only `transform/main.py`.

## The script

Run from the closure root:

```bash
uv run --python 3.12 --with "dlt[duckdb]==1.28.2" --with "duckdb==1.5.4" \
  --with "pandas==2.3.3" python self_check.py
```

```python
# self_check.py
import ast, re, sys, tempfile, types
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- Phase A ---
# Structural check of models.py + spec.py against the pinned nxd.spec surface
# (reference/nxd-spec-api.md, nxd v0.41.139). No imports, no execution.

DTYPES = {
    "string", "boolean", "date", "date32", "date64", "double", "float",
    "float16", "float32", "float64", "int8", "int16", "int32", "int64",
    "uint", "uint8", "uint16", "uint32", "uint64", "number", "vector",
    "binary", "vector_embeddings", "timestamp", "decimal", "duration",
    "time32", "time64", "list", "list_view", "large_list", "large_list_view",
    "map", "dictionary", "struct", "variant",
}
AGGS = {"COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MIN", "MAX"}
KWARGS = {                      # role builder -> allowed keyword names
    "primary_key": set(),
    "dimension": {"name", "pii", "label", "description"},
    "join": {"to", "to_column", "cardinality", "to_data_product"},
    "metric": {"of", "name", "description", "boolean", "extra_dimensions",
               "column"},
    "field": {"roles", "description", "label", "name"},
    "metric_field": {"description", "name"},
}
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")

errors, unverified = [], []
def bad(msg): errors.append(msg)

def call_name(node):
    """Dotted or bare name of a Call's func, or None."""
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None

def spine(node):
    """Every Call in a chained expression, outermost first."""
    out = []
    while isinstance(node, ast.Call):
        out.append(node)
        node = node.func.value if isinstance(node.func, ast.Attribute) else None
    return out

def literal_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(
        node.value, str) else None

def check_kwargs(call, name, where):
    allowed = KWARGS[name]
    for kw in call.keywords:
        if kw.arg is None:
            unverified.append(f"{where}: **spread into {name}()")
            continue
        if kw.arg in allowed:
            continue
        if name == "join" and kw.arg == "to_model":
            bad(f"{where}: join() takes to=, not to_model=")
        else:
            bad(f"{where}: {name}() has no keyword '{kw.arg}' "
                f"(allowed: {sorted(allowed) or 'none'})")
    if name == "primary_key" and call.args:
        bad(f"{where}: primary_key() takes no arguments")
    if name == "metric":
        if any(k.arg == "of" for k in call.keywords) and \
           any(k.arg == "column" for k in call.keywords):
            bad(f"{where}: metric() takes of= or column=, never both")

def check_dtype(node, where):
    """A call in dtype position must be a known data-type constructor."""
    n = call_name(node)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if n not in DTYPES:
            bad(f"{where}: unknown data type '{n}()' — not in the pinned "
                f"nxd.spec.data_types surface")

def walk_roles(node, where, *, in_view):
    """Validate every role/dtype/Agg reference inside one schema entry."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) \
                and sub.value.id == "Agg" and sub.attr not in AGGS:
            bad(f"{where}: Agg.{sub.attr} is not a member "
                f"(allowed: {sorted(AGGS)})")
        if not isinstance(sub, ast.Call):
            continue
        n = call_name(sub)
        if n in KWARGS:
            check_kwargs(sub, n, where)
        if n == "metric":
            if not in_view:
                bad(f"{where}: metric() inside a semantic_model schema — "
                    f"metrics are consume-time only, declare them as "
                    f"metric_field(metric(...)) on a semantic_view")
            if sub.args and not (isinstance(sub.args[0], ast.Attribute)
                                 and isinstance(sub.args[0].value, ast.Name)
                                 and sub.args[0].value.id == "Agg"):
                bad(f"{where}: metric()'s first argument must be an Agg "
                    f"member (e.g. Agg.SUM), not a bare value")

def parse_models(src, path):
    """-> ({var: name}, {var: kind}, {name: joins}, {name: has_pk})"""
    tree = ast.parse(src, path)
    var_name, var_kind, joins, has_pk = {}, {}, {}, {}
    for imp in ast.walk(tree):
        if isinstance(imp, ast.ImportFrom) and (imp.module or "").startswith("nxd"):
            head = imp.module.split(".")
            if not (head[:2] == ["nxd", "spec"] and len(head) <= 3):
                bad(f"{path}: import from '{imp.module}' — public DSL only "
                    f"(nxd.spec / nxd.spec.data_types)")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        chain = spine(node.value)
        if not chain:
            continue
        root = chain[-1]
        kind = call_name(root)
        if kind not in ("semantic_model", "semantic_view"):
            continue
        model = literal_str(root.args[0]) if root.args else None
        if model is None or not SNAKE.match(model):
            bad(f"{path}: {kind}() name must be a lowercase snake_case string "
                f"literal, got {ast.unparse(root.args[0]) if root.args else '<none>'}")
            continue
        var_name[target.id], var_kind[target.id] = model, kind
        joins.setdefault(model, []); has_pk[model] = False
        in_view = kind == "semantic_view"
        for call in chain:
            if call_name(call) not in ("schema", "fields") or not call.args:
                continue
            schema = call.args[0]
            if not isinstance(schema, ast.Dict):
                unverified.append(f"{model}: .schema() argument is not a dict literal")
                continue
            if in_view and not schema.keys:
                bad(f"{path}: semantic_view('{model}') has an empty schema — "
                    f"this raises at build time")
            for k, v in zip(schema.keys, schema.values):
                col = literal_str(k) or "<dynamic>"
                where = f"{path}:{model}.{col}"
                if k is None:
                    unverified.append(f"{model}: ** spread in .schema()")
                    continue
                entry_calls = ([v] if isinstance(v, ast.Call)
                               else list(v.elts) if isinstance(v, ast.Tuple) else [])
                if not entry_calls and not isinstance(v, ast.Tuple):
                    unverified.append(f"{where}: schema value is "
                                      f"{type(v).__name__}, not a call or tuple")
                    continue
                top = call_name(v) if isinstance(v, ast.Call) else None
                if in_view and isinstance(v, ast.Call) and top != "metric_field":
                    bad(f"{where}: a semantic_view field must be "
                        f"metric_field(...), got {top}()")
                if top in ("field", "metric_field") and v.args:
                    check_dtype(v.args[0], where)
                elif top in DTYPES or (top and isinstance(v, ast.Call)
                                       and isinstance(v.func, ast.Name)):
                    check_dtype(v, where)
                if isinstance(v, ast.Tuple) and v.elts:
                    check_dtype(v.elts[0], where)
                walk_roles(v, where, in_view=in_view)
                for sub in ast.walk(v):
                    if call_name(sub) == "primary_key":
                        has_pk[model] = True
                    if call_name(sub) == "join":
                        tgt = (literal_str(sub.args[0]) if sub.args else
                               next((literal_str(k.value) for k in sub.keywords
                                     if k.arg == "to"), None))
                        if tgt:
                            joins[model].append((tgt, where))
    return var_name, var_kind, joins, has_pk

def parse_spec(src, path, var_name, var_kind):
    """-> set of promised model names"""
    tree = ast.parse(src, path)
    promised, modelled, saw = set(), set(), {"data_product": False,
                                             "script": False, "compute": False,
                                             "secrets": False, "port": False}
    if ".semantic_tools(" in src:
        bad(f"{path}: .semantic_tools(...) is forbidden on desktop")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        n = call_name(node)
        if n == "data_product":
            saw["data_product"] = True
            ip = next((literal_str(k.value) for k in node.keywords
                       if k.arg == "infra_profile"), None)
            if ip != "desktop-local":
                bad(f"{path}: data_product(infra_profile=...) must be the "
                    f"literal \"desktop-local\", got {ip!r}")
        elif n == "script":
            saw["script"] = True
            if literal_str(node.args[0] if node.args else None) != "transform/main.py":
                bad(f"{path}: script() must point at \"transform/main.py\"")
        elif n in ("compute", "secrets"):
            saw[n] = True
        elif n == "port":
            saw["port"] = True
            if literal_str(node.args[0] if node.args else None) != "duckdb":
                bad(f"{path}: the output port must be named \"duckdb\"")
            if len(node.args) < 2 or call_name(node.args[1]) != "storage":
                bad(f"{path}: .port(\"duckdb\", ...) second argument must be "
                    f"a storage(...) call")
        elif n in ("promise", "model") and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Name) and arg.id in var_name:
                (promised if n == "promise" else modelled).add(var_name[arg.id])
                if n == "promise" and var_kind[arg.id] == "semantic_view":
                    bad(f"{path}: .promise({arg.id}) — {var_name[arg.id]} is a "
                        f"semantic_view; views are registered with .model(), "
                        f"never promised")
            else:
                unverified.append(f"{path}: .{n}() argument "
                                  f"{ast.unparse(arg)} is not a models.py name")
    for key, msg in [("data_product", "no data_product(...) call"),
                     ("script", "no script(...) call"),
                     ("compute", "script() has no .compute(...)"),
                     ("secrets", "script() has no .secrets([...])"),
                     ("port", "no .port(...) call")]:
        if not saw[key]:
            bad(f"{path}: {msg}")
    for ref in re.findall(r'"(/infra-profile/[^"]*)"', src):
        if not re.fullmatch(r"/infra-profile/desktop-local#/services/[a-z0-9-]+", ref):
            bad(f"{path}: malformed service reference {ref!r} — expected "
                f"/infra-profile/desktop-local#/services/<name>")
    return promised, modelled

def model_constants(src):
    """BASE_MODELS / PHYSICAL_MODELS out of transform/main.py, statically."""
    tree, out = ast.parse(src, "transform/main.py"), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                isinstance(node.targets[0], ast.Name) and \
                node.targets[0].id in ("BASE_MODELS", "PHYSICAL_MODELS"):
            try:
                out[node.targets[0].id] = list(ast.literal_eval(node.value))
            except ValueError:
                unverified.append(f"transform/main.py: {node.targets[0].id} "
                                  f"is not a literal")
    return out

models_src = Path("models.py").read_text()
spec_src = Path("spec.py").read_text()
transform_src = Path("transform/main.py").read_text()

var_name, var_kind, joins, has_pk = parse_models(models_src, "models.py")
promised, modelled = parse_spec(spec_src, "spec.py", var_name, var_kind)

base_names = {n for v, n in var_name.items() if var_kind[v] == "semantic_model"}
for model, edges in joins.items():
    for tgt, where in edges:
        if tgt not in base_names:
            bad(f"{where}: join(to=\"{tgt}\") — no semantic_model of that name "
                f"in models.py")
for model in base_names:
    if not has_pk[model]:
        bad(f"models.py: semantic_model('{model}') declares no primary_key()")

consts = model_constants(transform_src)
physical = set(consts.get("PHYSICAL_MODELS", []))
if promised != base_names:
    bad(f"naming invariant: semantic_model names {sorted(base_names)} != "
        f"promised names {sorted(promised)}")
if physical and promised != physical:
    bad(f"naming invariant: promised names {sorted(promised)} != "
        f"PHYSICAL_MODELS {sorted(physical)}")
if "BASE_MODELS" in consts:
    dirs = {d.name for d in Path("data").iterdir() if d.is_dir()}
    if set(consts["BASE_MODELS"]) != dirs:
        bad(f"BASE_MODELS {sorted(consts['BASE_MODELS'])} != data/ directories "
            f"{sorted(dirs)}")

for u in unverified:
    print(f"unverified: {u}")
if errors:
    print("\nPHASE A FAILED — structural check of models.py / spec.py:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print(f"phase A ok — {len(base_names)} semantic_model, "
      f"{len(modelled - base_names)} semantic_view, "
      f"{len(unverified)} unverified entries")

# ---------------------------------------------------------------- Phase B ---
# Dry-run of transform/main.py against a scratch DuckDB. This one EXECUTES.

@dataclass
class DuckDbOutput:
    path: str; schema: str; model_tables: dict; models: dict = field(default_factory=dict)

nxd = types.ModuleType("nxd"); core = types.ModuleType("nxd.core")
ctx = types.ModuleType("nxd.core.context"); ctx.DuckDbOutput = DuckDbOutput; dp = types.SimpleNamespace(
    on_transform=lambda *a, **k: (lambda fn: fn), main=lambda: None)
nxd.data_product, nxd.core, core.context = dp, core, ctx
sys.modules.update({"nxd": nxd, "nxd.core": core, "nxd.core.context": ctx})

sys.path.insert(0, ".")
from transform.main import BASE_MODELS, PHYSICAL_MODELS, ingest  # noqa: E402

DIRS = [d.name for d in sorted(Path("data").iterdir()) if d.is_dir()]
# Only BASE models are backed by data/. Derived models are landed by the
# transform and appear in PHYSICAL_MODELS with no directory of their own.
assert set(BASE_MODELS) == set(DIRS), "base models must match data/"
assert set(BASE_MODELS) <= set(PHYSICAL_MODELS), "base models must be promised"
run = Path(tempfile.mkdtemp())
# model_tables comes from PHYSICAL_MODELS, never the data/ listing: a map built
# from directories KeyErrors the moment a derived model resolves its table name.
out = DuckDbOutput(path=str(run / "data.duckdb"), schema="main",
                   model_tables={m: m for m in PHYSICAL_MODELS})
ingest(duckdb=out, secrets={"csv_source": str(Path("data").resolve())})
import duckdb
con = duckdb.connect(out.path, read_only=True)
for m in PHYSICAL_MODELS:  # unquoted main.<name> — the invariant, physically
    print(m, con.execute(f"SELECT COUNT(*) FROM main.{m}").fetchone()[0])
assert (run / ".transform-complete").exists()
print(f"SELF-CHECK OK — transform dry-run EXECUTED; models.py/spec.py checked "
      f"STRUCTURALLY against the pinned nxd v0.41.139 DSL surface (not "
      f"executed — no nxd wheel installable here); {len(unverified)} "
      f"unverified entries listed above. A spec fault only the real wheel or "
      f"the supervisor's spec compilation can raise still reaches handoff.")
```

## Reading a failure

The row counts printed for derived models are worth reading, not just passing:
a derived table with zero rows, or with exactly as many rows as its source when
the derivation was supposed to expand or collapse, means the derivation ran but
did nothing. The Step-3b asserts should have caught that — if they did not, the
invariant they encode was too weak.

Reading a Phase A failure: every message names the file, model, and column. A
kwarg rejection (`join() takes to=, not to_model=`) is a typo — fix the call. A
naming-invariant failure is a diverged name — fix the NAME in every place it
appears (`models.py`, `.promise`, `PHYSICAL_MODELS`, `data/<name>/`), never
quote around it. If a message contradicts the installed wheel's actual
behaviour, the pin has drifted: re-derive that one signature, and update
`nxd-spec-api.md` and this script together.
